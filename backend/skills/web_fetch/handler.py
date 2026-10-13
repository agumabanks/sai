"""Web Fetch — extract and summarize content from any URL."""
import logging
import re
import httpx
from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


def _strip_html(html: str) -> str:
    """Quick and dirty HTML-to-text conversion."""
    # Remove script/style blocks
    html = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', '', html, flags=re.IGNORECASE)
    # Remove tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class WebFetchSkill(BaseSkill):
    name = "web_fetch"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        url = args.get("url", "").strip()
        mode = args.get("mode", "extract")

        if not url:
            return SkillResult(success=False, error="A 'url' parameter is required.")

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "SanaaAI/1.0 (Research Bot)"
                })
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            raw = resp.text

            if "html" in content_type:
                text = _strip_html(raw)
            else:
                text = raw

            # Truncate to prevent token overflow
            text = text[:6000]

            if mode == "summarize":
                from core.brain import Brain
                brain = Brain()
                summary = await brain.think(
                    f"Summarize the following web page content concisely:\n\n{text}",
                    complexity="low"
                )
                return SkillResult(success=True, output=summary, data={"url": url, "chars": len(text)})

            return SkillResult(success=True, output=text, data={"url": url, "chars": len(text)})

        except httpx.HTTPStatusError as e:
            return SkillResult(success=False, error=f"HTTP {e.response.status_code} from {url}")
        except Exception as e:
            logger.error(f"web_fetch failed: {e}")
            return SkillResult(success=False, error=str(e))
