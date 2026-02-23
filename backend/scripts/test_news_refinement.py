import asyncio
import logging
import sys
import os

# Set up logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Add backend to path
sys.path.append("/var/www/ai.sanaa.co/backend")

async def test_news_agent():
    from core.agents.news_agent import NewsAgent
    from core.database import StrategicSignal, AsyncSessionLocal
    from sqlalchemy import select

    agent = NewsAgent()
    print("--- Starting News Aggregation Test ---")
    
    # Run daily summary (limited topics for speed)
    summary = await agent.get_daily_summary(topics=["Finance", "Uganda/EAC"])
    
    print("\n--- Synthesis Summary ---")
    print(summary[:500] + "...")
    
    print("\n--- Verifying Database Records ---")
    from core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(StrategicSignal).order_by(StrategicSignal.created_at.desc()).limit(10)
        )
        signals = result.scalars().all()
        
        print(f"Total signals found in recent history: {len(signals)}")
        for s in signals:
            print(f"  - [{s.classification}] {s.title} (Score: {s.score})")
            if s.business_impact:
                print(f"    Impact: {s.business_impact[:100]}...")

if __name__ == "__main__":
    asyncio.run(test_news_agent())
