import asyncio
import logging
import sys
import json
from datetime import datetime

# Set up logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Add backend to path
sys.path.append("/var/www/ai.sanaa.co/backend")

async def test_news_agent_mocked():
    from core.agents.news_agent import NewsAgent
    from core.database import StrategicSignal, AsyncSessionLocal
    from sqlalchemy import select, delete
    from unittest.mock import AsyncMock, patch

    agent = NewsAgent()
    print("--- Starting Mocked News Aggregation Test ---")
    
    # Mock data
    mock_articles = [
        {"title": "Uganda Central Bank Hikes Rates", "link": "https://example.com/a", "summary": "Bank of Uganda raises rates by 50bps.", "source": "Finance", "score": 9},
        {"title": "EAC Trade Fair Opens in Arusha", "link": "https://example.com/b", "summary": "The annual EAC trade fair kicks off.", "source": "Uganda/EAC", "score": 8}
    ]
    
    mock_summary = "## TOP STRATEGIC SIGNALS\n### Market\n**Headline:** Monetary Policy Tightening\n**Why It Matters:** Increased borrowing costs for Sanaa sellers.\n**Signal Level:** High"
    
    mock_summary_signals = [
        {
            "title": "Monetary Policy Tightening",
            "summary": "Bank of Uganda raises rates.",
            "score": 8,
            "classification": "Market",
            "business_impact": "Higher interest rates.",
            "tags": ["finance", "uganda"]
        }
    ]
    
    mock_article_signals = [
        {
            "title": "Rate Hike Opportunity",
            "link": "https://example.com/a",
            "summary": "BOA Rate hike details.",
            "score": 9,
            "classification": "Opportunity",
            "business_impact": "Direct relevance to treasury management.",
            "tags": ["banking"]
        }
    ]

    # Patch brain.think to return our mocks
    with patch.object(agent.brain, 'think') as mock_think:
        mock_think.side_effect = [
            mock_summary, # Synthesis
            json.dumps(mock_summary_signals), # _extract_signals_from_summary
            json.dumps(mock_article_signals)  # _extract_signals_from_articles
        ]
        
        # Patch archive_briefing to see if it receives the right signals
        import core.agents.news_agent as news_agent_mod
        with patch.object(news_agent_mod, 'archive_briefing', new_callable=AsyncMock) as mock_archive:
            # We need to manually set up filtered_news for the test
            # Since get_daily_summary is complex, let's just test the extraction bits directly
            
            print("Testing extraction from summary...")
            res_summary_signals = await agent._extract_signals_from_summary(mock_summary)
            print(f"Extracted {len(res_summary_signals)} signals from summary.")
            
            print("Testing extraction from articles...")
            res_article_signals = await agent._extract_signals_from_articles(mock_articles)
            print(f"Extracted {len(res_article_signals)} signals from articles.")
            
            # Combine
            all_signals = res_summary_signals + res_article_signals
            
            print("Testing persistence and duplicate prevention...")
            from core.intelligence.persistence import archive_knowledge
            
            # 1. First archive
            title = f"Test Briefing {datetime.now()}"
            bid1 = await archive_knowledge(title=title, content=mock_summary, signals=all_signals)
            print(f"Archived first set. Briefing ID: {bid1}")
            
            # 2. Try archiving again with same signals (Duplicate prevention check)
            bid2 = await archive_knowledge(title=title + " retry", content=mock_summary, signals=all_signals)
            print(f"Archived second set. Briefing ID: {bid2}")

    print("\n--- Verifying Database Records ---")
    async with AsyncSessionLocal() as session:
        # Check signals for the first briefing
        result = await session.execute(
            select(StrategicSignal).where(StrategicSignal.briefing_id == bid1)
        )
        signals1 = result.scalars().all()
        print(f"Signals for Briefing {bid1}: {len(signals1)}")
        for s in signals1:
            print(f"  - [{s.classification}] {s.title}")

        # Check signals for the second briefing (should be 0 or fewer if duplicate prevention works)
        result = await session.execute(
            select(StrategicSignal).where(StrategicSignal.briefing_id == bid2)
        )
        signals2 = result.scalars().all()
        print(f"Signals for Briefing {bid2}: {len(signals2)}")

if __name__ == "__main__":
    asyncio.run(test_news_agent_mocked())
