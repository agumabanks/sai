import os
import uuid
import asyncio
from typing import Dict, Any
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from core.skills.base import BaseSkill, SkillResult

class WebAutomationSkill(BaseSkill):
    async def execute(self, params: Dict[str, Any], context: Any) -> SkillResult:
        action = params.get("action")
        url = params.get("url")
        wait_for = params.get("wait_for")
        timeout_sec = params.get("timeout_sec", 30)

        if not url:
            return SkillResult(success=False, error="URL is required.")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                await page.goto(url, timeout=timeout_sec * 1000)
                
                if wait_for:
                    await page.wait_for_selector(wait_for, timeout=timeout_sec * 1000)
                else:
                    await page.wait_for_load_state("networkidle", timeout=timeout_sec * 1000)
                
                if action == "extract_html":
                    html = await page.content()
                    await browser.close()
                    return SkillResult(success=True, output=html)
                    
                elif action == "extract_text":
                    html = await page.content()
                    await browser.close()
                    soup = BeautifulSoup(html, "html.parser")
                    text = soup.get_text(separator="\n", strip=True)
                    return SkillResult(success=True, output=text)
                    
                elif action == "screenshot":
                    screenshot_dir = "/var/www/ai.sanaa.co/backend/storage/screenshots"
                    os.makedirs(screenshot_dir, exist_ok=True)
                    filename = f"screenshot_{uuid.uuid4().hex}.png"
                    filepath = os.path.join(screenshot_dir, filename)
                    
                    await page.screenshot(path=filepath, full_page=True)
                    await browser.close()
                    
                    return SkillResult(
                        success=True, 
                        output=f"Screenshot saved to {filepath}",
                        data={"filepath": filepath}
                    )
                else:
                    await browser.close()
                    return SkillResult(success=False, error=f"Unknown action: {action}")
                    
        except Exception as e:
            return SkillResult(success=False, error=f"Playwright error: {str(e)}")

# Register entry point
handler = WebAutomationSkill
