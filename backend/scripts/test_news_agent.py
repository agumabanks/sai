import asyncio
import sys
import os

# Add parent directory of core to path so "core.agents" works
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.agents.news_agent import NewsAgent
from dotenv import load_dotenv

# Load env from /opt/antigravity/.env
load_dotenv("/opt/antigravity/.env")

async def test_email():
    agent = NewsAgent()
    print("--- FETCHING AND SENDING TEST EMAIL TO media@sanaa.co ---")
    
    # This will fetch, summarize, generate PDF, and send
    success = await agent.send_newsletter(recipient="media@sanaa.co")
    print(f"Email sent: {success}")
    
    # Verify PDF exists
    news_dir = "/var/www/ai.sanaa.co/data/news"
    files = os.listdir(news_dir)
    print(f"PDFs in data/news: {files}")

if __name__ == "__main__":
    asyncio.run(test_email())
