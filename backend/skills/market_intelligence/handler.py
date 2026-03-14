"""
Market Intelligence Skill — competitor monitoring and market analysis.

Actions:
  - scan_market: Aggregate signals from configured RSS feeds and web sources
    using httpx + beautifulsoup4.
  - analyze_trends: Use Brain/LLM to identify market trends, opportunities,
    and threats from aggregated data.
  - competitor_watch: Monitor specific competitor URLs for content changes
    using site content hashing.
  - report: Generate a structured market intelligence report.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text

from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Default RSS feeds if none provided
DEFAULT_FEEDS: List[str] = [
    "https://feeds.feedburner.com/TechCrunch",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
]

# Timeout for HTTP requests (seconds)
HTTP_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_url(url: str, timeout: float = HTTP_TIMEOUT) -> Optional[str]:
    """Fetch a URL and return its text content, or None on failure."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True,
            headers={"User-Agent": "SanaaAI-MarketIntel/1.0"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning(f"[MarketIntel] Failed to fetch {url}: {exc}")
        return None


def _parse_rss(xml_text: str) -> List[Dict[str, str]]:
    """Parse RSS/Atom XML and extract items as dicts with title, link, summary, source."""
    items: List[Dict[str, str]] = []

    # Use lxml-xml parser to correctly handle RSS/Atom XML (html.parser
    # treats <link> as self-closing void element and loses its text content).
    try:
        soup = BeautifulSoup(xml_text, "xml")
    except Exception:
        # Fallback to html.parser if lxml is not installed
        soup = BeautifulSoup(xml_text, "html.parser")

    # Try RSS 2.0 <item> elements first
    for item in soup.find_all("item"):
        title = item.find("title")
        link = item.find("link")
        desc = item.find("description")
        source_el = item.find("source")
        items.append({
            "title": title.get_text(strip=True) if title else "",
            "link": link.get_text(strip=True) if link else "",
            "summary": (desc.get_text(strip=True)[:500] if desc else ""),
            "source": (source_el.get_text(strip=True) if source_el else "rss"),
        })

    # Fallback: Atom <entry> elements
    if not items:
        for entry in soup.find_all("entry"):
            title = entry.find("title")
            link_el = entry.find("link")
            summary = entry.find("summary") or entry.find("content")
            items.append({
                "title": title.get_text(strip=True) if title else "",
                "link": link_el.get("href", "") if link_el else "",
                "summary": (summary.get_text(strip=True)[:500] if summary else ""),
                "source": "atom",
            })

    return items


def _hash_content(text: str) -> str:
    """SHA-256 hash of textual content for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_page_text(html: str) -> str:
    """Extract visible text from HTML, stripping scripts and styles."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:5000]


# ---------------------------------------------------------------------------
# Signal storage
# ---------------------------------------------------------------------------

async def _store_signal(
    title: str,
    link: str = "",
    source: str = "",
    summary: str = "",
    classification: str = "market_signal",
    score: int = 50,
    business_impact: str = "",
) -> None:
    """Persist a strategic signal to the strategic_signals table."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    """INSERT INTO strategic_signals
                       (title, link, source, summary, classification, score,
                        business_impact, created_at)
                       VALUES (:title, :link, :source, :summary, :classification,
                               :score, :business_impact, :created_at)"""
                ),
                {
                    "title": title,
                    "link": link,
                    "source": source,
                    "summary": summary,
                    "classification": classification,
                    "score": score,
                    "business_impact": business_impact,
                    "created_at": datetime.now(timezone.utc),
                },
            )
            await session.commit()
    except Exception as exc:
        logger.error(f"[MarketIntel] Failed to store signal: {exc}")


# ---------------------------------------------------------------------------
# Skill class
# ---------------------------------------------------------------------------

class MarketIntelligenceSkill(BaseSkill):
    """Market intelligence: scan feeds, analyse trends, watch competitors, report."""

    name = "market_intelligence"
    description = (
        "Market intelligence: aggregate signals from RSS/web sources, "
        "analyse market trends via LLM, monitor competitor URLs for changes, "
        "and generate structured market intelligence reports."
    )
    version = "1.0.0"
    permissions = ["network"]
    tags = ["market-intelligence", "research", "competitors", "trends", "analysis"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "scan_market":
            return await self._scan_market(args, context)
        elif action == "analyze_trends":
            return await self._analyze_trends(args, context)
        elif action == "competitor_watch":
            return await self._competitor_watch(args, context)
        elif action == "report":
            return await self._report(args, context)

        return SkillResult(
            success=False,
            error=(
                f"Unknown action: {action}. "
                "Valid actions: scan_market, analyze_trends, competitor_watch, report"
            ),
        )

    # ------------------------------------------------------------------
    # scan_market
    # ------------------------------------------------------------------
    async def _scan_market(self, args: dict, context: SkillContext) -> SkillResult:
        """Aggregate signals from configured RSS feeds and web sources."""
        feeds = args.get("feeds") or DEFAULT_FEEDS

        if not isinstance(feeds, list) or len(feeds) == 0:
            return SkillResult(
                success=False,
                error="Parameter 'feeds' must be a non-empty list of RSS feed URLs.",
            )

        all_signals: List[Dict[str, str]] = []
        feed_errors: List[str] = []

        for feed_url in feeds:
            xml_text = await _fetch_url(feed_url)
            if xml_text is None:
                feed_errors.append(feed_url)
                continue
            items = _parse_rss(xml_text)
            for item in items:
                item["feed_url"] = feed_url
            all_signals.extend(items)

        # Store each signal in strategic_signals
        stored = 0
        for sig in all_signals:
            await _store_signal(
                title=sig.get("title", "Untitled"),
                link=sig.get("link", ""),
                source=sig.get("source", "rss"),
                summary=sig.get("summary", ""),
                classification="market_signal",
                score=50,
            )
            stored += 1

        output_lines = [
            f"📡 Market Scan Complete",
            f"Feeds processed: {len(feeds) - len(feed_errors)}/{len(feeds)}",
            f"Signals collected: {len(all_signals)}",
            f"Signals stored: {stored}",
        ]
        if feed_errors:
            output_lines.append(f"Failed feeds: {', '.join(feed_errors)}")

        if all_signals:
            output_lines.append("")
            output_lines.append("Top signals:")
            for sig in all_signals[:5]:
                output_lines.append(f"  • {sig['title'][:100]}")

        return SkillResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "total_signals": len(all_signals),
                "stored": stored,
                "feeds_processed": len(feeds) - len(feed_errors),
                "feeds_total": len(feeds),
                "feed_errors": feed_errors,
                "signals": all_signals[:20],  # cap for payload size
            },
        )

    # ------------------------------------------------------------------
    # analyze_trends
    # ------------------------------------------------------------------
    async def _analyze_trends(self, args: dict, context: SkillContext) -> SkillResult:
        """Use Brain/LLM to identify trends, opportunities, and threats."""
        topic = args.get("topic", "general market")

        if not context.brain:
            return SkillResult(
                success=False,
                error="Brain engine not available for trend analysis.",
            )

        # Fetch recent signals from DB for analysis context
        recent_signals: List[Dict[str, Any]] = []
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text(
                        """SELECT title, summary, source, classification, score
                           FROM strategic_signals
                           ORDER BY created_at DESC
                           LIMIT 30"""
                    )
                )
                rows = result.mappings().all()
                recent_signals = [dict(r) for r in rows]
        except Exception as exc:
            logger.warning(f"[MarketIntel] Could not load recent signals: {exc}")

        signals_context = ""
        if recent_signals:
            signals_context = "\n".join(
                f"- {s['title']}: {(s.get('summary') or '')[:200]}"
                for s in recent_signals
            )
        else:
            signals_context = "(No recent signals available — generating analysis from general knowledge.)"

        prompt = (
            f"You are a senior market analyst. Analyse the following market signals "
            f"related to '{topic}' and produce a structured analysis.\n\n"
            f"SIGNALS:\n{signals_context}\n\n"
            "Respond with the following sections:\n"
            "## Key Trends\n"
            "## Opportunities\n"
            "## Threats\n"
            "## Recommended Actions\n\n"
            "Be specific and actionable. Reference the signals where possible."
        )

        try:
            analysis = await context.brain.think(
                prompt, complexity="balanced", channel="market_intelligence",
            )
        except Exception as exc:
            logger.error(f"[MarketIntel] LLM analysis failed: {exc}")
            return SkillResult(success=False, error=f"Trend analysis failed: {exc}")

        if not analysis:
            return SkillResult(success=False, error="LLM returned empty analysis.")

        # Store a summary signal for the analysis itself
        await _store_signal(
            title=f"Trend Analysis: {topic}",
            source="llm_analysis",
            summary=analysis[:500],
            classification="trend_analysis",
            score=70,
        )

        return SkillResult(
            success=True,
            output=analysis,
            data={
                "topic": topic,
                "signals_analysed": len(recent_signals),
                "analysis": analysis,
            },
        )

    # ------------------------------------------------------------------
    # competitor_watch
    # ------------------------------------------------------------------
    async def _competitor_watch(self, args: dict, context: SkillContext) -> SkillResult:
        """Monitor competitor URLs for content changes via hashing."""
        urls = args.get("urls")
        if not urls or not isinstance(urls, list) or len(urls) == 0:
            return SkillResult(
                success=False,
                error="Parameter 'urls' is required and must be a non-empty list of URLs.",
            )

        results: List[Dict[str, Any]] = []

        for url in urls:
            html = await _fetch_url(url)
            if html is None:
                results.append({"url": url, "status": "error", "changed": False})
                continue

            page_text = _extract_page_text(html)
            new_hash = _hash_content(page_text)

            # Check for previous hash in strategic_signals
            previous_hash: Optional[str] = None
            try:
                async with AsyncSessionLocal() as session:
                    row = await session.execute(
                        text(
                            """SELECT business_impact FROM strategic_signals
                               WHERE link = :url AND classification = 'competitor_hash'
                               ORDER BY created_at DESC LIMIT 1"""
                        ),
                        {"url": url},
                    )
                    existing = row.mappings().first()
                    if existing:
                        previous_hash = existing["business_impact"]
            except Exception as exc:
                logger.warning(f"[MarketIntel] Could not fetch previous hash for {url}: {exc}")

            changed = previous_hash is not None and previous_hash != new_hash
            is_new = previous_hash is None

            # Store the new hash
            await _store_signal(
                title=f"Competitor Watch: {url[:80]}",
                link=url,
                source="competitor_watch",
                summary=page_text[:300],
                classification="competitor_hash",
                score=60 if changed else 40,
                business_impact=new_hash,
            )

            results.append({
                "url": url,
                "status": "changed" if changed else ("new" if is_new else "unchanged"),
                "changed": changed,
                "hash": new_hash[:16],
            })

        changed_count = sum(1 for r in results if r["changed"])
        new_count = sum(1 for r in results if r["status"] == "new")
        error_count = sum(1 for r in results if r["status"] == "error")

        output_lines = [
            "🔍 Competitor Watch Complete",
            f"URLs monitored: {len(urls)}",
            f"Changes detected: {changed_count}",
            f"New entries: {new_count}",
        ]
        if error_count:
            output_lines.append(f"Errors: {error_count}")

        output_lines.append("")
        for r in results:
            icon = "🔴" if r["changed"] else ("🆕" if r["status"] == "new" else ("⚠️" if r["status"] == "error" else "🟢"))
            output_lines.append(f"  {icon} {r['url'][:60]} — {r['status']}")

        return SkillResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "urls_monitored": len(urls),
                "changes_detected": changed_count,
                "new_entries": new_count,
                "errors": error_count,
                "results": results,
            },
        )

    # ------------------------------------------------------------------
    # report
    # ------------------------------------------------------------------
    async def _report(self, args: dict, context: SkillContext) -> SkillResult:
        """Generate a structured market intelligence report."""
        topic = args.get("topic", "general market")
        timeframe = args.get("timeframe", "weekly")

        if not context.brain:
            return SkillResult(
                success=False,
                error="Brain engine not available for report generation.",
            )

        # Gather recent signals from DB
        signals: List[Dict[str, Any]] = []
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text(
                        """SELECT title, link, source, summary, classification,
                                  score, business_impact, created_at
                           FROM strategic_signals
                           ORDER BY created_at DESC
                           LIMIT 50"""
                    )
                )
                rows = result.mappings().all()
                signals = [dict(r) for r in rows]
        except Exception as exc:
            logger.warning(f"[MarketIntel] Could not load signals for report: {exc}")

        # Build a concise signal digest
        signal_digest = ""
        if signals:
            digest_lines = []
            for s in signals[:30]:
                digest_lines.append(
                    f"- [{s.get('classification', 'signal')}] {s['title']}: "
                    f"{(s.get('summary') or '')[:150]}"
                )
            signal_digest = "\n".join(digest_lines)
        else:
            signal_digest = "(No signals available yet — produce general analysis.)"

        prompt = (
            f"You are a senior market intelligence analyst. Produce a {timeframe} "
            f"market intelligence report focused on '{topic}'.\n\n"
            f"SIGNAL DATA:\n{signal_digest}\n\n"
            "Structure the report as follows:\n"
            "# Market Intelligence Report\n"
            f"**Period:** {timeframe}\n"
            f"**Focus:** {topic}\n\n"
            "## Executive Summary\n"
            "## Market Signals Overview\n"
            "## Competitor Activity\n"
            "## Trend Analysis\n"
            "## Opportunities\n"
            "## Threats & Risks\n"
            "## Recommendations\n\n"
            "Be data-driven, reference specific signals, and provide actionable "
            "recommendations."
        )

        try:
            report_text = await context.brain.think(
                prompt, complexity="powerful", channel="market_intelligence",
            )
        except Exception as exc:
            logger.error(f"[MarketIntel] Report generation failed: {exc}")
            return SkillResult(success=False, error=f"Report generation failed: {exc}")

        if not report_text:
            return SkillResult(success=False, error="LLM returned empty report.")

        # Store report as a signal
        await _store_signal(
            title=f"Market Intelligence Report: {topic} ({timeframe})",
            source="market_report",
            summary=report_text[:500],
            classification="market_report",
            score=80,
        )

        return SkillResult(
            success=True,
            output=report_text,
            data={
                "topic": topic,
                "timeframe": timeframe,
                "signals_used": len(signals),
                "report": report_text,
            },
        )


# Register entry point
handler = MarketIntelligenceSkill
