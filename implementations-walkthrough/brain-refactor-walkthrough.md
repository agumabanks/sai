# System Brain Module Refactor Walkthrough

I have refactored the core intelligence tracking and routing into a dedicated module `core/brain` to enable modular improvements and better management of local vs cloud LLMs.

## Architectural Changes

### New Module Structure: `core/brain/`
- **`__init__.py`**: Exposes the main `Brain` class.
- **`engine.py`**: Contains the core `think` logic, complexity routing, and context assembly.
- **`providers.py`**: Manages the `TIERS` configuration (Local vs Groq/Claude/OpenAI) and builds the model chain.
- **`usage.py`**: Handles database logging of token usage and costs.

### Benefits
- **Separation of Concerns**: Model configuration is now separate from execution logic.
- **Scalability**: Easier to add new providers (like DeepSeek or others) just by editing `providers.py`.
- **Maintainability**: `agents` package is cleaner without the heavy `llm_brain.py` file.

## Verification
- **News Agent Test**: Ran `test_news_agent.py` which successfully initialized the new `Brain`, routed to Groq (Tier 2/3), and delivered the email.
- **Import Check**: Confirmed `NewsAgent`, `EmailAgent`, and `ReportAgent` correctly import `core.brain.Brain`.
