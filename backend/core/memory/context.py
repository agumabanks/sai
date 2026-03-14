"""
Context Assembly Pipeline
Builds the LLM context window from: system prompt + memories + knowledge + history.
"""

import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import text

from datetime import datetime
from core.database import AsyncSessionLocal, Conversation, json
from core.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

# Approximate token counts (conservative — 1 token ~ 4 chars)
TOKEN_RATIO = 4


def estimate_tokens(text_str: str) -> int:
    return len(text_str) // TOKEN_RATIO


SYSTEM_PROMPT = """You are Sanaa AI, an autonomous intelligence assistant built by Sanaa.

You help users with system operations, monitoring, intelligence briefings, and general questions.
You can execute skills, check system status, and provide insights.

CAPABILITIES:
- System monitoring: CPU, memory, disk, service status
- 22+ operational skills for automation
- Intelligence briefings and news analysis
- Watchdog alerts and anomaly detection

RULES:
1. For casual messages (greetings, general questions), respond naturally and conversationally.
2. Only invoke skills when the user specifically asks about system state, operations, or data.
3. Be concise and direct. Do not over-explain or run unnecessary checks.
4. If you use a skill, briefly state why before executing.
"""


class ContextAssembler:
    """Builds the messages array for each LLM call, staying within token budget."""

    def __init__(self, memory: MemoryManager, max_context_tokens: int = 8000):
        self.memory = memory
        self.max_tokens = max_context_tokens

    async def assemble(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        channel: str = "web",
        include_history: int = 10,
    ) -> list[dict]:
        """
        Build the context messages in priority order:
        1. System prompt (never trimmed)
        2. Relevant memories (semantic search)
        3. Promoted learnings (recurring patterns from learning logs)
        4. Infrastructure knowledge
        5. Recent conversation history
        6. Current user message
        """
        messages = []
        used_tokens = 0

        # 1. System prompt — always included
        messages.append({"role": "system", "content": SYSTEM_PROMPT})
        used_tokens += estimate_tokens(SYSTEM_PROMPT)

        budget_remaining = self.max_tokens - used_tokens - estimate_tokens(user_message) - 500

        # 2. Relevant memories
        if budget_remaining > 500:
            memories = await self.memory.search(user_message, limit=5)
            if memories:
                memory_lines = []
                for m in memories:
                    conf = f" (confidence: {m['confidence']:.0%})" if m.get("confidence") else ""
                    memory_lines.append(f"- {m['content']}{conf}")
                memory_text = "Relevant knowledge from memory:\n" + "\n".join(memory_lines)
                mem_tokens = estimate_tokens(memory_text)
                if mem_tokens < budget_remaining:
                    messages.append({"role": "system", "content": memory_text})
                    budget_remaining -= mem_tokens

        # 3. Promoted learnings (recurring patterns from learning logs)
        if budget_remaining > 300:
            promoted_text = await self._get_promoted_learnings()
            if promoted_text:
                promo_tokens = estimate_tokens(promoted_text)
                if promo_tokens < budget_remaining:
                    messages.append({"role": "system", "content": promoted_text})
                    budget_remaining -= promo_tokens

        # 4. Infrastructure knowledge
        if budget_remaining > 300:
            knowledge = await self._get_relevant_knowledge(user_message)
            if knowledge:
                know_tokens = estimate_tokens(knowledge)
                if know_tokens < budget_remaining:
                    messages.append({"role": "system", "content": knowledge})
                    budget_remaining -= know_tokens

        # 5. Recent conversation history
        if session_id and budget_remaining > 500:
            history = await self._get_history(session_id, limit=include_history)
            # Add history newest-first until budget exhausted, then reverse
            history_to_add = []
            for msg in reversed(history):
                msg_tokens = estimate_tokens(msg["content"])
                if msg_tokens < budget_remaining:
                    history_to_add.insert(0, msg)
                    budget_remaining -= msg_tokens
                else:
                    break
            messages.extend(history_to_add)

        # 6. Current user message
        messages.append({"role": "user", "content": user_message})

        logger.debug(
            f"Context assembled: {len(messages)} messages, "
            f"~{self.max_tokens - budget_remaining} tokens used"
        )
        return messages

    async def _get_promoted_learnings(self) -> Optional[str]:
        """Fetch promoted learning entries for inclusion in system context."""
        try:
            from core.memory.promotion import PromotionEngine
            engine = PromotionEngine()
            context_text = await engine.get_promoted_context_text()
            return context_text if context_text else None
        except Exception as e:
            logger.warning(f"Failed to fetch promoted learnings: {e}")
            return None

    async def _get_relevant_knowledge(self, query: str) -> Optional[str]:
        """Fetch relevant infrastructure facts, plus user profile and project context from system_knowledge table."""
        # Fetch matching system facts
        sql = text("""
            SELECT domain, key, value
            FROM system_knowledge
            WHERE to_tsvector('english', key || ' ' || value)
                  @@ plainto_tsquery('english', :query)
               OR domain IN ('user_profile', 'project_context')
            ORDER BY
               CASE WHEN domain IN ('user_profile', 'project_context') THEN 0 ELSE 1 END,
               last_verified DESC NULLS LAST
            LIMIT 15
        """)
        async with AsyncSessionLocal() as session:
            result = await session.execute(sql, {"query": query})
            rows = result.mappings().all()

        if not rows:
            return None

        lines = [f"- [{r['domain']}] {r['key']}: {r['value']}" for r in rows]
        return "System & Profile Context:\n" + "\n".join(lines)

    async def _get_history(self, session_id: str, limit: int = 10) -> list[dict]:
        """Get recent conversation history for a session."""
        sql = text("""
            SELECT role, content
            FROM conversations
            WHERE session_id = :session_id
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                sql, {"session_id": session_id, "limit": limit}
            )
            rows = result.mappings().all()

        # Reverse to get chronological order
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def save_turn(
        self,
        session_id: str,
        channel: str,
        sender_id: str,
        role: str,
        content: str,
        sender_name: Optional[str] = None,
        model: Optional[str] = None,
        tool_calls: Optional[list] = None,
    ):
        """Save a conversation turn to the database."""
        await Conversation.create(
            session_id=session_id,
            channel=channel,
            sender_id=sender_id,
            sender_name=sender_name,
            role=role,
            content=content,
            model=model,
            tool_calls=tool_calls,
            token_count=estimate_tokens(content),
        )
