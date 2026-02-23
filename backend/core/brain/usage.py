"""
Sanaa AI - LLM Usage Tracking
"""

import logging
from core.database import LLMUsage, AsyncSessionLocal
from core.brain.providers import TIERS

logger = logging.getLogger(__name__)

async def track_usage(model: str, tier: int, usage, latency_ms: int):
    """Record token usage and estimated cost."""
    try:
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        cost_per_1k = TIERS[tier]["cost_per_1k"]
        cost = (input_tokens + output_tokens) / 1000 * cost_per_1k

        provider = model.split("/")[0] if "/" in model else "unknown"

        async with AsyncSessionLocal() as session:
            entry = LLMUsage(
                model=model,
                provider=provider,
                tier=tier,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
            )
            session.add(entry)
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to track LLM usage: {e}")
