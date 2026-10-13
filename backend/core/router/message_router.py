"""
Message Router — central dispatch between channels and the agent core.

Flow:
    Channel receives raw input → ChannelAdapter.receive_message() → InternalMessage
    → MessageRouter.route() → LLMBrain.think() → response text
    → ChannelAdapter.send_response() → user sees reply
"""

import logging
import time
import hashlib
from typing import Optional

from core.router.internal_message import InternalMessage
from core.channels.base import ChannelAdapter
from core.database import AuditLog, Conversation
from core.config import get_settings
from core.security.sanitizer import InputSanitizer
from core.policies import (
    get_or_create_session_id,
    get_session_policy,
    can_send_response,
)

settings = get_settings()

logger = logging.getLogger(__name__)


class MessageRouter:
    """Routes normalized messages to the agent core and back to channels."""

    def __init__(self, brain, channels: Optional[dict[str, ChannelAdapter]] = None):
        self.brain = brain
        self.channels: dict[str, ChannelAdapter] = channels or {}
        # Per-channel auth: set of allowed sender IDs. Empty set = allow all.
        self._allowed_senders: dict[str, set[str]] = {}
        self.sanitizer = InputSanitizer()

    def register_channel(self, channel: ChannelAdapter):
        """Register a channel adapter."""
        self.channels[channel.channel_id] = channel
        logger.info(f"Channel registered: {channel.channel_id}")

    def set_allowed_senders(self, channel_id: str, sender_ids: set[str]):
        """Set which sender IDs are allowed for a channel. Empty = allow all."""
        self._allowed_senders[channel_id] = sender_ids

    def _is_authorized(self, message: InternalMessage) -> bool:
        """Check if sender is allowed for this channel."""
        allowed = self._allowed_senders.get(message.channel)
        if not allowed:
            return True  # no restrictions configured
        return message.sender_id in allowed

    # ==================== ROUTING ====================

    async def route(self, message: InternalMessage) -> str:
        """
        Process an incoming message end-to-end:
        1. Auth check
        2. Generate session ID
        3. Intercept approval tokens (YES-XXXXXX)
        4. Save user turn
        5. Send to LLM brain
        6. Save assistant turn
        7. Send response back through channel
        8. Audit log
        """
        start = time.monotonic()

        # Auth check
        if not self._is_authorized(message):
            logger.warning(
                f"Unauthorized message from {message.sender_id} on {message.channel}"
            )
            return ""

        # Check for approval tokens
        text = (message.text or "").strip().upper()
        if text.startswith("YES-") and len(text) > 4:
            token = text[4:].strip()
            from core.approvals.manager import manager as approval_manager
            
            # Use channel as 'via'
            if await approval_manager.process_approval(token, via=message.channel):
                reply = f"✅ Approval {token} confirmed."
                channel = self.channels.get(message.channel)
                if channel and channel.is_connected():
                    await channel.send_response(message, reply)
                return reply
            else:
                reply = f"❌ Invalid or expired approval token: {token}."
                channel = self.channels.get(message.channel)
                if channel and channel.is_connected():
                    await channel.send_response(message, reply)
                return reply


        # Session control commands (/new, /reset, /status)
        special = await self._handle_session_commands(message)
        if special is not None:
            return special

        # Ensure session ID
        if not message.session_id:
            message.session_id = await self._derive_session_id(message)

        # Input sanitization — detect prompt injection
        sanitized = self.sanitizer.sanitize(message.text or "", source=message.channel)
        if sanitized.injection_detected:
            logger.warning(
                f"Prompt injection detected from {message.channel}:{message.sender_id} "
                f"score={sanitized.injection_score:.2f} findings={sanitized.findings}"
            )
            try:
                await AuditLog.log(
                    actor=f"{message.channel}:{message.sender_id}",
                    action="message.injection_detected",
                    resource=(message.text or "")[:200],
                    details={
                        "score": sanitized.injection_score,
                        "findings": sanitized.findings,
                        "session_id": message.session_id,
                    },
                    success=False,
                )
            except Exception:
                pass
            # Use sanitized text instead of raw input
            message.text = sanitized.sanitized

        # Save user turn
        from core.memory.context import ContextAssembler
        ctx = self.brain.context_assembler
        await ctx.save_turn(
            session_id=message.session_id,
            channel=message.channel,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            role="user",
            content=message.text,
        )

        # Get response from brain
        sender_role = ""
        if isinstance(message.metadata, dict):
            sender_role = str(message.metadata.get("role") or message.raw.get("role") or "")
        elif isinstance(message.raw, dict):
            sender_role = str(message.raw.get("role") or "")

        response = await self.brain.think(
            prompt=message.text,
            complexity="auto",
            session_id=message.session_id,
            channel=message.channel,
            sender_id=message.sender_id,
            sender_role=sender_role,
        )

        latency_ms = int((time.monotonic() - start) * 1000)

        # Send response back through the originating channel
        channel = self.channels.get(message.channel)
        if channel and channel.is_connected():
            allowed, deny_reason = await can_send_response(message, message.session_id or "")
            if allowed:
                await self._send_chunked(channel, message, response)
            else:
                try:
                    await AuditLog.log(
                        actor=f"{message.channel}:{message.sender_id}",
                        action="message.send_blocked",
                        resource=message.text[:200],
                        details={
                            "session_id": message.session_id,
                            "reason": deny_reason,
                        },
                        success=False,
                    )
                except Exception:
                    pass

        # Audit
        await AuditLog.log(
            actor=f"{message.channel}:{message.sender_id}",
            action="message.routed",
            resource=message.text[:200],
            details={
                "latency_ms": latency_ms,
                "session_id": message.session_id,
            },
            success=True,
        )

        logger.info(
            f"Routed [{message.channel}] {message.sender_id}: "
            f"{message.text[:60]}... → {len(response)} chars ({latency_ms}ms)"
        )

        # Learning log: detect corrections, feature requests, knowledge gaps
        try:
            from core.intelligence.learning_logs import learning_log_manager
            await learning_log_manager.detect_and_log(
                user_message=message.text or "",
                ai_response=response,
                session_id=message.session_id or "",
                channel=message.channel,
            )
        except Exception:
            pass  # Learning detection is best-effort

        return response

    async def route_and_respond(self, message: InternalMessage) -> str:
        """Alias for route() — processes message and sends response back."""
        return await self.route(message)

    # ==================== HELPERS ====================

    async def _derive_session_id(self, message: InternalMessage) -> str:
        """
        Generate or fetch the active session ID based on session policy.
        """
        try:
            return await get_or_create_session_id(message, force_new=False)
        except Exception:
            raw = f"{message.channel}:{message.chat_id}"
            return hashlib.sha256(raw.encode()).hexdigest()[:24]

    async def _handle_session_commands(self, message: InternalMessage) -> Optional[str]:
        text = (message.text or "").strip()
        if not text.startswith("/"):
            return None

        lower = text.lower()
        policy = await get_session_policy()
        reset_triggers = [t.lower() for t in policy.get("reset_triggers", ["/new", "/reset"])]

        if lower == "/status":
            if not message.session_id:
                message.session_id = await self._derive_session_id(message)
            status = (
                f"Session status\n"
                f"- session_id: {message.session_id}\n"
                f"- channel: {message.channel}\n"
                f"- provider: {self.brain.get_current_provider()}\n"
                f"- dm_scope: {policy.get('dm_scope')}\n"
                f"- send_policy_default: {policy.get('send_policy', {}).get('default', 'allow')}"
            )
            channel = self.channels.get(message.channel)
            if channel and channel.is_connected():
                await channel.send_response(message, status)
            return status

        if lower == "/stop":
            reply = "No cancellable in-session background run is active for this session."
            channel = self.channels.get(message.channel)
            if channel and channel.is_connected():
                await channel.send_response(message, reply)
            return reply

        if lower == "/welcomeback" or lower == "/welcome":
            from core.intelligence.briefing import WelcomeBackBriefing
            briefing_gen = WelcomeBackBriefing(self.brain)
            
            # Send an immediate acknowledgement
            channel = self.channels.get(message.channel)
            if channel and channel.is_connected():
                await channel.send_response(message, "Generating your Welcome Back briefing... ⏳")
                
            reply = await briefing_gen.generate_briefing(since_hours=12)
            if channel and channel.is_connected():
                await channel.send_response(message, reply)
            return reply

        if lower.startswith("/compact"):
            message.session_id = await get_or_create_session_id(message, force_new=True)
            reply = (
                "Session compacted by rotating to a fresh session.\n"
                f"- new_session_id: {message.session_id}"
            )
            channel = self.channels.get(message.channel)
            if channel and channel.is_connected():
                await channel.send_response(message, reply)
            return reply

        if lower == "/skills":
            await self.brain.ensure_skills_loaded()
            skill_list = []
            for skill in self.brain.skill_registry._skills.values():
                status = "enabled" if skill.enabled else "disabled"
                skill_list.append(f"  - {skill.name}: {skill.description[:60]} [{status}]")
            reply = f"Available Skills ({len(skill_list)}):\n" + "\n".join(skill_list[:30])
            if len(skill_list) > 30:
                reply += f"\n  ... and {len(skill_list) - 30} more"
            channel = self.channels.get(message.channel)
            if channel and channel.is_connected():
                await channel.send_response(message, reply)
            return reply

        if lower == "/model":
            provider = self.brain.get_current_provider()
            reply = (
                f"Current AI Model:\n"
                f"  Provider: {provider}\n"
                f"  Groq: {settings.groq_model}\n"
                f"  Anthropic Fast: {settings.anthropic_model_fast}\n"
                f"  Anthropic Premium: {settings.anthropic_model_premium}\n"
                f"  Local: {settings.ollama_model}"
            )
            channel = self.channels.get(message.channel)
            if channel and channel.is_connected():
                await channel.send_response(message, reply)
            return reply

        if lower.startswith("/memory"):
            query = text[len("/memory"):].strip()
            if not query:
                reply = "Usage: /memory <search query>\nSearches your AI memory for relevant information."
            else:
                memories = await self.brain.memory.search(query, limit=5)
                if memories:
                    lines = [f"Memory search for '{query}':"]
                    for m in memories:
                        conf = f" ({m['confidence']:.0%})" if m.get('confidence') else ""
                        lines.append(f"  - {m['content'][:150]}{conf}")
                    reply = "\n".join(lines)
                else:
                    reply = f"No memories found for '{query}'."
            channel = self.channels.get(message.channel)
            if channel and channel.is_connected():
                await channel.send_response(message, reply)
            return reply

        if lower == "/help":
            reply = (
                "Sanaa AI Commands:\n"
                "  /new — Start a new session\n"
                "  /reset — Reset current session\n"
                "  /status — Show session status\n"
                "  /skills — List available skills\n"
                "  /model — Show current AI model\n"
                "  /memory <query> — Search memories\n"
                "  /help — Show this help\n"
                "  /compact — Compact session (rotate)\n"
                "  /welcomeback — Get a briefing of what happened\n"
                "  /stop — Cancel running tasks\n"
                "  /learnings — Show recent learning logs\n"
                "  YES-<token> — Approve a pending action"
            )
            channel = self.channels.get(message.channel)
            if channel and channel.is_connected():
                await channel.send_response(message, reply)
            return reply

        if lower == "/learnings":
            try:
                from core.intelligence.learning_logs import learning_log_manager
                stats = await learning_log_manager.get_stats()
                recent = await learning_log_manager.get_learnings(limit=5)
                lines = [
                    f"Learning Logs Summary:",
                    f"  Total: {stats.get('total_learnings', 0)}",
                    f"  Corrections: {stats.get('corrections', 0)}",
                    f"  Feature Requests: {stats.get('feature_requests', 0)}",
                    f"  Knowledge Gaps: {stats.get('knowledge_gaps', 0)}",
                    f"  Errors: {stats.get('errors', 0)}",
                ]
                if recent:
                    lines.append("\nRecent Learnings:")
                    for entry in recent[:5]:
                        lines.append(f"  [{entry.get('category', '?')}] {entry.get('summary', '')[:100]}")
                reply = "\n".join(lines)
            except Exception as e:
                reply = f"Learning logs unavailable: {e}"
            channel = self.channels.get(message.channel)
            if channel and channel.is_connected():
                await channel.send_response(message, reply)
            return reply

        matched_trigger = None
        for trig in reset_triggers:
            if lower == trig or lower.startswith(trig + " "):
                matched_trigger = trig
                break
        if not matched_trigger:
            return None

        # Persistently rotate the route-mapped session for this chat.
        message.session_id = await get_or_create_session_id(message, force_new=True)
        remainder = text[len(matched_trigger):].strip()

        if not remainder:
            reply = f"Started a new session.\n- session_id: {message.session_id}"
            channel = self.channels.get(message.channel)
            if channel and channel.is_connected():
                await channel.send_response(message, reply)
            return reply

        message.text = remainder
        return None

    async def _send_chunked(
        self, channel: ChannelAdapter, message: InternalMessage, response: str
    ):
        """Split long responses into channel-appropriate chunks."""
        max_length = {
            "whatsapp": 4000,
            "telegram": 4000,
            "web": 100_000,
        }.get(message.channel, 4000)

        if len(response) <= max_length:
            await channel.send_response(message, response)
        else:
            chunks = self._split_at_boundaries(response, max_length)
            for chunk in chunks:
                await channel.send_response(message, chunk)

    @staticmethod
    def _split_at_boundaries(text: str, max_length: int) -> list[str]:
        """Split text at paragraph/sentence boundaries to avoid mid-word cuts."""
        chunks = []
        while len(text) > max_length:
            # Try to split at double newline (paragraph)
            split_at = text.rfind("\n\n", 0, max_length)
            if split_at == -1:
                # Try single newline
                split_at = text.rfind("\n", 0, max_length)
            if split_at == -1:
                # Try period + space (sentence)
                split_at = text.rfind(". ", 0, max_length)
                if split_at != -1:
                    split_at += 1  # include the period
            if split_at == -1:
                # Hard cut at space
                split_at = text.rfind(" ", 0, max_length)
            if split_at == -1:
                split_at = max_length

            chunks.append(text[:split_at].rstrip())
            text = text[split_at:].lstrip()

        if text:
            chunks.append(text)
        return chunks

    # ==================== STATUS ====================

    def get_channel_status(self) -> dict:
        """Return connectivity status for all registered channels."""
        status = {
            cid: {
                "connected": ch.is_connected(),
                "channel_id": ch.channel_id,
            }
            for cid, ch in self.channels.items()
        }
        # Inject the active brain provider into the status
        status["active_provider"] = self.brain.get_current_provider()
        return status
