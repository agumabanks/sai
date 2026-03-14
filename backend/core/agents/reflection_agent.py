"""
Reflection Agent — Behavioral Cloning & Memory Consolidation
Runs daily to analyze user commands and interactions, establishing "Jarvis" preferences.

Includes OpenClaw-inspired correction detection and knowledge gap detection:
- Correction detection: scans conversation history for patterns where user corrects the AI.
- Gap detection: identifies instances where the AI expressed uncertainty or user provided missing context.
Both feed into the structured learning logs system.
"""

import logging
import json
import re
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
from core.database import AsyncSessionLocal
from core.brain import get_shared_brain

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Correction detection patterns
# --------------------------------------------------------------------------
# Each pattern is a compiled regex applied to user messages.
# To reduce false positives, we require a correction indicator followed by
# substantive content (at least a few words giving the correct information).
# We also define "false positive" patterns that look like corrections but are
# actually polite dismissals, agreements, or questions.
# --------------------------------------------------------------------------

# Phrases that, when followed by substantive content, indicate a user correction
_CORRECTION_PATTERNS = [
    # "No, I meant X" / "No I meant X"
    re.compile(r"\bno[,.]?\s+i\s+meant\b", re.IGNORECASE),
    # "That's wrong" / "That is wrong" / "Thats wrong"
    re.compile(r"\bthat(?:'?s|\s+is)\s+wrong\b", re.IGNORECASE),
    # "That's not right" / "That's not correct"
    re.compile(r"\bthat(?:'?s|\s+is)\s+not\s+(?:right|correct)\b", re.IGNORECASE),
    # "Actually it should be" / "Actually, it's X"
    re.compile(r"\bactually\s+(?:it\s+should|it\s*'?s|the|I|we|you)\b", re.IGNORECASE),
    # "You got it wrong" / "You got that wrong"
    re.compile(r"\byou\s+got\s+(?:it|that)\s+wrong\b", re.IGNORECASE),
    # "Wrong, it's X" / "Wrong — the answer is X"
    re.compile(r"^wrong[,.\s—–-]", re.IGNORECASE),
    # "Not X, it's Y" pattern e.g. "Not MySQL, it's PostgreSQL"
    re.compile(r"\bnot\s+\w+[,;]\s+(?:it(?:'?s|\s+is)|I\s+(?:meant|want))\b", re.IGNORECASE),
    # "I said X not Y" pattern
    re.compile(r"\bi\s+said\b.*\bnot\b", re.IGNORECASE),
    # "No, that's not" (as opener)
    re.compile(r"^no[,.]?\s+that(?:'?s|\s+is)\s+not\b", re.IGNORECASE),
    # "Incorrect" as standalone or at start
    re.compile(r"^incorrect[,.\s—–-]", re.IGNORECASE),
]

# Patterns that look like corrections but are actually polite refusals,
# agreements, or generic negation — used to filter false positives.
_FALSE_POSITIVE_PATTERNS = [
    # "No thanks" / "No, thank you" / "No, that's all"
    re.compile(r"\bno[,.]?\s+(?:thanks?|thank\s+you|that(?:'?s|\s+is)\s+all)\b", re.IGNORECASE),
    # "No problem" / "No worries"
    re.compile(r"\bno\s+(?:problem|worries|issue)\b", re.IGNORECASE),
    # "Not sure" (user expressing own uncertainty, not correcting)
    re.compile(r"^\s*(?:i(?:'?m)?\s+)?not\s+sure\b", re.IGNORECASE),
    # "No, I don't" / "No, I'm good"
    re.compile(r"\bno[,.]?\s+i(?:'?m|\s+am)?\s+(?:good|fine|ok|okay|done)\b", re.IGNORECASE),
    # General question patterns ("Why is X not …", "Why not …")
    re.compile(r"^\s*(?:why|how|when|what|where|is|are|can|could|should)\b", re.IGNORECASE),
]

# --------------------------------------------------------------------------
# Gap (uncertainty) detection patterns
# --------------------------------------------------------------------------
# Applied to *assistant* messages to find expressions of uncertainty.
# --------------------------------------------------------------------------

