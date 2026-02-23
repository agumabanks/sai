# Sanaa Intelligence Core: Multi-Tier News Agent Refinement

I have successfully refined the News Agent to strictly follow the **Sanaa Intelligence Core** multi-tier directive using Groq for all processing tiers.

## Key Enhancements

### 1. Batched Tier 1 Analysis (Token Efficiency)
To handle a larger volume of articles (up to 10 from each of the ~10 feeds) without hitting Groq's RPM (Requests Per Minute) limits, I implemented a **Batched Scoring** system.
- Articles are collected and deduplicated first.
- Candidates are sent to Groq in batches of 15 per call for preliminary tagging, sector classification, and relevance scoring.
- This adheres to the "Token Efficiency Rule" and ensures high-speed processing.

### 2. Intelligent Deduplication
Implemented a title-based deduplication layer to ensure the same story from multiple RSS sources is only processed once, preserving tokens and reducing noise.

### 3. Enhanced Strategic Synthesis (Tier 3)
The final synthesis prompt was updated to utilize the sector tags and classifications generated in Tier 1.
- **Why It Matters**: Now explicitly mandates "Business Impact Analysis" with a focus on East African/EAC implications.
- **Structure**: Strictly follows the TOP STRATEGIC SIGNALS, Categorized Sections, Opportunity Watch, and WhatsApp Version format.

## Verification Results

The full pipeline was verified using `scripts/test_news_agent.py`:
1.  **Ingestion**: Successfully fetched articles from across all defined feeds.
2.  **Deduplication**: Filtered redundant entries correctly.
3.  **Batch Scoring**: Processed all candidates via Groq Tier 1 without rate limits.
4.  **Synthesis**: Generated a high-signal report using Groq Tier 3.
5.  **Output**: PDF generated and email sent successfully.

![Newsletter Generated](file:///var/www/ai.sanaa.co/data/news/Sanaa_Media_News_2026_02_15.pdf)
