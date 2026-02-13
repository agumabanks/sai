"""Web Test Agent — Tests webapps using Playwright"""

import os
from playwright.async_api import async_playwright

class WebTestAgent:
    def __init__(self):
        self.urls = os.getenv("MONITOR_URLS", "").split(",")

    async def test_single(self, url: str) -> dict:
        """Test a single URL"""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            result = {
                "url": url,
                "status": "down",
                "latency_ms": 0,
                "error": None
            }
            
            try:
                start_time = os.times().elapsed
                response = await page.goto(url, timeout=30000)
                end_time = os.times().elapsed
                
                result["latency_ms"] = int((end_time - start_time) * 1000)
                
                if response and response.ok:
                    result["status"] = "up"
                else:
                    result["status"] = "down"
                    result["error"] = f"HTTP {response.status if response else 'No Response'}"
                    
            except Exception as e:
                result["error"] = str(e)
            finally:
                await browser.close()
                
            return result

    async def test_all(self) -> list:
        """Test all monitored URLs"""
        results = []
        for url in self.urls:
            if url.strip():
                results.append(await self.test_single(url.strip()))
        return results