_AI_UNCERTAINTY_PATTERNS = [
    re.compile(r"\bi\s+don(?:'?t|'t)\s+know\b", re.IGNORECASE),
    re.compile(r"\bi(?:'?m|\s+am)\s+not\s+sure\b", re.IGNORECASE),
    re.compile(r"\bi\s+can(?:'?t|not|'t)\s+help\s+with\b", re.IGNORECASE),
    re.compile(r"\bi\s+don(?:'?t|'t)\s+have\s+(?:information|data|access|details)\b", re.IGNORECASE),
    re.compile(r"\bi(?:'?m|\s+am)\s+unable\s+to\b", re.IGNORECASE),
    re.compile(r"\bi\s+can(?:'?t|not|'t)\s+(?:find|determine|access|retrieve)\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:lack|have\s+no)\s+(?:information|knowledge|data|access)\b", re.IGNORECASE),
    re.compile(r"\bbeyond\s+my\s+(?:capabilities|knowledge|scope)\b", re.IGNORECASE),
]

# Applied to *assistant* messages requesting more info from user
_AI_NEEDS_INFO_PATTERNS = [
    re.compile(r"\bi\s+need\s+more\s+(?:information|details|context)\b", re.IGNORECASE),
    re.compile(r"\bcould\s+you\s+(?:provide|give|share|tell)\s+(?:me\s+)?(?:more|the)\b", re.IGNORECASE),
    re.compile(r"\bplease\s+(?:provide|specify|clarify)\b", re.IGNORECASE),
]


