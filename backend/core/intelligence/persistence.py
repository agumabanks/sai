import logging
from typing import List, Dict, Any
from core.database import IntelligenceBriefing, StrategicSignal, AsyncSessionLocal

logger = logging.getLogger(__name__)

async def archive_knowledge(title: str, content: str, signals: List[Dict[str, Any]] = None, metadata: Dict[str, Any] = None):
    """
    Persist general knowledge events, briefings, or reports to the database.
    (Generalized from archive_briefing)
    """
    try:
        from sqlalchemy import select, and_
        from datetime import datetime, timedelta, timezone

        async with AsyncSessionLocal() as session:
            # 1. Create the Briefing record
            briefing = IntelligenceBriefing(
                title=title,
                content=content,
                metadata_=metadata,
                delivered=True
            )
            session.add(briefing)
            await session.flush()
            
            # 2. Create individual StrategicSignal records with duplicate prevention
            if signals:
                for s in signals:
                    sig_title = s.get("title")
                    sig_class = s.get("classification")
                    
                    # Check for duplicates in the last 24 hours
                    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
                    existing = await session.execute(
                        select(StrategicSignal).where(
                            and_(
                                StrategicSignal.title == sig_title,
                                StrategicSignal.classification == sig_class,
                                StrategicSignal.created_at >= day_ago
                            )
                        )
                    )
                    if existing.scalars().first():
                        logger.info(f"Skipping duplicate signal: {sig_title}")
                        continue

                    signal = StrategicSignal(
                        briefing_id=briefing.id,
                        title=sig_title,
                        link=s.get("link"),
                        source=s.get("source", "Agent"),
                        summary=s.get("summary"),
                        score=s.get("score", 0),
                        classification=sig_class,
                        business_impact=s.get("business_impact"),
                        tags=s.get("tags")
                    )
                    session.add(signal)
            
            await session.commit()
            logger.info(f"Successfully archived knowledge event: {title}")
            return briefing.id
    except Exception as e:
        logger.error(f"Failed to archive knowledge event: {e}")
        return None

# Keep archive_briefing for backward compatibility but alias it
archive_briefing = archive_knowledge
