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
from core.brain import Brain
from core.config import get_settings
from core.intelligence.memory import IntelligenceMemory
from core.intelligence.persistence import archive_briefing
from core.database import SystemKnowledge

logger = logging.getLogger(__name__)

class NewsEvent:
    """Structured event logging for independent audit trails (OpenClaw Pattern)."""
    def __init__(self, category: str, severity: str, message: str, metadata: dict = None):
        self.id = hashlib.md5(f"{category}:{message}:{datetime.now()}".encode()).hexdigest()[:8]
        self.category = category # ingestion, analysis, synthesis, delivery
        self.severity = severity # info, warning, error
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
    def __init__(self):
        self.settings = get_settings()
        self.brain = Brain()
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

    async def get_daily_summary(self, topics=None):
        """Aggregate news and summarize using structured OpenClaw logic."""
        if topics is None:
            topics = self.feeds.keys()

        # Ingestion phase
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

        # Deduplication (improved semantic slugs)
        seen_slugs = set()
        unique_articles = []
        for a in all_articles:
            # Create a more robust slug: lowercase alphanumeric only
            slug = re.sub(r'[^a-zA-Z0-9]', '', a["title"].lower())
            if slug not in seen_slugs and len(slug) > 10:
                seen_slugs.add(slug)
                unique_articles.append(a)
        
        NewsEvent("ingestion", "info", f"Aggregated {len(unique_articles)} unique articles").log()

        if not unique_articles:
            return "No news aggregated (Check feed URLs or connectivity)."

        # Tier 1 filtering (Batch processing)
        filtered_news = []
        batch_size = 15
        for i in range(0, len(unique_articles), batch_size):
            batch = unique_articles[i:i+batch_size]
            NewsEvent("analysis", "info", f"Analyzing batch {i//batch_size + 1} of {(len(unique_articles)-1)//batch_size + 1}").log()
            try:
                scored_batch = await self._score_articles_batch(batch)
                for article, analysis in zip(batch, scored_batch):
                    if analysis.get("score", 0) >= 7:
                        article.update(analysis)
                        filtered_news.append(article)
            except Exception as e:
                NewsEvent("analysis", "error", f"Batch {i//batch_size + 1} failed", {"error": str(e)}).log()

        if not filtered_news:
            NewsEvent("analysis", "warning", "Zero high-signal articles found").log()
            return "No high-signal news found for today."

        # Grouping for synthesis
        all_news = {}
        for art in filtered_news:
            source = art["source"]
            if source not in all_news:
                all_news[source] = []
            all_news[source].append(art)

        # Tier 3 synthesis
        domain_context = await self.memory.get_all_context()
        NewsEvent("synthesis", "info", f"Starting synthesis for {len(filtered_news)} articles").log()
        
        prompt = f"""You are the Chief Editor of Sanaa Media Intelligence.
        
        SANAA ECOSYSTEM CONTEXT:
        {domain_context}

        Rules:
        1. Priority: Finance, trade, policy, infrastructure.
        2. Business Impact: Connect events to East African business.
        3. DEEP OPPORTUNITY EXTRACTION: 
           - Identify specific Tenders, grants, or policy openings.
           - Extract Official IDs, reference numbers, and URLs.
           - If a document is mentioned (e.g., "Draft Energy Policy 2026"), search for its official link.
        4. Tone: Professional, executive.

        Structure:
        ## TOP STRATEGIC SIGNALS
        (3-5 pointers)
        
        ### [CATEGORY]
        **Headline:** ...
        **What Happened:** ...
        **Why It Matters:** ...
        **Opportunities:** (List specific tenders/IDs/links if any)
        **Signal Level:** High/Medium/Low
        
        ## Opportunity Watch
        (Highlight specific actionable items with official links)

        ## WHATSAPP VERSION
        (Concise summary)

        DATA:
        {json.dumps(all_news, indent=2)}
        """

        try:
            summary = await self.brain.think(prompt, complexity="high")
            if not summary or len(summary.strip()) < 100:
                logger.warning("Empty LLM synthesis, triggering fallback")
                summary = self._generate_fallback_summary(all_news)
            
            # Verify links (Deep Opportunity Extraction)
            summary = await self._verify_links(summary)

            # QA/repair pass to stabilize briefing structure and usefulness
            summary = await self._qa_and_repair_summary(summary, all_news)
            
            # Dual-Stream Extraction:
            # 1. Broad signals from summary
            signals = await self._extract_signals_from_summary(summary)
            
            # 2. Specific signals from top-tier articles (score >= 9)
            top_articles = [a for a in filtered_news if a.get("score", 0) >= 9]
            if top_articles:
                article_signals = await self._extract_signals_from_articles(top_articles)
                signals.extend(article_signals)
            
            # Archive to database
            briefing_title = f"Daily Briefing - {datetime.now().strftime('%Y-%m-%d')}"
            await archive_briefing(
                title=briefing_title,
                content=summary,
                signals=signals,
                metadata={"article_count": len(filtered_news), "topics": list(all_news.keys())}
            )
            
            return summary
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return self._generate_fallback_summary(all_news)

    async def _qa_and_repair_summary(self, summary: str, all_news: dict) -> str:
        """Assess briefing quality and run one repair pass if needed."""
        qa = await self._assess_summary_quality(summary)
        try:
            qa_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            await SystemKnowledge.set_pref(
                "briefing.latest.qa",
                json.dumps(qa),
                domain="news",
                source="news_agent",
            )
            await SystemKnowledge.set_pref(
                f"briefing.qa.history.{qa_timestamp}",
                json.dumps(qa),
                domain="news",
                source="news_agent",
            )
        except Exception as e:
            logger.warning(f"Failed to persist briefing QA: {e}")

        score = int(qa.get("score", 0) or 0) if isinstance(qa, dict) else 0
        needs_repair = bool(qa.get("needs_repair")) if isinstance(qa, dict) else False
        if score >= 7 and not needs_repair:
            return summary

        repair_prompt = f"""Repair this Sanaa intelligence briefing.

Requirements:
- Keep facts and links already present (do not invent links).
- Keep executive tone.
- Ensure these sections exist in order:
  1) ## TOP STRATEGIC SIGNALS
  2) ## Opportunity Watch
  3) ## WHATSAPP VERSION
- Make the WhatsApp version concise (<= 1200 characters).
- If evidence is weak, say so explicitly instead of guessing.

SOURCE NEWS (for grounding):
{json.dumps(all_news, indent=2)[:12000]}

CURRENT BRIEFING:
{summary}
"""
        try:
            repaired = await self.brain.think(repair_prompt, complexity="high")
            if repaired and len(repaired.strip()) > 200:
                return repaired
        except Exception as e:
            logger.warning(f"Briefing repair pass failed: {e}")
        return summary

    async def _assess_summary_quality(self, summary: str) -> dict:
        """Score briefing quality so bad briefs can be auto-repaired."""
        prompt = f"""Assess this Sanaa intelligence briefing for format and signal quality.

Return ONLY JSON:
{{
  "score": 1-10,
  "needs_repair": true,
  "issues": ["..."],
  "strengths": ["..."]
}}

BRIEFING:
{summary}
"""
        default = {"score": 6, "needs_repair": False, "issues": [], "strengths": []}
        try:
            response = await self.brain.think(prompt, complexity="medium")
            match = re.search(r'\{[\s\S]*\}', response)
            if not match:
                return default
            data = json.loads(match.group())
            if not isinstance(data, dict):
                return default
            return {
                "score": int(data.get("score", 6) or 6),
                "needs_repair": bool(data.get("needs_repair", False)),
                "issues": data.get("issues", []) if isinstance(data.get("issues"), list) else [],
                "strengths": data.get("strengths", []) if isinstance(data.get("strengths"), list) else [],
            }
        except Exception as e:
            logger.warning(f"Briefing QA failed: {e}")
            return default

    async def _extract_signals_from_summary(self, summary: str) -> list:
        """Extract broad 'Strategic Signals' from the synthesized summary."""
        prompt = f"""Extract high-level 'Strategic Signals' from the following Intelligence Summary.
        
        SUMMARY:
        {summary}
        
        Respond ONLY in a JSON list of objects:
        [
          {{
            "title": "Signal Headline",
            "summary": "Brief explanation",
            "score": 1-10,
            "classification": "Opportunity|Threat|Policy|Market",
            "business_impact": "How it affects Sanaa/East Africa",
            "tags": ["tag1", "tag2"]
          }}
        ]
        """
        try:
            response = await self.brain.think(prompt, complexity="medium")
            match = re.search(r'\[[\s\S]*\]', response)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning(f"Failed to extract signals from summary: {e}")
        return []

    async def _extract_signals_from_articles(self, articles: list) -> list:
        """Deep extraction of opportunities/tenders directly from high-score articles."""
        articles_context = json.dumps([{"title": a["title"], "link": a["link"], "summary": a["summary"]} for a in articles], indent=2)
        
        prompt = f"""Identify specific, actionable business opportunities or strategic shifts from these articles.
        Focus on: Tenders, Grants, Policy Changes, Mergers, or Infrastructure launches.
        
        ARTICLES:
        {articles_context}
        
        Respond ONLY in a JSON list of objects:
        [
          {{
            "title": "Specific Opportunity Title",
            "link": "Official URL",
            "summary": "Specific details (IDs, dates, requirements)",
            "score": 1-10,
            "classification": "Opportunity",
            "business_impact": "Direct relevance to Sanaa or its sellers",
            "tags": ["specific-tag"]
          }}
        ]
        """
        try:
            response = await self.brain.think(prompt, complexity="high")
            match = re.search(r'\[[\s\S]*\]', response)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning(f"Failed to extract signals from articles: {e}")
        return []

    async def _score_articles_batch(self, articles: list) -> list:
        """Batch analyze articles with Healer mechanism for self-correction."""
        articles_json = json.dumps([{"title": a["title"], "summary": a["summary"]} for a in articles], indent=1)
        
        # Double braces for literal JSON template in f-string
        prompt = f"""Analyze these news for East African Business relevance.
        Return EXCLUSIVELY a JSON list:
        [ {{ "score": 0-10, "classification": "category", "tags": [] }}, ... ]

        ARTICLES:
        {articles_json}
        """

        try:
            response = await self.brain.think(prompt, complexity="low")
            
            def parse_json(text):
                match = re.search(r'\[[\s\S]*\]', text)
                if match:
                    return json.loads(match.group())
                raise ValueError("No valid JSON found")

            try:
                results = parse_json(response)
            except (ValueError, json.JSONDecodeError):
                NewsEvent("analysis", "warning", "JSON parse failed, healing...").log()
                fix_prompt = f"Fix this broken JSON list. ONLY results, no text:\n{response}"
                fixed = await self.brain.think(fix_prompt, complexity="medium")
                results = parse_json(fixed)

            if len(results) != len(articles):
                return [{"score": 5, "classification": "General", "tags": []} for _ in articles]
            return results
        except Exception as e:
            NewsEvent("analysis", "error", f"Scoring failed: {e}").log()
            return [{"score": 5, "classification": "General", "tags": []} for _ in articles]

    async def _verify_links(self, text: str) -> str:
        """Healer wrapper for URLs: finds links in text and validates them."""
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
        for url in urls:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.head(url, follow_redirects=True)
                    if resp.status_code >= 400:
                        text = text.replace(url, f"{url} (Link Pending/Verification Failed)")
                    else:
                        text = text.replace(url, f"{url} [Validated]")
            except Exception:
                text = text.replace(url, f"{url} (Link Offline)")
        return text

    def _generate_fallback_summary(self, all_news: dict) -> str:
        lines = ["# Sanaa Intelligence Daily - High Signal Feed", ""]
        for topic, articles in all_news.items():
            if articles:
                lines.append(f"## {topic.upper()}")
                for art in articles:
                    lines.append(f"* **{art['title']}** - [Link]({art['link']})")
                lines.append("")
        return "\n".join(lines)

    async def generate_pdf(self, summary: str, filename: str = None):
        if not filename:
            filename = f"Sanaa_Media_News_{datetime.now().strftime('%Y_%m_%d')}.pdf"
        filepath = os.path.join("/var/www/ai.sanaa.co/data/news", filename)
        html_body = self._format_summary_to_html(summary)
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
        # Simple Markdown-to-HTML
        summary = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', summary)
        summary = re.sub(r'\*(.*?)\*', r'<em>\1</em>', summary)
        summary = re.sub(r'^##\s+(.*)', r'<h2 style="margin-top: 40px; border-bottom: 2px solid #1d1d1f; padding-bottom: 8px;">\1</h2>', summary, flags=re.MULTILINE)
        summary = re.sub(r'^###\s+(.*)', r'<h3 style="margin-top: 32px; border-bottom: 1px solid #e5e5e5; padding-bottom: 8px;">\1</h3>', summary, flags=re.MULTILINE)
        summary = re.sub(r'^\s*-\s+(.*)', r'<li style="margin-bottom: 8px;">\1</li>', summary, flags=re.MULTILINE)
        summary = re.sub(r'((?:<li>.*?</li>\s*)+)', r'<ul style="padding-left: 20px;">\1</ul>', summary, flags=re.DOTALL)
        
        lines = summary.split('\n')
        fmt = []
        for l in lines:
            l = l.strip()
            if not l: continue
            if l.startswith(("<h2", "<h3", "<ul", "<li", "<div")):
                fmt.append(l)
            else:
                fmt.append(f'<p style="margin-bottom: 16px; line-height: 1.6;">{l}</p>')
        return "\n".join(fmt)

    def _get_html_template(self, body_content: str) -> str:
        date_str = datetime.now().strftime('%A, %B %d, %Y')
        # Triple braces for extreme safety in nested strings
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: sans-serif; padding: 40px; background: #fff; color: #1d1d1f; line-height: 1.5; }}
                .container {{ max-width: 680px; margin: 0 auto; }}
                .header {{ text-align: center; margin-bottom: 40px; }}
                .header h1 {{ font-size: 32px; margin: 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Sanaa Media News</h1>
                    <p>{date_str}</p>
                </div>
                <div>{body_content}</div>
                <div style="margin-top: 60px; text-align: center; color: #86868b; font-size: 12px;">
                    <p>© {datetime.now().year} Sanaa Media Group</p>
                </div>
            </div>
        </body>
        </html>
        """

    async def send_newsletter(self, summary: str = None, recipient: str = None):
        if summary is None:
            summary = await self.get_daily_summary()
        if not summary or len(summary.strip()) < 100:
            logger.error("No content to send")
            return False

        try:
            subject = f"Sanaa Media News — {datetime.now().strftime('%b %d, %Y')}"
            
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

            html_body = self._format_summary_to_html(summary)
            full_html = self._get_html_template(html_body)

            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(summary, "plain"))
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
            return True
        except Exception as e:
            logger.error(f"Send failed: {e}")
            return False
