import os
import re
import json
import html
import httpx
import feedparser
import asyncio
import logging
import smtplib
import hashlib
from collections import Counter
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from core.brain import get_shared_brain
from core.config import get_settings
from core.intelligence.memory import IntelligenceMemory
from core.intelligence.persistence import archive_briefing, attach_pdf_to_latest_briefing
from core.database import SystemKnowledge

logger = logging.getLogger(__name__)

# Keywords for rule-based relevance filtering (saves LLM tokens)
HIGH_SIGNAL_KEYWORDS = {
    "trade", "tariff", "agoa", "eac", "comesa", "tax", "budget", "fiscal",
    "tender", "procurement", "contract", "grant", "loan", "imf", "world bank",
    "oil", "gas", "eacop", "pipeline", "mining", "mineral", "gold", "lithium",
    "energy", "solar", "renewable", "electricity", "power", "grid",
    "infrastructure", "road", "railway", "sgr", "port", "airport",
    "policy", "regulation", "bill", "parliament", "cabinet", "president",
    "investment", "fdi", "ipo", "stock", "exchange", "bond", "interest rate",
    "inflation", "gdp", "growth", "recession", "deficit", "debt",
    "uganda", "kenya", "tanzania", "rwanda", "burundi", "south sudan",
    "kampala", "nairobi", "dar es salaam", "kigali", "east africa",
    "export", "import", "customs", "logistics", "shipping", "freight",
    "agriculture", "coffee", "tea", "cotton", "maize", "food security",
    "fintech", "mobile money", "digital", "startup", "venture capital",
    "bank", "central bank", "forex", "currency", "shilling",
}

IRRELEVANT_NEWS_KEYWORDS = {
    "horse racing", "bettors", "derby", "football", "soccer", "premier league",
    "transfer window", "celebrity", "entertainment", "gossip", "wedding",
    "agm today", "alumni", "lifestyle", "fashion", "movie", "music", "sports",
}


class NewsEvent:
    """Structured event logging for independent audit trails (OpenClaw Pattern)."""
    def __init__(self, category: str, severity: str, message: str, metadata: dict = None):
        self.id = hashlib.md5(f"{category}:{message}:{datetime.now()}".encode()).hexdigest()[:8]
        self.category = category
        self.severity = severity
        self.message = message
        self.metadata = metadata or {}
        self.timestamp = datetime.now()

    def log(self):
        log_msg = f"[{self.category.upper()}][{self.severity.upper()}] {self.message}"
        if self.metadata:
            log_msg += f" | Metadata: {self.metadata}"
        if self.severity == "error":
            logger.error(log_msg)
        elif self.severity == "warning":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)


