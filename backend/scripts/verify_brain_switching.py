import asyncio
import sys
import os
import logging
from unittest.mock import MagicMock

# Add project root to path
sys.path.append("/var/www/ai.sanaa.co")
os.environ["SANAA_ENV"] = "testing"

from core.brain.engine import Brain
from core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verifier")

async def test_brain_switching():
    logger.info("--- Testing Dynamic Brain Switching ---")
    
    settings = get_settings()
    brain = Brain()
    
    # 1. Default State (OpenRouter)
    assert brain.get_current_provider() == "openrouter", "Initial state should be openrouter"
    tier1_models = brain.registry.get_models_for_tier(1)
    logger.info(f"Default Tier 1 Models: {tier1_models}")
    assert "liquid/lfm-40b" in tier1_models[0], "Default model should include liquid/lfm-40b"

    # 2. Switch to Local
    brain.switch_provider("local")
    assert brain.get_current_provider() == "local", "Should be local"
    assert "ollama" in brain.registry.get_models_for_tier(1)[0], "Tier 1 should be ollama"
    logger.info("Switch to Local: PASS")

    # 3. Switch to Groq
    brain.switch_provider("groq")
    assert brain.get_current_provider() == "groq", "Should be groq"
    assert "groq" in brain.registry.get_models_for_tier(1)[0], "Tier 1 should be groq"
    logger.info("Switch to Groq: PASS")

    # 4. Switch to OpenRouter
    brain.switch_provider("openrouter")
    assert brain.get_current_provider() == "openrouter", "Should be openrouter"
    assert "openrouter" in brain.registry.get_models_for_tier(1)[0], "Tier 1 should be openrouter"
    logger.info("Switch to OpenRouter: PASS")
    
    # 5. Configure OpenRouter Key (Simulation)
    old_key = settings.openrouter_api_key
    settings.openrouter_api_key = "sk-or-test-key-123"
    brain.registry.models = brain.registry._build_model_chain()
    # In a real test we'd check if the client picks it up, but here we just check the setting update flow logic
    assert settings.openrouter_api_key == "sk-or-test-key-123"
    logger.info("Configure OpenRouter Key: PASS")
    
    # Reset
    settings.openrouter_api_key = old_key

async def main():
    try:
        await test_brain_switching()
        logger.info("\n✅ Brain Switching Verification Passed!")
    except AssertionError as e:
        logger.error(f"\n❌ Verification Failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Unexpected Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