class ReflectionAgent:
    def __init__(self, brain=None):
        self.brain = brain or get_shared_brain()

    # ------------------------------------------------------------------
    # Correction Detection (VAL-MEM-006)
    # ------------------------------------------------------------------

    def detect_corrections(self, conversations: list[dict]) -> list[dict]:
        """Scan conversation history for patterns where user corrects the AI.

        Args:
            conversations: List of message dicts with 'role' and 'content' keys.

        Returns:
            List of correction dicts with keys: content, source, category.
        """
        if not conversations:
            return []

        corrections: list[dict] = []

        for i, msg in enumerate(conversations):
            if msg.get("role") != "user":
                continue

            content = msg.get("content", "").strip()
            if not content:
                continue

            # Check false-positive patterns first — skip if matched
            if any(fp.search(content) for fp in _FALSE_POSITIVE_PATTERNS):
                continue

            # Check correction patterns
            matched = False
            for pattern in _CORRECTION_PATTERNS:
                if pattern.search(content):
                    matched = True
                    break

            if not matched:
                continue

            # Build contextual correction entry including the preceding assistant message
            preceding_assistant = ""
            if i > 0 and conversations[i - 1].get("role") == "assistant":
                preceding_assistant = conversations[i - 1].get("content", "")

            correction_text = content
            if preceding_assistant:
                correction_text = (
                    f"User corrected AI. AI said: \"{preceding_assistant[:200]}\" "
                    f"→ User correction: \"{content}\""
                )

            corrections.append({
                "content": correction_text,
                "source": "conversation",
                "category": "correction",
            })

        return corrections

    # ------------------------------------------------------------------
    # Gap Detection (VAL-MEM-007)
    # ------------------------------------------------------------------

    def detect_gaps(self, conversations: list[dict]) -> list[dict]:
        """Identify knowledge gaps from AI uncertainty or user-provided missing context.

        Two sub-detectors:
        1. AI uncertainty: assistant messages expressing "I don't know", "I'm not sure", etc.
        2. Missing context: assistant asking for info, then user providing it.

        Args:
            conversations: List of message dicts with 'role' and 'content' keys.

        Returns:
            List of gap dicts with keys: content, source, category.
        """
        if not conversations:
            return []

        gaps: list[dict] = []

        for i, msg in enumerate(conversations):
            content = msg.get("content", "").strip()
            if not content:
                continue

            # --- Sub-detector 1: AI uncertainty in assistant messages ---
            if msg.get("role") == "assistant":
                for pattern in _AI_UNCERTAINTY_PATTERNS:
                    if pattern.search(content):
                        # Try to capture what the user asked (preceding user msg)
                        user_question = ""
                        if i > 0 and conversations[i - 1].get("role") == "user":
                            user_question = conversations[i - 1].get("content", "")

                        gap_text = (
                            f"AI expressed uncertainty: \"{content[:200]}\""
                        )
                        if user_question:
                            gap_text = (
                                f"Knowledge gap detected. User asked: \"{user_question[:200]}\" "
                                f"→ AI expressed uncertainty: \"{content[:200]}\""
                            )

                        gaps.append({
                            "content": gap_text,
                            "source": "conversation",
                            "category": "uncertainty",
                        })
                        break  # One gap entry per message

                # --- Sub-detector 2: AI needing more info ---
                for pattern in _AI_NEEDS_INFO_PATTERNS:
                    if pattern.search(content):
                        # Check if user subsequently provided the info
                        if i + 1 < len(conversations) and conversations[i + 1].get("role") == "user":
                            user_response = conversations[i + 1].get("content", "")
                            gap_text = (
                                f"AI needed more context: \"{content[:200]}\" "
                                f"→ User provided: \"{user_response[:200]}\""
                            )
                            gaps.append({
                                "content": gap_text,
                                "source": "conversation",
                                "category": "missing_context",
                            })
                        break  # One gap entry per message

        return gaps

    # ------------------------------------------------------------------
    # Learning Log Integration
    # ------------------------------------------------------------------

    async def process_corrections(self, conversations: list[dict], log_manager) -> int:
        """Detect corrections and store them as LEARNINGS entries.

        Args:
            conversations: List of message dicts.
            log_manager: LearningLogManager instance.

        Returns:
            Number of correction entries created.
        """
        corrections = self.detect_corrections(conversations)
        for corr in corrections:
            await log_manager.add_entry(
                log_type="LEARNINGS",
                source=corr["source"],
                content=corr["content"],
                category=corr["category"],
                confidence=0.7,
            )
        logger.info(f"ReflectionAgent: Stored {len(corrections)} correction(s) as LEARNINGS entries.")
        return len(corrections)

    async def process_gaps(self, conversations: list[dict], log_manager) -> int:
        """Detect knowledge gaps and store them as ERRORS entries.

        Args:
            conversations: List of message dicts.
            log_manager: LearningLogManager instance.

        Returns:
            Number of gap entries created.
        """
        gaps = self.detect_gaps(conversations)
        for gap in gaps:
            await log_manager.add_entry(
                log_type="ERRORS",
                source=gap["source"],
                content=gap["content"],
                category=gap["category"],
                confidence=0.6,
            )
        logger.info(f"ReflectionAgent: Stored {len(gaps)} knowledge gap(s) as ERRORS entries.")
        return len(gaps)

    async def analyze_conversations(self, conversations: list[dict], log_manager) -> dict:
        """Run both correction and gap detection on conversations.

        This is the main entry point called during the daily reflection cycle.

        Args:
            conversations: List of message dicts.
            log_manager: LearningLogManager instance.

        Returns:
            Dict with counts: {"corrections": int, "gaps": int}.
        """
        correction_count = await self.process_corrections(conversations, log_manager)
        gap_count = await self.process_gaps(conversations, log_manager)
        return {"corrections": correction_count, "gaps": gap_count}

    async def run_daily_reflection(self):
        """Analyze the last 24 hours of commands and conversations to infer user preferences, profile facts, and active projects.

        Also runs correction and gap detection on full conversation threads
        and stores findings in the learning logs system.
        """
        try:
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            
            # Fetch recent terminal commands
            sql_cmds = text("SELECT command_text FROM commands WHERE created_at >= :date AND user_id IS NOT NULL")
            # Fetch recent distinct user requests (conversations)
            sql_conv = text("SELECT content FROM conversations WHERE created_at >= :date AND role = 'user' AND sender_id != 'brain' LIMIT 100")
            
            async with AsyncSessionLocal() as session:
                cmd_res = await session.execute(sql_cmds, {"date": yesterday})
                conv_res = await session.execute(sql_conv, {"date": yesterday})
                
                commands = [r["command_text"] for r in cmd_res.mappings().all()]
                conversations = [r["content"] for r in conv_res.mappings().all()]

            # --- Run correction & gap detection on full conversation threads ---
            try:
                from core.memory.learning_logs import LearningLogManager

                sql_threads = text(
                    "SELECT role, content FROM conversations "
                    "WHERE created_at >= :date ORDER BY created_at ASC LIMIT 500"
                )
                async with AsyncSessionLocal() as session:
                    thread_res = await session.execute(sql_threads, {"date": yesterday})
                    thread_messages = [
                        {"role": r["role"], "content": r["content"]}
                        for r in thread_res.mappings().all()
                    ]

                if thread_messages:
                    log_manager = LearningLogManager()
                    analysis = await self.analyze_conversations(thread_messages, log_manager)
                    logger.info(
                        f"ReflectionAgent: Conversation analysis — "
                        f"{analysis['corrections']} corrections, {analysis['gaps']} gaps detected."
                    )
            except Exception as e:
                logger.error(f"ReflectionAgent: Correction/gap detection failed: {e}")

            if not commands and not conversations:
                logger.info("ReflectionAgent: No new user activity to analyze.")
                return

            # Prepare prompt for Brain
            prompt = f"""You are the Reflection & Memory Consolidation component of Sanaa AI. 
Analyze the user's recent actions and conversations to extract long-term persistent knowledge.

Recent Commands Executed by User:
{json.dumps(commands, indent=2)}

Recent Requests/Conversations from User:
{json.dumps(conversations, indent=2)}

Task: Extract knowledge into exactly three categories:
1. "learned_rules": 1-3 concise operational preferences (e.g., "User prefers reloading Nginx over restarting it").
2. "user_profile": Persistent facts about the user (e.g., "User's working hours are 9-5", "User's name is Banks").
3. "project_context": Active project statuses or deadlines (e.g., "Working on the loan issuance bug", "Migrating Soko to Laravel 11").

Respond ONLY with a valid JSON object matching this schema. If nothing notable can be learned for a category, return an empty list [] for it:
{{
  "learned_rules": ["rule 1"],
  "user_profile": ["fact 1"],
  "project_context": ["project 1"]
}}"""

            # Use a capable model for synthesis
            analysis = await self.brain.think(prompt, complexity="high")
            
            # Extract JSON object
            import re
            match = re.search(r'\{[\s\S]*\}', analysis)
            if match:
                try:
                    extracted = json.loads(match.group())
                    
                    from core.database import SystemKnowledge, AgentMemory
                    from core.memory.manager import MemoryManager
                    from sqlalchemy import update
                    from sqlalchemy.dialects.postgresql import insert
                    
                    memory_manager = MemoryManager()
                    
                    async with AsyncSessionLocal() as session:
                        # 1. Learned Rules -> SystemKnowledge (behavior)
                        for idx, rule in enumerate(extracted.get("learned_rules", [])):
                            key = f"learned_preference.{datetime.now().strftime('%Y%m%d%H%M')}.{idx}"
                            stmt = insert(SystemKnowledge).values(
                                domain="behavior", key=key, value=rule, last_verified=datetime.now(timezone.utc)
                            ).on_conflict_do_nothing()
                            await session.execute(stmt)
                            # Also store as embeddable fact
                            await memory_manager.store(content=rule, category="preference", source="reflection_agent")

                        # 2. User Profile -> SystemKnowledge (user_profile)
                        for idx, fact in enumerate(extracted.get("user_profile", [])):
                            key = f"profile_fact.{datetime.now().strftime('%Y%m%d%H%M')}.{idx}"
                            stmt = insert(SystemKnowledge).values(
                                domain="user_profile", key=key, value=fact, last_verified=datetime.now(timezone.utc)
                            ).on_conflict_do_nothing()
                            await session.execute(stmt)
                            await memory_manager.store(content=fact, category="fact", source="reflection_agent")

                        # 3. Project Context -> SystemKnowledge (project_context)
                        for idx, proj in enumerate(extracted.get("project_context", [])):
                            key = f"project_fact.{datetime.now().strftime('%Y%m%d%H%M')}.{idx}"
                            stmt = insert(SystemKnowledge).values(
                                domain="project_context", key=key, value=proj, last_verified=datetime.now(timezone.utc)
                            ).on_conflict_do_nothing()
                            await session.execute(stmt)
                            await memory_manager.store(content=proj, category="observation", source="reflection_agent")

                        await session.commit()
                        
                    # Request approvals for suggested skills
                    suggested_skills = extracted.get("suggested_skills", [])
                    for skill_def in suggested_skills:
                        name = skill_def.get("name")
                        desc = skill_def.get("description")
                        if name and desc:
                            await approval_manager.request_approval(
                                action="generate_skill",
                                target=name,
                                details={"skill_description": desc},
                                channels=["dashboard"]
                            )
                        
                    logger.info(f"ReflectionAgent: Learned {len(extracted.get('learned_rules', []))} rules, {len(extracted.get('user_profile', []))} profile facts, {len(extracted.get('project_context', []))} project contexts, suggested {len(suggested_skills)} new skills.")
                except json.JSONDecodeError:
                    logger.error("ReflectionAgent: Failed to parse JSON from LLM output.")
                    
        except Exception as e:
            logger.error(f"ReflectionAgent Failed: {e}")

if __name__ == "__main__":
    import asyncio
    agent = ReflectionAgent()
    asyncio.run(agent.run_daily_reflection())