class NewsAgent:
    def __init__(self, brain=None):
        self.settings = get_settings()
        self.brain = brain or get_shared_brain()
        self.memory = IntelligenceMemory()
        self.feeds = {
            "Finance": [
                "https://www.marketwatch.com/rss/topstories",
                "https://www.forbes.com/business/feed/",
                "https://search.cnbc.com/rs/search/all/rss.xml?query=finance"
            ],
            "Ecommerce": [
                "https://www.retaildive.com/feeds/news/",
                "https://www.ecommercebytes.com/feed/"
            ],
            "Uganda/EAC": [
                "https://nilepost.co.ug/feed/",
                "https://www.independent.co.ug/feed/",
                "https://chimpreports.com/feed/"
            ]
        }

    @staticmethod
    def _pref_enabled(value, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}

    @staticmethod
    def _normalize_recipients(value) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            raw_items = value
        else:
            raw_items = str(value).split(",")
        return [str(item).strip() for item in raw_items if str(item).strip()]

    async def fetch_feed(self, url: str):
        """Fetch and parse an RSS feed."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return feedparser.parse(response.text)
        except Exception as e:
            logger.warning(f"Failed to fetch feed {url}: {e}")
        return None

    async def _fetch_source(self, sector: str, url: str) -> list:
        """Fetch articles from a single source with watchdog-style logging."""
        try:
            feed = await self.fetch_feed(url)
            if feed and feed.entries:
                publication = self._derive_publication(url)
                articles = []
                for entry in feed.entries[:10]:
                    articles.append({
                        "title": entry.title,
                        "link": entry.link,
                        "summary": getattr(entry, 'summary', '')[:400],
                        "source": sector,
                        "publication": publication,
                    })
                NewsEvent("ingestion", "info", f"Fetched {len(articles)} articles from {url}", {"sector": sector}).log()
                return articles
            else:
                NewsEvent("ingestion", "warning", f"No entries or failed to parse feed from {url}", {"sector": sector}).log()
                return []
        except Exception as e:
            NewsEvent("ingestion", "error", f"Error fetching source {url}: {e}", {"sector": sector}).log()
            return []

    def _derive_publication(self, url: str) -> str:
        host = urlparse(url).netloc.lower()
        host = host.replace("www.", "").replace("feeds.", "").replace("search.", "")
        parts = [part for part in host.split(".") if part and part not in {"co", "com", "ug", "org", "net", "rss", "xml"}]
        if not parts:
            return "Unknown"
        return " ".join(part.capitalize() for part in parts[:2])

    def _keyword_relevance_score(self, article: dict) -> int:
        """Fast rule-based relevance scoring — zero LLM tokens used."""
        text = f"{article['title']} {article.get('summary', '')}".lower()
        hits = sum(1 for kw in HIGH_SIGNAL_KEYWORDS if kw in text)
        penalties = sum(1 for kw in IRRELEVANT_NEWS_KEYWORDS if kw in text)
        # Uganda/EAC articles get automatic boost
        if article.get("source") == "Uganda/EAC" and hits > 0:
            hits += 3
        if any(country in text for country in ("uganda", "kenya", "rwanda", "tanzania", "burundi", "south sudan", "east africa")):
            hits += 2
        if penalties and hits < 4:
            hits -= penalties * 2
        return max(0, min(hits, 10))

    def _is_editorially_relevant(self, article: dict) -> bool:
        text = f"{article['title']} {article.get('summary', '')}".lower()
        if any(kw in text for kw in IRRELEVANT_NEWS_KEYWORDS) and article.get("score", 0) < 5:
            return False
        return article.get("score", 0) >= 3

    def _select_balanced_articles(self, articles: list[dict], limit: int = 18) -> list[dict]:
        selected = []
        publication_counts: Counter[str] = Counter()
        sector_counts: Counter[str] = Counter()

        for article in articles:
            publication = article.get("publication", "Unknown")
            sector = article.get("source", "General")

            if not self._is_editorially_relevant(article):
                continue
            if publication_counts[publication] >= 4:
                continue
            if sector_counts[sector] >= 6 and len(selected) < 12:
                continue

            selected.append(article)
            publication_counts[publication] += 1
            sector_counts[sector] += 1

            if len(selected) >= limit:
                break

        if len(selected) < min(limit, 10):
            for article in articles:
                if article in selected or article.get("score", 0) < 2:
                    continue
                selected.append(article)
                if len(selected) >= limit:
                    break

        return selected

    async def get_daily_summary(self, topics=None):
        """Aggregate news and summarize — token-efficient single-pass approach."""
        if topics is None:
            topics = self.feeds.keys()

        # === INGESTION ===
        NewsEvent("ingestion", "info", f"Starting aggregation for {len(self.feeds)} sectors").log()
        fetch_tasks = []
        for sector, urls in self.feeds.items():
            for url in urls:
                fetch_tasks.append(self._fetch_source(sector, url))

        raw_results = await asyncio.gather(*fetch_tasks)

        all_articles = []
        for res in raw_results:
            if isinstance(res, list):
                all_articles.extend(res)

        # === DEDUPLICATION ===
        seen_slugs = set()
        unique_articles = []
        for a in all_articles:
            slug = re.sub(r'[^a-zA-Z0-9]', '', a["title"].lower())
            if slug not in seen_slugs and len(slug) > 10:
                seen_slugs.add(slug)
                unique_articles.append(a)

        NewsEvent("ingestion", "info", f"Aggregated {len(unique_articles)} unique articles").log()

        if not unique_articles:
            return "No news aggregated (Check feed URLs or connectivity)."

        # === KEYWORD FILTERING (replaces LLM batch scoring — saves ~4 API calls) ===
        for a in unique_articles:
            a["score"] = self._keyword_relevance_score(a)

        # Sort by score, then rebalance so one publisher or weak category does not dominate
        unique_articles.sort(key=lambda x: x["score"], reverse=True)
        filtered_news = self._select_balanced_articles(unique_articles, limit=18)
        if not filtered_news:
            filtered_news = unique_articles[:15]

        NewsEvent("analysis", "info", f"Keyword-filtered to {len(filtered_news)} high-signal articles").log()

        # === GROUP BY SECTOR ===
        all_news = {}
        for art in filtered_news:
            source = art["source"]
            if source not in all_news:
                all_news[source] = []
            all_news[source].append(art)

        # === TIER 3 SYNTHESIS (single LLM call — all token budget here) ===
        NewsEvent("synthesis", "info", f"Starting synthesis for {len(filtered_news)} articles").log()

        # Keep DATA compact — only title, link, summary, source
        compact_data = {}
        for sector, arts in all_news.items():
            compact_data[sector] = [
                {
                    "title": a["title"],
                    "link": a["link"],
                    "summary": a.get("summary", "")[:220],
                    "publication": a.get("publication", "Unknown"),
                    "score": a.get("score", 0),
                }
                for a in arts
            ]

        prompt = f"""You are the Chief Editor of Sanaa Media Intelligence — an executive daily briefing for East African decision-makers.

