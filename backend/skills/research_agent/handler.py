"""
Research Agent Skill — Multi-step web research with deeper analysis.

Performs comprehensive web research by:
  1) Formulating multiple search queries from the research topic
  2) Fetching results from DuckDuckGo (duckduckgo-search)
  3) Following top links and extracting content (httpx + beautifulsoup4)
  4) Synthesizing findings via Brain/LLM with structured output
  5) Storing research results in memory for future reference

Actions:
  - research: Full multi-step research flow (default)
  - quick_search: Simple DuckDuckGo search without deep content extraction
  - extract_url: Fetch and extract content from a specific URL
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal
from core.memory.manager import MemoryManager
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = 15.0
MAX_CONTENT_PER_PAGE = 4000  # chars extracted per page
MAX_PAGES_TO_FETCH = 5
DEFAULT_QUERIES_PER_TOPIC = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_url(url: str, timeout: float = HTTP_TIMEOUT) -> Optional[str]:
    """Fetch a URL and return its HTML content, or None on failure."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "SanaaAI-ResearchAgent/2.0 (compatible; research bot)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except httpx.TimeoutException:
        logger.warning(f"[ResearchAgent] Timeout fetching {url}")
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning(f"[ResearchAgent] HTTP {exc.response.status_code} for {url}")
        return None
    except Exception as exc:
        logger.warning(f"[ResearchAgent] Failed to fetch {url}: {exc}")
        return None


def _extract_page_text(html: str, max_chars: int = MAX_CONTENT_PER_PAGE) -> str:
    """Extract visible text from HTML, stripping scripts, styles, nav, footer."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text_content = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    lines = [line.strip() for line in text_content.split("\n") if line.strip()]
    return "\n".join(lines)[:max_chars]


def _extract_page_title(html: str) -> str:
    """Extract the page title from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


