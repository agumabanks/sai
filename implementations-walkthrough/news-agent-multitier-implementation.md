# News Agent: Multi-Tier Intelligence Implementation Plan

This plan details the upgrade of the `NewsAgent` to use a multi-tier LLM architecture. 
Tier 1 (Local) will be used for high-speed, low-cost filtering and scoring.
Tier 3 (Groq) will be reserved for high-value executive synthesis.

## Architecture

1.  **Ingestion**: Fetch RSS feeds (increased limit to gather more candidates).
2.  **Tier 1 (Local/Low Complexity)**:
    -   **Action**: Score and classify each article.
    -   **Prompt**: "Analyze this headline/summary. Score relevance (0-10) for East African Business. Return JSON."
    -   **Filter**: Discard articles with score < 7.
3.  **Tier 3 (Groq/High Complexity)**:
    -   **Action**: "Chief Editor" synthesis.
    -   **Input**: Top verified high-signal articles.
    -   **Output**: Structured Executive Briefing + WhatsApp summary.

## Proposed Changes

### [core/agents/news_agent.py](file:///var/www/ai.sanaa.co/core/agents/news_agent.py)

#### [MODIFY] [news_agent.py](file:///var/www/ai.sanaa.co/core/agents/news_agent.py)
- **Method `filter_articles`**:
    -   Iterate through feed entries.
    -   Call `self.brain.think(prompt, complexity="low")`.
    -   Prompt must be optimized for speed and JSON output.
    -   Parse score and filter.
- **Method `get_daily_summary`**:
    -   Remove the "top 3" hard limit.
    -   Fetch more candidates (e.g., top 10 from each feed).
    -   Apply `filter_articles`.
    -   Pass filtered results to the Chief Editor prompt with `complexity="high"`.

## Verification Plan

### Automated Tests
- Run `python3 scripts/test_news_agent.py`.
- Check logs to verify:
    -   "Low complexity" calls for scoring (Tier 1).
    -   "High complexity" call for synthesis (Tier 3).
- Verify the final PDF contains only high-relevance stories.
