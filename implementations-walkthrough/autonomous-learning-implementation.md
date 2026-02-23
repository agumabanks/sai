# Sanaa Intelligence Core: Autonomous Self-Learning

This plan implements a "Knowledge Extraction" loop that allows the Sanaa News Agent (and other future agents) to learn from the existing codebase and sibling repositories.

## Overview

The agent will autonomously scan sibling repositories (`soko`, `fx.sanaa.co`, etc.) to extract business logic, domain terminology, and strategic goals. This knowledge will be persisted and used to ground all future LLM completions.

## Proposed Changes

### 1. New Intelligence Module
#### [NEW] [scanner.py](file:///var/www/ai.sanaa.co/core/intelligence/scanner.py)
A specialized service that:
- Iterates through `/var/www/` sibling directories.
- Identifies key documentation (`*.md`, `README`, `*audit*`).
- Uses LLM (Tier 1) to extract "Strategic Insights".

#### [NEW] [memory.py](file:///var/www/ai.sanaa.co/core/intelligence/memory.py)
A persistence layer that:
- Stores extracted knowledge in `data/intelligence/domain_context.json`.
- Provides an interface for agents to retrieve "Context Snippets".

### 2. News Agent Integration
#### [MODIFY] [news_agent.py](file:///var/www/ai.sanaa.co/core/agents/news_agent.py)
- Update `get_daily_summary` to load domain context from `memory.py`.
- Inject this context into the Tier 3 prompt to ensure the "Chief Editor" is aware of Sanaa's internal business goals (e.g., "Prioritize news affecting mobile money because Soko relies on it").

## Verification Plan

### Automated Tests
- Create `scripts/test_learning_loop.py`:
    1. Trigger a scan of `soko`.
    2. Verify `domain_context.json` captures "Soko" related business logic.
    3. Run a mock `get_daily_summary` and check if the prompt includes the new context.

### Manual Verification
- View the generated `data/intelligence/domain_context.json` to ensure it contains high-quality, non-hallucinated business intelligence.
