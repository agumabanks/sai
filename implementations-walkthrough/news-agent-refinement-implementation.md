# Sanaa Intelligence Core: Refinement Plan

This plan details the final refinements to the `NewsAgent` to fully comply with the "Sanaa Intelligence Core" directive.

## Refinements

1.  **Deduplication**: Implement title/URL-based deduplication.
2.  **Batched Tier 1 Analysis**: 
    -   Collect all candidate articles.
    -   Process articles in batches (e.g., 10-15 per call) to avoid Groq RPM rate limits.
    -   Update `_score_article` to `_score_articles_batch`.
3.  **Tier 1 Enhancement (Fast Filtering/Tagging)**:
    -   Score, Tag, and Classify each article in the batch.
    -   Return structured JSON for the entire batch.
4.  **Tier 3 Enhancement (Strategic Synthesis)**:
    -   Utilize Tier 1 metadata for deep business impact analysis.


## Proposed Changes

### [core/agents/news_agent.py](file:///var/www/ai.sanaa.co/core/agents/news_agent.py)

#### [MODIFY] [news_agent.py](file:///var/www/ai.sanaa.co/core/agents/news_agent.py)
-   Refactor `get_daily_summary` to include a deduplication set.
-   Refactor `_score_article` to return a dict `{"score": int, "tags": list, "classification": str}`.
-   Refactor final synthesis prompt in `get_daily_summary`.

## Verification Plan

### Automated Tests
-   Run `python3 scripts/test_news_agent.py`.
-   Verify the logged metadata shows tags being generated.
-   Verify the final PDF content is deep and strategic.
