import os
import re
import json
import httpx
import feedparser
import asyncio
import logging
import smtplib
import hashlib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from playwright.async_api import async_playwright
from core.brain import get_shared_brain
from core.config import get_settings
from core.intelligence.memory import IntelligenceMemory
from core.intelligence.persistence import archive_briefing
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
                articles = []
                for entry in feed.entries[:10]:
                    articles.append({
                        "title": entry.title,
                        "link": entry.link,
                        "summary": getattr(entry, 'summary', '')[:400],
                        "source": sector
                    })
                NewsEvent("ingestion", "info", f"Fetched {len(articles)} articles from {url}", {"sector": sector}).log()
                return articles
            else:
                NewsEvent("ingestion", "warning", f"No entries or failed to parse feed from {url}", {"sector": sector}).log()
                return []
        except Exception as e:
            NewsEvent("ingestion", "error", f"Error fetching source {url}: {e}", {"sector": sector}).log()
            return []

    def _keyword_relevance_score(self, article: dict) -> int:
        """Fast rule-based relevance scoring — zero LLM tokens used."""
        text = f"{article['title']} {article.get('summary', '')}".lower()
        hits = sum(1 for kw in HIGH_SIGNAL_KEYWORDS if kw in text)
        # Uganda/EAC articles get automatic boost
        if article.get("source") == "Uganda/EAC":
            hits += 3
        return min(hits, 10)

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

        # Sort by score, take top articles
        unique_articles.sort(key=lambda x: x["score"], reverse=True)
        filtered_news = [a for a in unique_articles if a["score"] >= 3]
        if not filtered_news:
            filtered_news = unique_articles[:15]

        # Cap at 20 to keep synthesis prompt size reasonable
        filtered_news = filtered_news[:20]

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
                {"title": a["title"], "link": a["link"], "summary": a.get("summary", "")[:200]}
                for a in arts
            ]

        prompt = f"""You are the Chief Editor of Sanaa Media Intelligence — an executive daily briefing for East African decision-makers.

AUDIENCE: Entrepreneurs, Traders, Government Officials, Investors in Uganda/EAC.
FOCUS: Finance, Policy, Infrastructure, Trade, Tax, Mining, Energy, Agriculture.
TONE: Analytical, Executive, Neutral. No fluff. No marketing speak.

STRICT OUTPUT FORMAT (use these exact markdown headers):

## TOP STRATEGIC SIGNALS
- Signal 1: [one-line macro insight]
- Signal 2: [one-line macro insight]
- Signal 3: [one-line macro insight]

### FINANCE & MARKETS
**Headline:** [Story title]
**What Happened:** [2-3 sentences of facts]
**Why It Matters:** [Business/strategic impact for East Africa]
**Signal Level:** High/Medium/Low
**Source:** [Publication]

### UGANDA/EAC
**Headline:** [Story title]
**What Happened:** [2-3 sentences of facts]
**Why It Matters:** [Business/strategic impact]
**Signal Level:** High/Medium/Low
**Source:** [Publication]

(Repeat for each major story across categories. Group related stories.)

## Opportunity Watch
- [Specific tender, grant, policy opening, or business opportunity with link if available]

## WHATSAPP VERSION
(Write a concise WhatsApp-ready summary, max 1000 characters. Use bullet points. Include key headlines and one-line impacts. Format for mobile reading.)

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
        sig_match = re.search(r'##\s*TOP STRATEGIC SIGNALS(.*?)(?=##|\Z)', summary, re.DOTALL | re.IGNORECASE)
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
        match = re.search(r'##\s*WHATSAPP VERSION\s*\n(.*?)(?=##|\Z)', summary, re.DOTALL | re.IGNORECASE)
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
                lines.append(f"**Source:** [{art['link']}]({art['link']})")
                score = art.get('score', 5)
                level = "High" if score >= 7 else "Medium" if score >= 4 else "Low"
                lines.append(f"**Signal Level:** {level}")
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
            lines.append(f"- {art['title']}")
        lines.append("")
        lines.append("Full briefing: check your email for the PDF attachment.")

        return "\n".join(lines)

    async def generate_pdf(self, summary: str, filename: str = None):
        if not filename:
            filename = f"Sanaa_Media_News_{datetime.now().strftime('%Y_%m_%d')}.pdf"
        filepath = os.path.join("/var/www/ai.sanaa.co/data/news", filename)
        # Strip WhatsApp section from PDF — it's for mobile delivery only
        pdf_summary = re.sub(r'##\s*WHATSAPP VERSION.*', '', summary, flags=re.DOTALL | re.IGNORECASE).strip()
        html_body = self._format_summary_to_html(pdf_summary)
        full_html = self._get_html_template(html_body)
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.set_content(full_html)
                await page.pdf(path=filepath, format="A4", print_background=True, margin={"top": "1cm", "right": "1cm", "bottom": "1cm", "left": "1cm"})
                await browser.close()
            return filepath
        except Exception as e:
            logger.error(f"PDF failed: {e}")
            return None

    def _format_summary_to_html(self, summary: str) -> str:
        """Convert markdown briefing to styled HTML with signal badges."""
        # Signal Level badges (before other transformations)
        summary = re.sub(
            r'\*\*Signal Level:\*\*\s*High',
            '<div style="display:inline-block;background:#dc2626;color:#fff;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;margin:4px 0;">HIGH SIGNAL</div>',
            summary
        )
        summary = re.sub(
            r'\*\*Signal Level:\*\*\s*Medium',
            '<div style="display:inline-block;background:#f59e0b;color:#fff;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;margin:4px 0;">MEDIUM SIGNAL</div>',
            summary
        )
        summary = re.sub(
            r'\*\*Signal Level:\*\*\s*Low',
            '<div style="display:inline-block;background:#10b981;color:#fff;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;margin:4px 0;">LOW SIGNAL</div>',
            summary
        )

        # Bold and italic
        summary = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', summary)
        summary = re.sub(r'\*(.*?)\*', r'<em>\1</em>', summary)

        # Strategic Signals section — special styling
        summary = re.sub(
            r'^##\s+TOP STRATEGIC SIGNALS',
            '<h2 style="margin-top:40px;color:#1e40af;border-bottom:3px solid #1e40af;padding-bottom:8px;font-size:20px;">TOP STRATEGIC SIGNALS</h2>',
            summary, flags=re.MULTILINE
        )

        # Opportunity Watch — special styling
        summary = re.sub(
            r'^##\s+Opportunity Watch',
            '<h2 style="margin-top:40px;color:#059669;border-bottom:3px solid #059669;padding-bottom:8px;font-size:20px;">OPPORTUNITY WATCH</h2>',
            summary, flags=re.MULTILINE | re.IGNORECASE
        )

        # Regular H2 sections
        summary = re.sub(
            r'^##\s+(.*)',
            r'<h2 style="margin-top:40px;border-bottom:2px solid #1d1d1f;padding-bottom:8px;">\1</h2>',
            summary, flags=re.MULTILINE
        )

        # H3 category sections
        summary = re.sub(
            r'^###\s+(.*)',
            r'<h3 style="margin-top:32px;border-bottom:1px solid #d1d5db;padding-bottom:8px;color:#374151;font-size:16px;">\1</h3>',
            summary, flags=re.MULTILINE
        )

        # List items
        summary = re.sub(
            r'^\s*[-*]\s+(.*)',
            r'<li style="margin-bottom:8px;line-height:1.5;">\1</li>',
            summary, flags=re.MULTILINE
        )
        summary = re.sub(
            r'((?:<li[^>]*>.*?</li>\s*)+)',
            r'<ul style="padding-left:20px;margin:12px 0;">\1</ul>',
            summary, flags=re.DOTALL
        )

        # Markdown links → HTML links
        summary = re.sub(
            r'\[([^\]]+)\]\(([^\)]+)\)',
            r'<a href="\2" style="color:#2563eb;text-decoration:underline;">\1</a>',
            summary
        )

        # Bare URLs → clickable links
        summary = re.sub(
            r'(?<!["\'])(https?://[^\s<\)]+)',
            r'<a href="\1" style="color:#2563eb;text-decoration:underline;word-break:break-all;">\1</a>',
            summary
        )

        lines = summary.split('\n')
        fmt = []
        for l in lines:
            l = l.strip()
            if not l:
                continue
            if l.startswith(("<h2", "<h3", "<ul", "<li", "<div", "<a ")):
                fmt.append(l)
            else:
                fmt.append(f'<p style="margin-bottom:12px;line-height:1.6;">{l}</p>')
        return "\n".join(fmt)

    def _get_html_template(self, body_content: str) -> str:
        date_str = datetime.now().strftime('%A, %B %d, %Y')
        year = datetime.now().year
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 40px 20px; background: #fff; color: #1d1d1f; line-height: 1.6; }}
        .container {{ max-width: 700px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 40px; padding-bottom: 20px; border-bottom: 1px solid #e5e7eb; }}
        .header h1 {{ font-size: 28px; margin: 0 0 4px; color: #111827; letter-spacing: -0.5px; }}
        .header .subtitle {{ font-size: 14px; color: #6b7280; margin: 0; }}
        .header .date {{ font-size: 13px; color: #9ca3af; margin-top: 4px; }}
        strong {{ color: #111827; }}
        a {{ color: #2563eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Sanaa Media Intelligence</h1>
            <p class="subtitle">Executive Daily Briefing</p>
            <p class="date">{date_str}</p>
        </div>
        <div>{body_content}</div>
        <div style="margin-top: 60px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center; color: #9ca3af; font-size: 11px;">
            <p>&copy; {year} Sanaa Media Group &mdash; Confidential Intelligence Briefing</p>
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

            # Fetch recipients from DB preferences, fallback to settings.env
            db_recipients = await SystemKnowledge.get_pref("alert.recipients", default=None)
            if db_recipients:
                recipients = db_recipients if isinstance(db_recipients, list) else [db_recipients]
            else:
                recipients = [recipient] if recipient else self.settings.alert_recipient_list

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

            pdf_path = await self.generate_pdf(summary)
            if pdf_path and os.path.exists(pdf_path):
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

            # Get WhatsApp recipients from DB or settings
            wa_recipients = await SystemKnowledge.get_pref("news.whatsapp_recipients", default=None)
            if not wa_recipients:
                # Fallback: check settings for a default news WhatsApp number
                wa_recipients = getattr(self.settings, 'news_whatsapp_recipients', None)

            if not wa_recipients:
                NewsEvent("delivery", "warning", "No WhatsApp recipients configured for news briefing").log()
                return

            if isinstance(wa_recipients, str):
                wa_recipients = [r.strip() for r in wa_recipients.split(",") if r.strip()]

            from core.integrations.whatsapp_saas_manager import WhatsAppSaaSManager
            wa = WhatsAppSaaSManager()

            date_str = datetime.now().strftime('%b %d, %Y')
            header = f"*SANAA INTELLIGENCE DAILY*\n_{date_str}_\n\n"
            full_message = header + wa_text

            sent = 0
            for phone in wa_recipients:
                try:
                    result = await wa.send_text(phone, full_message)
                    if result:
                        sent += 1
                except Exception as e:
                    NewsEvent("delivery", "warning", f"WhatsApp send failed for {phone}: {e}").log()

            NewsEvent("delivery", "info", f"WhatsApp briefing sent to {sent}/{len(wa_recipients)} recipients").log()

        except ImportError:
            NewsEvent("delivery", "warning", "WhatsJet integration not available for news delivery").log()
        except Exception as e:
            NewsEvent("delivery", "error", f"WhatsApp briefing delivery failed: {e}").log()
