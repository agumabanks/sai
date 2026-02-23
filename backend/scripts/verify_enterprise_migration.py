import asyncio
import logging
from core.agents.email_agent import EmailInboxAgent
from core.agents.server_health import ServerHealthAgent
from core.agents.app_monitor import AppMonitorAgent
from core.agents.healer import SelfHealer
from core.intelligence.memory import IntelligenceMemory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_migration():
    logger.info("=== Starting Enterprise Migration Verification ===")
    
    # 1. Verify Intelligence Memory
    memory = IntelligenceMemory()
    logger.info("Checking Intelligence Memory...")
    memory.add_strategic_signal({"category": "test", "title": "System Check", "summary": "Verification in progress", "score": 5})
    context = memory.get_all_context()
    if "RECENT STRATEGIC SIGNALS" in context:
        logger.info("✅ Intelligence Memory generalized successfully.")
    else:
        logger.error("❌ Intelligence Memory verification failed.")

    # 2. Verify Agents (Dry Run / Mock)
    email_agent = EmailInboxAgent()
    health_agent = ServerHealthAgent()
    app_agent = AppMonitorAgent()
    
    logger.info("Testing Server Health Agent Snapshot...")
    snapshot = await health_agent.get_snapshot()
    if snapshot.get("overall_status"):
        logger.info(f"✅ Server Health Agent active. Status: {snapshot['overall_status']}")
    
    logger.info("Testing App Monitor Agent Log Scan...")
    # This might return empty if no logs, but shouldn't crash
    logs = await app_agent.get_logs(limit=1)
    logger.info(f"✅ App Monitor Agent scan completed. {len(logs)} entries found.")

    # 3. Verify Healer
    healer = SelfHealer()
    logger.info("Testing Healer with mock critical event...")
    test_event = {
        "id": "test_123",
        "category": "app",
        "severity": "critical",
        "message": "Database connection timeout in Soko app",
        "app": "soko"
    }
    actions = await healer.process_events([test_event])
    if any(a.get("ui_heal_token") for a in actions):
        logger.info("✅ Healer successfully generated UI remediation token.")
    else:
        logger.error("❌ Healer remediation logic failed.")

    logger.info("=== Verification Complete ===")

if __name__ == "__main__":
    asyncio.run(verify_migration())