def _ddg_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Run a DuckDuckGo text search and return results."""
    try:
        ddgs = DDGS()
        results = ddgs.text(query, max_results=max_results)
        return results if results else []
    except Exception as exc:
        logger.warning(f"[ResearchAgent] DDG search failed for '{query}': {exc}")
        return []


# ---------------------------------------------------------------------------
# Skill class
# ---------------------------------------------------------------------------

class ResearchAgentSkill(BaseSkill):
    """Multi-step web research agent with deep analysis."""

    name = "research_agent"
    description = (
        "Performs multi-step web research: formulates search queries from a topic, "
        "fetches DuckDuckGo results, extracts content from top links, synthesizes "
        "findings via LLM, and stores results in memory."
    )
    version = "2.0.0"
    permissions = ["network"]
    tags = ["research", "ai", "search", "intelligence", "analysis"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "research")

        if action == "research":
            return await self._full_research(args, context)
        elif action == "quick_search":
            return await self._quick_search(args, context)
        elif action == "extract_url":
            return await self._extract_url(args, context)

        return SkillResult(
            success=False,
            error=(
                f"Unknown action: {action}. "
                "Valid actions: research, quick_search, extract_url"
            ),
        )

    # ------------------------------------------------------------------
    # Step 1: Formulate search queries from topic using LLM
    # ------------------------------------------------------------------
    async def _formulate_queries(
        self, topic: str, num_queries: int, context: SkillContext
    ) -> List[str]:
        """Use LLM to generate diverse search queries from a research topic."""
        if not context.brain:
            # Fallback: generate basic query variants without LLM
            return self._fallback_queries(topic, num_queries)

        prompt = (
            f"You are a research assistant. Given the research topic below, "
            f"generate exactly {num_queries} diverse DuckDuckGo search queries that "
            f"will help gather comprehensive information.\n\n"
            f"TOPIC: {topic}\n\n"
            f"Requirements:\n"
            f"- Each query should explore a different angle or aspect\n"
            f"- Include a mix of broad and specific queries\n"
            f"- Use search-engine-friendly phrasing\n"
            f"- Return ONLY the queries, one per line, no numbering or bullet points\n"
            f"- No explanations or commentary"
        )

        try:
            response = await context.brain.think(
                prompt, complexity="fast", channel="research_agent"
            )
            if response:
                queries = [
                    q.strip().lstrip("0123456789.-) ")
                    for q in response.strip().split("\n")
                    if q.strip() and len(q.strip()) > 3
                ]
                # Ensure we have the right number
                if queries:
                    return queries[:num_queries]
        except Exception as exc:
            logger.warning(f"[ResearchAgent] Query formulation failed: {exc}")

        return self._fallback_queries(topic, num_queries)

    @staticmethod
    def _fallback_queries(topic: str, num_queries: int) -> List[str]:
        """Generate basic query variants without LLM."""
        queries = [topic]
        if num_queries >= 2:
            queries.append(f"{topic} latest developments 2026")
        if num_queries >= 3:
            queries.append(f"{topic} analysis overview")
        return queries[:num_queries]

    # ------------------------------------------------------------------
    # Step 2: Search and fetch content
    # ------------------------------------------------------------------
    async def _search_and_extract(
        self, queries: List[str], max_results_per_query: int = 3, max_pages: int = MAX_PAGES_TO_FETCH
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """Execute searches and extract content from top results.

        Returns:
            Tuple of (extracted_contents, errors)
        """
        all_results: List[Dict[str, str]] = []
        seen_urls: set = set()

        # Gather search results from all queries
        for query in queries:
            results = _ddg_search(query, max_results=max_results_per_query)
            for res in results:
                url = res.get("href", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append({
                        "url": url,
                        "title": res.get("title", ""),
                        "snippet": res.get("body", ""),
                        "query": query,
                    })

        # Fetch and extract content from top pages
        extracted: List[Dict[str, Any]] = []
        errors: List[str] = []
        pages_fetched = 0

        for result in all_results:
            if pages_fetched >= max_pages:
                break

            url = result["url"]
            logger.info(f"[ResearchAgent] Fetching content from: {url}")

            html = await _fetch_url(url)
            if html is None:
                errors.append(f"Failed to fetch: {url}")
                continue

            page_text = _extract_page_text(html)
            page_title = _extract_page_title(html) or result["title"]

            if len(page_text.strip()) < 100:
                errors.append(f"Insufficient content from: {url}")
                continue

            extracted.append({
                "url": url,
                "title": page_title,
                "snippet": result["snippet"],
                "content": page_text,
                "query": result["query"],
            })
            pages_fetched += 1

        return extracted, errors

    # ------------------------------------------------------------------
    # Step 3: Synthesize findings via LLM
    # ------------------------------------------------------------------
    async def _synthesize(
        self, topic: str, sources: List[Dict[str, Any]], context: SkillContext
    ) -> Dict[str, Any]:
        """Use LLM to synthesize extracted content into a structured report."""
        if not context.brain:
            return {
                "key_findings": ["Brain engine not available for synthesis"],
                "sources": [{"title": s["title"], "url": s["url"]} for s in sources],
                "confidence": 0.3,
                "knowledge_gaps": ["LLM synthesis not performed"],
                "report": "Research data collected but synthesis unavailable (no Brain engine).",
            }

        # Build source context for LLM
        source_texts = []
        for i, src in enumerate(sources, 1):
            source_texts.append(
                f"SOURCE {i}: {src['title']} ({src['url']})\n"
                f"CONTENT:\n{src['content'][:3000]}\n"
            )
        combined = "\n---\n".join(source_texts)

        prompt = (
            f"You are a senior research analyst. Synthesize the following web research "
            f"about '{topic}' into a comprehensive, structured report.\n\n"
            f"RAW MATERIALS ({len(sources)} sources):\n{combined}\n\n"
            f"Produce the report in this EXACT format:\n\n"
            f"## Key Findings\n"
            f"- [finding 1]\n"
            f"- [finding 2]\n"
            f"- [finding 3]\n"
            f"(list 3-7 key findings)\n\n"
            f"## Detailed Analysis\n"
            f"[Detailed synthesis of the research, 2-4 paragraphs]\n\n"
            f"## Sources\n"
            f"- [source title] (URL)\n"
            f"(list all sources used)\n\n"
            f"## Confidence Assessment\n"
            f"[Rate confidence as HIGH/MEDIUM/LOW and explain why]\n\n"
            f"## Knowledge Gaps\n"
            f"- [gap 1]\n"
            f"- [gap 2]\n"
            f"(areas where more research is needed)"
        )

        try:
            report_text = await context.brain.think(
                prompt, complexity="high", channel="research_agent"
            )
        except Exception as exc:
            logger.error(f"[ResearchAgent] LLM synthesis failed: {exc}")
            return {
                "key_findings": [f"Synthesis failed: {exc}"],
                "sources": [{"title": s["title"], "url": s["url"]} for s in sources],
                "confidence": 0.2,
                "knowledge_gaps": ["Synthesis could not be completed"],
                "report": f"Research data collected but synthesis failed: {exc}",
            }

        if not report_text:
            return {
                "key_findings": ["LLM returned empty response"],
                "sources": [{"title": s["title"], "url": s["url"]} for s in sources],
                "confidence": 0.2,
                "knowledge_gaps": ["Synthesis produced no output"],
                "report": "LLM returned empty synthesis.",
            }

        # Parse the structured report
        parsed = self._parse_report(report_text, sources)
        parsed["report"] = report_text
        return parsed

    @staticmethod
    def _parse_report(
        report_text: str, sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract structured data from the LLM-generated report."""
        key_findings: List[str] = []
        knowledge_gaps: List[str] = []
        confidence = 0.5  # default

        current_section = ""
        for line in report_text.split("\n"):
            stripped = line.strip()

            if stripped.startswith("## Key Findings"):
                current_section = "findings"
                continue
            elif stripped.startswith("## Detailed Analysis"):
                current_section = "analysis"
                continue
            elif stripped.startswith("## Sources"):
                current_section = "sources"
                continue
            elif stripped.startswith("## Confidence"):
                current_section = "confidence"
                continue
            elif stripped.startswith("## Knowledge Gaps"):
                current_section = "gaps"
                continue
            elif stripped.startswith("## "):
                current_section = ""
                continue

            if current_section == "findings" and stripped.startswith("- "):
                key_findings.append(stripped[2:].strip())
            elif current_section == "gaps" and stripped.startswith("- "):
                knowledge_gaps.append(stripped[2:].strip())
            elif current_section == "confidence":
                lower = stripped.lower()
                if "high" in lower:
                    confidence = 0.85
                elif "medium" in lower:
                    confidence = 0.6
                elif "low" in lower:
                    confidence = 0.35

        return {
            "key_findings": key_findings if key_findings else ["See report for details"],
            "sources": [{"title": s["title"], "url": s["url"]} for s in sources],
            "confidence": confidence,
            "knowledge_gaps": knowledge_gaps if knowledge_gaps else [],
        }

    # ------------------------------------------------------------------
    # Step 4: Store in memory
    # ------------------------------------------------------------------
    async def _store_in_memory(
        self,
        topic: str,
        synthesis: Dict[str, Any],
        context: SkillContext,
    ) -> Optional[int]:
        """Store research results in the memory system for future reference."""
        findings_text = "\n".join(
            f"- {f}" for f in synthesis.get("key_findings", [])
        )
        sources_text = "\n".join(
            f"- {s['title']} ({s['url']})"
            for s in synthesis.get("sources", [])
        )
        gaps_text = "\n".join(
            f"- {g}" for g in synthesis.get("knowledge_gaps", [])
        )

        memory_content = (
            f"Research: {topic}\n"
            f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"Confidence: {synthesis.get('confidence', 0.5)}\n\n"
            f"Key Findings:\n{findings_text}\n\n"
            f"Sources:\n{sources_text}\n\n"
            f"Knowledge Gaps:\n{gaps_text}"
        )

        try:
            memory = MemoryManager()
            memory_id = await memory.store(
                content=memory_content,
                category="research",
                source="research_agent",
                confidence=synthesis.get("confidence", 0.5),
                metadata={
                    "topic": topic,
                    "num_sources": len(synthesis.get("sources", [])),
                    "num_findings": len(synthesis.get("key_findings", [])),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(f"[ResearchAgent] Stored research memory ID {memory_id}")
            return memory_id
        except Exception as exc:
            logger.error(f"[ResearchAgent] Failed to store in memory: {exc}")
            return None

    # ------------------------------------------------------------------
    # Action: research (full multi-step flow)
    # ------------------------------------------------------------------
    async def _full_research(self, args: dict, context: SkillContext) -> SkillResult:
        """Execute the full multi-step research pipeline."""
        topic = args.get("topic")
        if not topic:
            return SkillResult(
                success=False,
                error="Parameter 'topic' is required for research.",
            )

        max_results = min(int(args.get("max_results", 3)), 5)
        num_queries = min(int(args.get("num_queries", DEFAULT_QUERIES_PER_TOPIC)), 5)
        max_pages = min(int(args.get("max_pages", MAX_PAGES_TO_FETCH)), 8)

        logger.info(f"[ResearchAgent] Starting multi-step research on: {topic}")

        # Step 1: Formulate search queries
        queries = await self._formulate_queries(topic, num_queries, context)
        logger.info(f"[ResearchAgent] Generated {len(queries)} queries: {queries}")

        # Step 2: Search and extract content
        extracted, fetch_errors = await self._search_and_extract(
            queries, max_results_per_query=max_results, max_pages=max_pages
        )

        if not extracted:
            # Return partial result if we have search results but no content
            return SkillResult(
                success=False,
                error=(
                    "Failed to extract content from any search results. "
                    f"Errors: {'; '.join(fetch_errors[:5])}"
                ),
                data={
                    "queries": queries,
                    "errors": fetch_errors,
                },
            )

        # Step 3: Synthesize via LLM
        synthesis = await self._synthesize(topic, extracted, context)

        # Step 4: Store in memory
        memory_id = await self._store_in_memory(topic, synthesis, context)

        # Build output
        report = synthesis.get("report", "No report generated.")
        output = f"🔍 **Research Report: {topic}**\n\n{report}"

        return SkillResult(
            success=True,
            output=output,
            data={
                "topic": topic,
                "queries_used": queries,
                "sources_count": len(extracted),
                "sources": synthesis.get("sources", []),
                "key_findings": synthesis.get("key_findings", []),
                "confidence": synthesis.get("confidence", 0.5),
                "knowledge_gaps": synthesis.get("knowledge_gaps", []),
                "memory_id": memory_id,
                "fetch_errors": fetch_errors,
                "pages_extracted": len(extracted),
            },
        )

    # ------------------------------------------------------------------
    # Action: quick_search
    # ------------------------------------------------------------------
    async def _quick_search(self, args: dict, context: SkillContext) -> SkillResult:
        """Quick DuckDuckGo search without deep content extraction."""
        topic = args.get("topic")
        if not topic:
            return SkillResult(
                success=False,
                error="Parameter 'topic' is required for quick_search.",
            )

        max_results = min(int(args.get("max_results", 5)), 10)

        results = _ddg_search(topic, max_results=max_results)
        if not results:
            return SkillResult(
                success=False,
                error=f"No search results found for: {topic}",
            )

        output_lines = [f"🔎 Quick Search: {topic}", f"Results: {len(results)}", ""]
        for i, res in enumerate(results, 1):
            output_lines.append(f"{i}. **{res.get('title', 'Untitled')}**")
            output_lines.append(f"   {res.get('href', '')}")
            body = res.get("body", "")
            if body:
                output_lines.append(f"   {body[:200]}")
            output_lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "topic": topic,
                "results_count": len(results),
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    }
                    for r in results
                ],
            },
        )

    # ------------------------------------------------------------------
    # Action: extract_url
    # ------------------------------------------------------------------
    async def _extract_url(self, args: dict, context: SkillContext) -> SkillResult:
        """Fetch a specific URL and extract its text content."""
        url = args.get("url")
        if not url:
            return SkillResult(
                success=False,
                error="Parameter 'url' is required for extract_url.",
            )

        html = await _fetch_url(url)
        if html is None:
            return SkillResult(
                success=False,
                error=f"Failed to fetch URL: {url}",
            )

        page_text = _extract_page_text(html)
        page_title = _extract_page_title(html)

        if not page_text.strip():
            return SkillResult(
                success=False,
                error=f"No text content extracted from: {url}",
            )

        return SkillResult(
            success=True,
            output=f"📄 **{page_title or url}**\n\n{page_text[:5000]}",
            data={
                "url": url,
                "title": page_title,
                "content": page_text,
                "content_length": len(page_text),
            },
        )


# Register entry point
handler = ResearchAgentSkill
