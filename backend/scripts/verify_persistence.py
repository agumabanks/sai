import asyncio
import logging
from core.database import IntelligenceBriefing, StrategicSignal, AsyncSessionLocal
from sqlalchemy import select, func

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_archive():
    logger.info("--- VERIFYING INTELLIGENCE ARCHIVE ---")
    async with AsyncSessionLocal() as session:
        # Check briefings count
        briefing_count = await session.execute(select(func.count(IntelligenceBriefing.id)))
        count = briefing_count.scalar()
        logger.info(f"Total briefings in DB: {count}")
        
        if count > 0:
            # Get latest briefing
            result = await session.execute(
                select(IntelligenceBriefing).order_by(IntelligenceBriefing.created_at.desc()).limit(1)
            )
            latest = result.scalars().first()
            logger.info(f"Latest Briefing: {latest.title} (Created: {latest.created_at})")
            
            # Check signals for this briefing
            signal_count = await session.execute(
                select(func.count(StrategicSignal.id)).where(StrategicSignal.briefing_id == latest.id)
            )
            s_count = signal_count.scalar()
            logger.info(f"Signals attached to latest briefing: {s_count}")
            
            if s_count > 0:
                # Get a sample signal
                s_result = await session.execute(
                    select(StrategicSignal).where(StrategicSignal.briefing_id == latest.id).limit(1)
                )
                sample = s_result.scalars().first()
                logger.info(f"Sample Signal: {sample.title} | Score: {sample.score} | Classification: {sample.classification}")
                
                print("\n[SUCCESS] Intelligence Archive is functional and storing data correctly.")
            else:
                print("\n[WARNING] Briefing found but no signals attached.")
        else:
            print("\n[ERROR] No briefings found in database. Archive check failed.")

if __name__ == "__main__":
    asyncio.run(verify_archive())