AUDIENCE: Entrepreneurs, Traders, Government Officials, Investors in Uganda/EAC.
FOCUS: Finance, Policy, Infrastructure, Trade, Tax, Mining, Energy, Agriculture.
TONE: Analytical, Executive, Neutral. No fluff. No marketing speak.
EDITORIAL RULES:
- Exclude soft human-interest, celebrity, sports, alumni-event, and generic crime stories unless they have direct policy, trade, fiscal, or investment relevance.
- Prioritize East Africa impact first, then relevant global developments that materially affect East Africa.
- Keep the briefing balanced across markets, policy, infrastructure, trade, and enterprise. Do not let one publisher or one country dominate the narrative without cause.
- Order the stories so the reader feels momentum: start with the strongest macro/regional signals, move into sector and company implications, end with opportunity watch.
- Write with discipline and curiosity, not hype. The goal is to keep an executive reading to the end because the flow is sharp and useful.

STRICT OUTPUT FORMAT (use these exact markdown headers):

## TOP STRATEGIC SIGNALS
- Signal 1: [one-line macro insight]
- Signal 2: [one-line macro insight]
- Signal 3: [one-line macro insight]

## READER'S GUIDE
- [1 sentence on what to expect first]
- [1 sentence on why this matters today]

### FINANCE & MARKETS
**Headline:** [Story title]
**What Happened:** [2-3 sentences of facts]
**Why It Matters:** [Business/strategic impact for East Africa]
**Signal Level:** High/Medium/Low
**Source:** [Use the publication field exactly]

### UGANDA/EAC
**Headline:** [Story title]
**What Happened:** [2-3 sentences of facts]
**Why It Matters:** [Business/strategic impact]
**Signal Level:** High/Medium/Low
**Source:** [Use the publication field exactly]

(Repeat for each major story across categories. Group related stories. Merge similar headlines instead of repeating near-duplicates.)

## Opportunity Watch
- [Specific tender, grant, policy opening, or business opportunity with link if available]

## WHATSAPP VERSION
(Write a concise WhatsApp-ready summary, 5 bullets max, 700-900 characters. Start with one strong top-line hook, then bullets with headline + impact, and end with one line inviting the reader to open the PDF/email for the full briefing. Format for mobile reading.)

