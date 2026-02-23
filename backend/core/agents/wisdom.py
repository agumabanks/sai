"""
Sanaa AI WisdomAgent — Autonomous Log Analysis & Debugging
Meditates on logs and alerts to find patterns and suggest permanent fixes.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from core.brain.engine import Brain
from core.database import Alert, AuditLog, SystemKnowledge, AsyncSessionLocal
from sqlalchemy import select, desc

logger = logging.getLogger(__name__)

class WisdomAgent:
    def __init__(self):
        self.brain = Brain()

    async def meditate(self):
        """Perform a deep scan of recent system metadata to find 'Wisdom'."""
        logger.info("WisdomAgent: Starting log meditation...")
        
        # 1. Fetch recent alerts and audit logs
        async with AsyncSessionLocal() as session:
            # Recent failure alerts
            alert_res = await session.execute(
                select(Alert)
                .where(Alert.severity.in_(["high", "critical"]))
                .order_by(desc(Alert.created_at))
                .limit(20)
            )
            alerts = alert_res.scalars().all()
            
            # Recent critical audit logs
            audit_res = await session.execute(
                select(AuditLog)
                .where(AuditLog.success == False)
                .order_by(desc(AuditLog.timestamp))
                .limit(20)
            )
            audits = audit_res.scalars().all()

        if not alerts and not audits:
            logger.info("WisdomAgent: No critical issues found to meditate on.")
            return

        # 2. Construct context for the Brain
        context = {
            "alerts": [
                {"message": a.message, "metric": a.metric, "time": a.created_at.isoformat()}
                for a in alerts
            ],
            "failures": [
                {"action": au.action, "resource": au.resource, "time": au.timestamp.isoformat() if au.timestamp else None}
                for au in audits
            ]
        }

        # 3. Ask Brain for Wisdom
        prompt = f"""You are the System Architect of Sanaa AI.
        Analyze these recent system failures and alerts to find a root cause pattern.
        
        LOG DATA:
        {json.dumps(context, indent=2)}
        
        Provide a structured 'Wisdom Byte' in JSON:
        {{
            "pattern_found": "Clear description of the recurring issue",
            "root_cause_hypothesis": "Why is this happening?",
            "suggested_fix": "Concrete architectural or config change",
            "confidence": 1-10,
            "severity_score": 1-10
        }}
        """
        
        try:
            raw_wisdom = await self.brain.think(prompt, complexity="high")
            import re
            match = re.search(r'\{[\s\S]*\}', raw_wisdom)
            if match:
                wisdom_data = json.loads(match.group())
                
                # 4. Persist Wisdom to SystemKnowledge
                await SystemKnowledge.set_pref(
                    "system.wisdom.latest",
                    json.dumps(wisdom_data),
                    domain="wisdom",
                    source="wisdom_agent"
                )
                logger.info("WisdomAgent: New insight persisted.")
                return wisdom_data
        except Exception as e:
            logger.error(f"WisdomAgent meditation failed: {e}")
            return None

    async def get_latest_insight(self):
        """Retrieve the latest meditation result."""
        val = await SystemKnowledge.get_pref("system.wisdom.latest", domain="wisdom")
        if val:
            try:
                return json.loads(val)
            except:
                return None
        return None
