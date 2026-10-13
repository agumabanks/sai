"""
Sanaa AI - LLM Providers and Tiers Configuration
"""

from typing import Dict, List, Any
from core.config import get_settings

settings = get_settings()

# Provider priority in auto mode:
#   PRIMARY  → Groq        (fast, free tier, default for all complexity levels)
#   FALLBACK → OpenRouter  (when Groq is unavailable)
#   LAST RESORT → Ollama/local (only when all cloud providers are unreachable)
#
# This order is enforced by brain_auto_provider_order and _build_model_chain.
# Ollama is NEVER the default — it is only reached after cloud providers fail.

TIERS: Dict[int, Dict[str, Any]] = {
    1: {
        "name": "fast",          # Groq primary, Ollama last-resort
        "max_tokens": 2048,
        "use_for": ["status_check", "simple_query", "format_response", "json_extraction"],
    },
    2: {
        "name": "balanced",      # Groq primary, Ollama last-resort
        "max_tokens": 4096,
        "use_for": ["log_analysis", "email_summary", "moderate_reasoning", "scoring"],
    },
    3: {
        "name": "powerful",      # Groq primary, Ollama last-resort
        "max_tokens": 8192,
        "use_for": ["complex_analysis", "code_review", "planning", "news_synthesis", "security_audit"],
    },
}

class ModelRegistry:
    def __init__(self):
        self.strategy = settings.llm_strategy
        self.active_provider = "auto"  # Auto-selects best available provider based on configured API keys
        self.local_model = f"ollama/{settings.ollama_model}"
        self.models = self._build_model_chain()

    def set_active_provider(self, provider: str):
        """Force a specific provider for this session."""
        self.active_provider = provider
        self.models = self._build_model_chain()

    @staticmethod
    def soldier_model_id() -> str:
        """Canonical model string for the soldier endpoint (openai-compat prefix)."""
        return f"openai/{settings.soldier_model}" if settings.soldier_model else ""

    @staticmethod
    def is_soldier_model(model: str) -> bool:
        """True when this model string belongs to the soldier endpoint."""
        sid = ModelRegistry.soldier_model_id()
        return bool(sid) and model == sid

    def _build_model_chain(self) -> Dict[int, List[str]]:
        """Build model chains based on active provider strategy."""
        self.local_model = f"ollama/{settings.ollama_model}"
        groq_model = f"groq/{settings.groq_model}"
        openrouter_model = f"openrouter/{settings.openrouter_model}"
        anthropic_fast = f"anthropic/{settings.anthropic_model_fast}"
        anthropic_premium = f"anthropic/{settings.anthropic_model_premium}"
        soldier_model = self.soldier_model_id()  # "" when not configured

        # 1. Force Local
        if self.active_provider == "local":
            return {
                1: [self.local_model],
                2: [self.local_model],
                3: [self.local_model]
            }

        # 1b. Force Soldier (self-hosted OpenAI-compat endpoint)
        if self.active_provider == "soldier":
            if soldier_model:
                return {1: [soldier_model], 2: [soldier_model], 3: [soldier_model]}
            # Soldier not configured — fall through to auto
            pass

        # 2. Force Groq
        if self.active_provider == "groq":
            return {
                1: [groq_model],
                2: [groq_model],
                3: [groq_model]
            }

        # 3. Force Claude (source can be Anthropic, Groq, or OpenRouter)
        if self.active_provider == "claude":
            claude_source = (getattr(settings, "brain_claude_source", "anthropic") or "anthropic").lower()
            fallback_order = [claude_source] + [p for p in ("anthropic", "groq", "openrouter") if p != claude_source]

            def chain_for_tier(tier: int) -> List[str]:
                chain: List[str] = []
                for provider in fallback_order:
                    if provider == "anthropic" and settings.anthropic_api_key:
                        anthropic_chain = (
                            [anthropic_fast]
                            if tier == 1
                            else [anthropic_fast, anthropic_premium]
                            if tier == 2
                            else [anthropic_premium, anthropic_fast]
                        )
                        for model in anthropic_chain:
                            if model not in chain:
                                chain.append(model)
                    elif provider == "groq" and settings.groq_api_key:
                        if groq_model not in chain:
                            chain.append(groq_model)
                    elif provider == "openrouter" and settings.openrouter_api_key:
                        if openrouter_model not in chain:
                            chain.append(openrouter_model)
                if self.local_model not in chain:
                    chain.append(self.local_model)
                return chain

            return {1: chain_for_tier(1), 2: chain_for_tier(2), 3: chain_for_tier(3)}

        # 4. Force OpenRouter
        if self.active_provider == "openrouter":
            return {
                1: [openrouter_model],
                2: [openrouter_model],
                3: [openrouter_model]
            }

        # 5. Auto / Hybrid (Default): follow configurable provider order
        provider_order_raw = getattr(settings, "brain_auto_provider_order", "groq,anthropic,openrouter,local") or "groq,anthropic,openrouter,local"
        provider_order = [p.strip().lower() for p in provider_order_raw.split(",") if p.strip()]
        if not provider_order:
            provider_order = ["groq", "anthropic", "openrouter", "local"]

        def provider_models_for_tier(provider: str, tier: int) -> List[str]:
            if provider == "local":
                return [self.local_model]
            if provider == "soldier" and soldier_model and settings.soldier_url:
                # 35B model hosted on Salad.cloud — capable at all tiers
                return [soldier_model]
            if provider == "groq" and settings.groq_api_key:
                return [groq_model]
            if provider == "anthropic" and settings.anthropic_api_key:
                if tier == 1:
                    return [anthropic_fast]
                if tier == 2:
                    return [anthropic_fast, anthropic_premium]
                return [anthropic_premium, anthropic_fast]
            if provider == "openrouter" and settings.openrouter_api_key:
                return [openrouter_model]
            if provider == "openai" and settings.openai_api_key:
                if tier == 1:
                    return ["openai/gpt-4o-mini"]
                if tier == 2:
                    return ["openai/gpt-4o-mini"]
                return ["openai/gpt-4o"]
            return []

        models: Dict[int, List[str]] = {}
        for tier in (1, 2, 3):
            chain: List[str] = []
            for provider in provider_order:
                for model in provider_models_for_tier(provider, tier):
                    if model not in chain:
                        chain.append(model)
            models[tier] = chain or [self.local_model]

        return models

    def get_models_for_tier(self, tier: int) -> List[str]:
        return self.models.get(tier, [self.local_model])
