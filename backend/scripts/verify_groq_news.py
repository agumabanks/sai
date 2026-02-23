import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure we can import core
sys.path.append("/var/www/ai.sanaa.co")
load_dotenv("/opt/antigravity/.env")

from core.agents.news_agent import NewsAgent

async def verify():
    agent = NewsAgent()
    print("--- FETCHING AND FILTERING ARTICLES ---")
    
    # We call get_daily_summary which handles Phase 1 and Phase 2 internally
    # We want to see what Groq says
    summary = await agent.get_daily_summary()
    
    print("\n" + "="*50)
    print("RAW GROQ RESPONSE (CHIEF EDITOR SYNTHESIS):")
    print("="*50 + "\n")
    print(summary)
    print("\n" + "="*50)
    
    if len(summary) > 200:
        print("\n[SUCCESS] Groq response is substantial. Proceeding to send test news...")
        success = await agent.send_newsletter(summary=summary, recipient="media@sanaa.co")
        print(f"Test Email Sent: {success}")
    else:
        print("\n[ERROR] Groq response was empty or too short. Check logs.")

if __name__ == "__main__":
    asyncio.run(verify())