NEWS DATA:
{json.dumps(compact_data, indent=1)}
"""

        summary = None
        try:
            summary = await self.brain.think(prompt, complexity="high")
            if not summary or len(summary.strip()) < 150:
                logger.warning("LLM synthesis too short or empty, triggering fallback")
                summary = None
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")

        # If synthesis failed, use structured fallback
        if not summary:
            summary = self._generate_fallback_summary(all_news)

        # === LINK VERIFICATION (concurrent, with timeout) ===
        try:
            summary = await asyncio.wait_for(self._verify_links(summary), timeout=30)
        except asyncio.TimeoutError:
            NewsEvent("delivery", "warning", "Link verification timed out, skipping").log()

        # === ARCHIVE ===
        try:
            signals = self._extract_signals_from_text(summary)
            briefing_title = f"Daily Briefing - {datetime.now().strftime('%Y-%m-%d')}"
            await archive_briefing(
                title=briefing_title,
                content=summary,
                signals=signals,
                metadata={"article_count": len(filtered_news), "topics": list(all_news.keys())}
            )
        except Exception as e:
            logger.warning(f"Failed to archive briefing: {e}")

        return summary

    def _extract_signals_from_text(self, summary: str) -> list:
        """Extract signals from summary text using regex — no LLM needed."""
        signals = []
        # Find signal lines after "TOP STRATEGIC SIGNALS"
        sig_match = re.search(r'#{2,3}\s*TOP STRATEGIC SIGNALS(.*?)(?=^#{2,3}\s|\Z)', summary, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        if sig_match:
            for line in sig_match.group(1).strip().split('\n'):
                line = line.strip().lstrip('- *')
                if len(line) > 10:
                    signals.append({
                        "title": line[:120],
                        "summary": line,
                        "score": 8,
                        "classification": "Signal",
                        "tags": ["daily-briefing"]
                    })
        return signals

    def _extract_whatsapp_version(self, summary: str) -> str:
        """Extract the WHATSAPP VERSION section from the briefing."""
        match = re.search(r'#{2,3}\s*WHATSAPP VERSION\s*\n(.*?)(?=^#{2,3}\s|\Z)', summary, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        if match:
            wa_text = match.group(1).strip()
            # Clean markdown formatting for plain text WhatsApp
            wa_text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', wa_text)  # bold → WhatsApp bold
            wa_text = re.sub(r'\[(.*?)\]\((.*?)\)', r'\1: \2', wa_text)  # links → text: url
            if len(wa_text) > 50:
                return wa_text[:1200]
        return ""

    async def _verify_links(self, text: str) -> str:
        """Verify URLs in text concurrently."""
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
        # Deduplicate and limit to avoid excessive requests
        unique_urls = list(dict.fromkeys(urls))[:15]

        async def check_url(url):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.head(url, follow_redirects=True)
                    return url, resp.status_code < 400
            except Exception:
                return url, False

        results = await asyncio.gather(*[check_url(u) for u in unique_urls], return_exceptions=True)

        for result in results:
            if isinstance(result, tuple):
                url, valid = result
                if valid:
                    text = text.replace(url, f"{url}")
                else:
                    text = text.replace(url, f"{url} [Link Unverified]")
        return text

    def _generate_fallback_summary(self, all_news: dict) -> str:
        """Structured fallback when LLM is unavailable — still professional."""
        date_str = datetime.now().strftime('%A, %B %d, %Y')
        lines = [f"## TOP STRATEGIC SIGNALS", ""]

        # Generate basic signals from top articles
        all_arts = []
        for articles in all_news.values():
            all_arts.extend(articles)
        all_arts.sort(key=lambda x: x.get("score", 0), reverse=True)
        top = all_arts[:3]
        for i, art in enumerate(top, 1):
            lines.append(f"- Signal {i}: {art['title']}")
        lines.append("")

        # Categorized stories
        for sector, articles in all_news.items():
            if not articles:
                continue
            lines.append(f"### {sector.upper()}")
            for art in articles[:5]:
                lines.append(f"**Headline:** {art['title']}")
                if art.get('summary'):
                    # Strip HTML from summary
                    clean_summary = re.sub(r'<[^>]+>', '', art['summary'])[:200]
                    lines.append(f"**What Happened:** {clean_summary}")
                lines.append("**Why It Matters:** Relevant because it affects business, policy, trade, or investor decisions tied to East Africa.")
                score = art.get('score', 5)
                level = "High" if score >= 7 else "Medium" if score >= 4 else "Low"
                lines.append(f"**Signal Level:** {level}")
                lines.append(f"**Source:** {art.get('publication', 'Unknown')} ({art['link']})")
                lines.append("")

        # Opportunity Watch placeholder
        lines.append("## Opportunity Watch")
        lines.append("- Review individual stories above for specific opportunities, tenders, and policy developments.")
        lines.append("")

        # WhatsApp version
        lines.append("## WHATSAPP VERSION")
        lines.append(f"*Sanaa Intelligence Daily - {date_str}*")
        lines.append("")
        for art in all_arts[:5]:
            lines.append(f"- {art['title']} - Impact: worth tracking for East Africa business or policy readers.")
        lines.append("")
        lines.append("Open the full PDF in your email for the complete briefing and links.")

        return "\n".join(lines)

    async def generate_pdf(self, summary: str, filename: str = None):
        if not filename:
            filename = f"Sanaa_Media_News_{datetime.now().strftime('%Y_%m_%d')}.pdf"
        filepath = os.path.join("/var/www/ai.sanaa.co/data/news", filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        # Strip WhatsApp section from PDF — it's for mobile delivery only
        pdf_summary = re.sub(r'##\s*WHATSAPP VERSION.*', '', summary, flags=re.DOTALL | re.IGNORECASE).strip()
        html_body = self._format_summary_to_html(pdf_summary)
        full_html = self._get_html_template(html_body)
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.set_content(full_html)
                await page.pdf(
                    path=filepath,
                    format="A4",
                    print_background=True,
                    prefer_css_page_size=True,
                    margin={"top": "14mm", "right": "12mm", "bottom": "14mm", "left": "12mm"},
                )
                await browser.close()
            return filepath
        except Exception as e:
            logger.error(f"PDF failed: {e}")
            return None

    def _format_summary_to_html(self, summary: str) -> str:
        """Convert the briefing markdown into structured executive HTML."""
        strategic_signals = self._extract_markdown_section(summary, "TOP STRATEGIC SIGNALS")
        opportunities = self._extract_markdown_section(summary, "Opportunity Watch")
        story_sections = self._parse_story_sections(summary)

        parts = []

        if strategic_signals:
            signal_cards = []
            for idx, line in enumerate(re.findall(r'^\s*[-*]\s+(.*)$', strategic_signals, re.MULTILINE), start=1):
                signal_cards.append(
                    f"""
                    <div class="signal-card">
                        <div class="eyebrow">Signal {idx}</div>
                        <h3>{self._render_inline_text(line.strip())}</h3>
                    </div>
                    """
                )

            if signal_cards:
                parts.append(
                    f"""
                    <section class="section-block">
                        <div class="section-header">
                            <span class="section-tag primary">Top Strategic Signals</span>
                            <h2>What executives should notice first</h2>
                        </div>
                        <div class="signal-grid">
                            {''.join(signal_cards)}
                        </div>
                    </section>
                    """
                )

        if story_sections:
            rendered_sections = []
            for section in story_sections:
                story_cards = []
                for story in section["stories"]:
                    story_cards.append(
                        f"""
                        <article class="story-card">
                            <div class="story-header">
                                <div>
                                    <h3>{self._render_inline_text(story.get('headline', 'Untitled'))}</h3>
                                </div>
                                {self._render_signal_level_badge(story.get('signal_level', ''))}
                            </div>
                            <div class="story-copy">
                                <p><strong>What Happened</strong><br>{self._render_inline_text(story.get('what_happened', 'Not provided.'))}</p>
                                <p><strong>Why It Matters</strong><br>{self._render_inline_text(story.get('why_it_matters', 'Not provided.'))}</p>
                            </div>
                            <div class="story-source">
                                <span>Source</span>
                                <div>{self._render_inline_text(story.get('source', 'Unknown source'))}</div>
                            </div>
                        </article>
                        """
                    )

                rendered_sections.append(
                    f"""
                    <section class="section-block">
                        <div class="section-header">
                            <span class="section-tag secondary">{html.escape(section['title'])}</span>
                            <h2>{html.escape(section['title'])}</h2>
                        </div>
                        <div class="story-stack">
                            {''.join(story_cards)}
                        </div>
                    </section>
                    """
                )

            parts.append("".join(rendered_sections))

        if opportunities:
            opportunity_items = [
                f"<li>{self._render_inline_text(item.strip())}</li>"
                for item in re.findall(r'^\s*[-*]\s+(.*)$', opportunities, re.MULTILINE)
                if item.strip()
            ]
            if opportunity_items:
                parts.append(
                    f"""
                    <section class="section-block">
                        <div class="section-header">
                            <span class="section-tag success">Opportunity Watch</span>
                            <h2>Openings worth immediate follow-up</h2>
                        </div>
                        <div class="opportunity-panel">
                            <ul>
                                {''.join(opportunity_items)}
                            </ul>
                        </div>
                    </section>
                    """
                )

        if not parts:
            return self._render_fallback_body_html(summary)

        return "".join(parts)

    def _extract_markdown_section(self, summary: str, title: str) -> str:
        match = re.search(
            rf'^#{{2,3}}\s*{re.escape(title)}\s*(.*?)(?=^#{{2,3}}\s|\Z)',
            summary,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        return match.group(1).strip() if match else ""

    def _parse_story_sections(self, summary: str) -> list[dict]:
        section_matches = list(re.finditer(r'^###\s+(.+)$', summary, re.MULTILINE))
        parsed_sections: list[dict] = []
        section_index: dict[str, dict] = {}

        for match in section_matches:
            title = match.group(1).strip()
            normalized_title = title.upper()
            if normalized_title in {"TOP STRATEGIC SIGNALS", "WHATSAPP VERSION", "OPPORTUNITY WATCH", "READER'S GUIDE"}:
                continue
            tail = summary[match.end():]
            next_heading = re.search(r'^(?:###|##)\s+', tail, re.MULTILINE)
            end_offset = match.end() + next_heading.start() if next_heading else len(summary)
            block = summary[match.end():end_offset].strip()
            stories = self._parse_story_items(block)

            if stories:
                existing = section_index.get(normalized_title)
                if existing:
                    existing["stories"].extend(stories)
                else:
                    item = {"title": title, "stories": stories}
                    parsed_sections.append(item)
                    section_index[normalized_title] = item

        return parsed_sections

    def _parse_story_items(self, block: str) -> list[dict]:
        items = []
        chunks = re.split(r'(?=\*\*Headline:\*\*)', block)

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk.startswith("**Headline:**"):
                continue

            items.append(
                {
                    "headline": self._extract_story_field(chunk, "Headline"),
                    "what_happened": self._extract_story_field(chunk, "What Happened"),
                    "why_it_matters": self._extract_story_field(chunk, "Why It Matters"),
                    "signal_level": self._extract_story_field(chunk, "Signal Level"),
                    "source": self._extract_story_field(chunk, "Source"),
                }
            )

        return items

    def _extract_story_field(self, block: str, label: str) -> str:
        match = re.search(
            rf'\*\*{re.escape(label)}:\*\*\s*(.*?)(?=(?:\n\*\*[A-Za-z /&]+:\*\*|\Z))',
            block,
            flags=re.DOTALL,
        )
        return match.group(1).strip() if match else ""

    def _render_inline_text(self, text: str) -> str:
        safe = html.escape(text)
        safe = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{html.escape(m.group(1))}</a>',
            safe,
        )
        safe = re.sub(
            r'(?<!["\'])(https?://[^\s<]+)',
            lambda m: f'<a href="{html.escape(m.group(1), quote=True)}">{html.escape(m.group(1))}</a>',
            safe,
        )
        safe = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', safe)
        safe = re.sub(r'\*(.*?)\*', r'<em>\1</em>', safe)
        return safe.replace("\n", "<br>")

    def _render_signal_level_badge(self, level: str) -> str:
        normalized = (level or "").strip().lower()
        if normalized == "high":
            klass = "badge badge-high"
            label = "High signal"
        elif normalized == "medium":
            klass = "badge badge-medium"
            label = "Medium signal"
        else:
            klass = "badge badge-low"
            label = "Low signal"
        return f'<span class="{klass}">{label}</span>'

    def _render_fallback_body_html(self, summary: str) -> str:
        blocks = []
        for raw_line in summary.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("## "):
                blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
            elif line.startswith("### "):
                blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
            elif line.startswith(("- ", "* ")):
                blocks.append(f"<li>{self._render_inline_text(line[2:])}</li>")
            else:
                blocks.append(f"<p>{self._render_inline_text(line)}</p>")

        body = "".join(blocks)
        body = re.sub(r'((?:<li>.*?</li>)+)', r'<ul class="fallback-list">\1</ul>', body, flags=re.DOTALL)
        return f'<section class="section-block fallback-body">{body}</section>'

    def _get_html_template(self, body_content: str) -> str:
        date_str = datetime.now().strftime('%A, %B %d, %Y')
        year = datetime.now().year
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        @page {{ size: A4; margin: 14mm 12mm; }}
        :root {{
            --ink: #0f172a;
            --muted: #64748b;
            --line: #dbe3ef;
            --panel: #f8fbff;
            --panel-strong: #eef6ff;
            --brand: #2563eb;
            --brand-soft: #dbeafe;
            --teal: #0f766e;
            --teal-soft: #ccfbf1;
            --amber: #b45309;
            --amber-soft: #fef3c7;
            --rose: #b91c1c;
            --rose-soft: #fee2e2;
            --emerald: #047857;
            --emerald-soft: #dcfce7;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            background: #ffffff;
            color: var(--ink);
            font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            line-height: 1.6;
        }}
        .sheet {{
            max-width: 780px;
            margin: 0 auto;
        }}
        .hero {{
            position: relative;
            overflow: hidden;
            border-radius: 26px;
            padding: 30px 32px;
            background:
                radial-gradient(circle at top right, rgba(37, 99, 235, 0.16), transparent 28%),
                linear-gradient(135deg, #eff6ff 0%, #ffffff 52%, #f8fafc 100%);
            border: 1px solid #dbeafe;
        }}
        .hero::after {{
            content: "";
            position: absolute;
            right: -42px;
            top: -42px;
            width: 170px;
            height: 170px;
            border-radius: 50%;
            background: rgba(37, 99, 235, 0.08);
        }}
        .eyebrow {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 9999px;
            background: rgba(37, 99, 235, 0.08);
            border: 1px solid rgba(37, 99, 235, 0.16);
            color: var(--brand);
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.24em;
            text-transform: uppercase;
        }}
        .hero h1 {{
            margin: 16px 0 6px;
            font-size: 32px;
            line-height: 1.05;
            letter-spacing: -0.04em;
        }}
        .hero p {{
            margin: 0;
            color: var(--muted);
            font-size: 14px;
        }}
        .hero-meta {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-top: 18px;
        }}
        .meta-card {{
            min-width: 150px;
            padding: 12px 14px;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(148, 163, 184, 0.18);
        }}
        .meta-card .label {{
            color: var(--muted);
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.2em;
            text-transform: uppercase;
        }}
        .meta-card .value {{
            margin-top: 6px;
            font-size: 15px;
            font-weight: 700;
            color: var(--ink);
        }}
        .section-block {{
            margin-top: 28px;
        }}
        .section-header {{
            margin-bottom: 14px;
        }}
        .section-tag {{
            display: inline-block;
            padding: 5px 11px;
            border-radius: 9999px;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.22em;
            text-transform: uppercase;
        }}
        .section-tag.primary {{
            background: var(--brand-soft);
            color: var(--brand);
        }}
        .section-tag.secondary {{
            background: #ede9fe;
            color: #6d28d9;
        }}
        .section-tag.success {{
            background: var(--teal-soft);
            color: var(--teal);
        }}
        .section-header h2 {{
            margin: 10px 0 0;
            font-size: 22px;
            line-height: 1.2;
            letter-spacing: -0.03em;
        }}
        .signal-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
        }}
        .signal-card {{
            padding: 16px;
            border-radius: 20px;
            background: var(--panel);
            border: 1px solid #d7e6f8;
        }}
        .signal-card h3 {{
            margin: 10px 0 0;
            font-size: 15px;
            line-height: 1.5;
        }}
        .story-stack {{
            display: flex;
            flex-direction: column;
            gap: 14px;
        }}
        .story-card {{
            border-radius: 22px;
            padding: 18px;
            background: var(--panel);
            border: 1px solid var(--line);
        }}
        .story-header {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: flex-start;
        }}
        .story-label {{
            color: var(--muted);
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.2em;
            text-transform: uppercase;
        }}
        .story-header h3 {{
            margin: 8px 0 0;
            font-size: 18px;
            line-height: 1.35;
        }}
        .badge {{
            display: inline-block;
            white-space: nowrap;
            padding: 7px 11px;
            border-radius: 9999px;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.18em;
            text-transform: uppercase;
        }}
        .badge-high {{
            background: var(--rose-soft);
            color: var(--rose);
        }}
        .badge-medium {{
            background: var(--amber-soft);
            color: var(--amber);
        }}
        .badge-low {{
            background: var(--emerald-soft);
            color: var(--emerald);
        }}
        .story-copy {{
            margin-top: 16px;
            display: grid;
            gap: 12px;
        }}
        .story-copy p {{
            margin: 0;
            color: #334155;
            font-size: 14px;
        }}
        .story-copy strong {{
            color: var(--ink);
            display: inline-block;
            margin-bottom: 4px;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.18em;
            text-transform: uppercase;
        }}
        .story-source {{
            margin-top: 14px;
            padding-top: 14px;
            border-top: 1px solid #dbe3ef;
        }}
        .story-source span {{
            display: block;
            color: var(--muted);
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            margin-bottom: 5px;
        }}
        .story-source div {{
            font-size: 13px;
            color: #334155;
        }}
        .opportunity-panel {{
            border-radius: 22px;
            padding: 18px 20px;
            background: linear-gradient(180deg, #f0fdfa, #ffffff);
            border: 1px solid #bdeee6;
        }}
        .opportunity-panel ul,
        .fallback-list {{
            margin: 0;
            padding-left: 18px;
        }}
        .opportunity-panel li,
        .fallback-list li {{
            margin-bottom: 10px;
        }}
        .fallback-body h2 {{
            font-size: 20px;
            margin: 20px 0 10px;
        }}
        .fallback-body h3 {{
            font-size: 16px;
            margin: 18px 0 8px;
        }}
        p {{
            font-size: 14px;
            color: #334155;
        }}
        a {{
            color: var(--brand);
            text-decoration: underline;
        }}
        .footer {{
            margin-top: 34px;
            padding-top: 18px;
            border-top: 1px solid var(--line);
            display: flex;
            justify-content: space-between;
            gap: 12px;
            color: #94a3b8;
            font-size: 11px;
        }}
    </style>
</head>
<body>
    <div class="sheet">
        <div class="hero">
            <span class="eyebrow">Sanaa Media Intelligence</span>
            <h1>Executive Daily Briefing</h1>
            <p>Structured market and policy intelligence for East African decision-makers.</p>
            <div class="hero-meta">
                <div class="meta-card">
                    <div class="label">Edition Date</div>
                    <div class="value">{date_str}</div>
                </div>
                <div class="meta-card">
                    <div class="label">Format</div>
                    <div class="value">PDF Executive Briefing</div>
                </div>
                <div class="meta-card">
                    <div class="label">Distribution</div>
                    <div class="value">Confidential Internal Use</div>
                </div>
            </div>
        </div>
        <div>{body_content}</div>
        <div class="footer">
            <div>&copy; {year} Sanaa Media Group</div>
            <div>Confidential Intelligence Briefing</div>
        </div>
    </div>
</body>
</html>"""

    async def send_newsletter(self, summary: str = None, recipient: str = None):
        if summary is None:
            summary = await self.get_daily_summary()
        if not summary or len(summary.strip()) < 100:
            logger.error("No content to send")
            return False

        # === WHATSAPP DELIVERY ===
        wa_text = self._extract_whatsapp_version(summary)
        if wa_text:
            await self._send_whatsapp_briefing(wa_text)

        # === EMAIL DELIVERY ===
        try:
            subject = f"Sanaa Media Intelligence — {datetime.now().strftime('%b %d, %Y')}"

            # Fetch dedicated Sanaa Media recipients first, then fall back to legacy alert recipients.
            db_recipients = await SystemKnowledge.get_pref("news.email_recipients", default=None)
            if not db_recipients:
                db_recipients = await SystemKnowledge.get_pref("alert.recipients", default=None)

            recipients = self._normalize_recipients(db_recipients)
            if not recipients and recipient:
                recipients = self._normalize_recipients(recipient)
            if not recipients:
                recipients = self.settings.news_email_recipient_list or self.settings.alert_recipient_list

            if not recipients:
                NewsEvent("delivery", "warning", "No email recipients configured for Sanaa Media briefing").log()
                return False

            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = self.settings.smtp_from
            msg["To"] = ", ".join(recipients)

            # Strip WhatsApp section from email body
            email_summary = re.sub(r'##\s*WHATSAPP VERSION.*', '', summary, flags=re.DOTALL | re.IGNORECASE).strip()
            html_body = self._format_summary_to_html(email_summary)
            full_html = self._get_html_template(html_body)

            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(email_summary, "plain"))
            alt.attach(MIMEText(full_html, "html"))
            msg.attach(alt)

            pdf_enabled = self._pref_enabled(
                await SystemKnowledge.get_pref("news.pdf_enabled", default=True),
                default=True,
            )
            pdf_path = await self.generate_pdf(summary) if pdf_enabled else None
            if pdf_path and os.path.exists(pdf_path):
                pdf_public_path = f"/media-intelligence/pdf/{os.path.basename(pdf_path)}"
                await attach_pdf_to_latest_briefing(summary, pdf_public_path)
                with open(pdf_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(pdf_path)}")
                    msg.attach(part)

            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as server:
                server.starttls()
                server.login(self.settings.smtp_user, self.settings.smtp_pass)
                server.sendmail(self.settings.smtp_from, recipients, msg.as_string())

            NewsEvent("delivery", "info", f"Newsletter emailed to {len(recipients)} recipients").log()
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False

    async def _send_whatsapp_briefing(self, wa_text: str):
        """Send the WhatsApp version of the briefing via WhatsJet."""
        try:
            # Check if WhatsApp is enabled
            if not getattr(self.settings, 'whatsapp_saas_enabled', False):
                NewsEvent("delivery", "info", "WhatsApp delivery skipped (not enabled)").log()
                return

            news_whatsapp_enabled = self._pref_enabled(
                await SystemKnowledge.get_pref("news.whatsapp_enabled", default=True),
                default=True,
            )
            if not news_whatsapp_enabled:
                NewsEvent("delivery", "info", "WhatsApp delivery skipped (news preference disabled)").log()
                return

            # Get WhatsApp recipients from DB or settings
            wa_recipients = await SystemKnowledge.get_pref("news.whatsapp_recipients", default=None)
            if not wa_recipients:
                # Fallback: check settings for a default news WhatsApp number
                wa_recipients = self.settings.news_whatsapp_recipient_list

            if not wa_recipients:
                NewsEvent("delivery", "warning", "No WhatsApp recipients configured for news briefing").log()
                return

            wa_recipients = self._normalize_recipients(wa_recipients)

            from core.integrations.whatsapp_saas_manager import WhatsAppSaaSManager
            try:
                from core.routes import deps
                wa = deps.whatsapp_saas
            except Exception:
                wa = None

            if not wa:
                wa = WhatsAppSaaSManager(
                    source_path=self.settings.whatsapp_saas_source_path,
                    base_url=self.settings.whatsapp_saas_base_url,
                    vendor_uid=self.settings.whatsapp_saas_vendor_uid,
                    api_token=self.settings.whatsapp_saas_api_token,
                )

            date_str = datetime.now().strftime('%b %d, %Y')
            header = f"*SANAA INTELLIGENCE DAILY*\n_{date_str}_\n\n"
            full_message = header + wa_text

            sent = 0
            for phone in wa_recipients:
                try:
                    result = await wa.send_message(phone, full_message)
                    if result and result.get("success", True):
                        sent += 1
                except Exception as e:
                    NewsEvent("delivery", "warning", f"WhatsApp send failed for {phone}: {e}").log()

            NewsEvent("delivery", "info", f"WhatsApp briefing sent to {sent}/{len(wa_recipients)} recipients").log()

        except ImportError:
            NewsEvent("delivery", "warning", "WhatsJet integration not available for news delivery").log()
        except Exception as e:
            NewsEvent("delivery", "error", f"WhatsApp briefing delivery failed: {e}").log()
