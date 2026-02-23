# Chief Editor News Agent: Implementation Walkthrough

I have upgraded the News Agent to the "Chief Editor" persona, implementing strict editorial rules to curate high-signal intelligence for East African decision-makers. The system now prioritizes strategic signals over general noise.

## Chief Editor Persona Implementation

### "Sanaa Choice" Editorial Logic
- **Objective**: Curate high-signal intelligence for Entreprenuers, Traders, Investors, and Government in Uganda/EAC.
- **Rules Enforced**:
    - **Remove Noise**: Ignore celebrity fluff/lifestyle unless economically relevant.
    - **Prioritize**: Finance, trade, tenders, policy, infrastructure, taxation, mining, energy.
    - **Tone**: Analytical, Executive, Neutral. No marketing/hype.

### Advanced Logic: OpenClaw Implementation

The Sanaa News Agent now incorporates enterprise-grade patterns from the OpenClaw framework:

*   **Watchdog Pattern**: The ingestion pipeline is crash-resistant. Failures in one RSS source (like NilePost or CNBC) are caught and logged as events, allowing the rest of the news to proceed without a system crash.
*   **Event Sourcing (NewsEvent)**: Every major action (Ingestion, Analysis, Synthesis, Delivery) is logged with a unique event ID and metadata, providing a perfect audit trail.
*   **Healer Pattern (Self-Correction)**: If Groq returns malformed JSON during the filtering phase, the agent automatically triggers a "Healer" loop, asking the LLM to fix the formatting before proceeding. This prevents the "empty briefing" bug.

## Current Pipeline Step-by-Step
The LLM prompt has been engineered to produce a strictly structured briefing:
1.  **TOP STRATEGIC SIGNALS**: 3-5 macro signals (No fluff).
2.  **Categorized Stories**:
    -   **Headline**: Executive summary.
    -   **What Happened**: Concise facts.
    -   **Why It Matters**: Business/Strategic impact.
    -   **Signal Level**: **HIGH** / **MEDIUM** / **LOW** (Visual badges implemented).
    -   **Source**: Publication Name.
3.  **Opportunity Watch**: Tenders, contracts, policy openings.
4.  **WHATSAPP VERSION**: Short, sharp bullet points for instant distribution.

## Technical Enhancements

### [news_agent.py](file:///var/www/ai.sanaa.co/core/agents/news_agent.py)
- **Prompt Engineering**: Rewrote the system prompt to enforce the "Chief Editor" rules and output format.
- **HTML Formatting**: 
    - Implemented regex parsers for the new markdown structure.
    - Added **CSS Badges** for "Signal Level" (Red for High, Yellow for Medium, Green for Low).
    - Preserved the clean "Apple Minimalist" aesthetic while adding data density.
- **Bug Fixes**: Corrected `Brain` import and instantiation.

## Verification
- **Test Run**: Successfully generated `Sanaa_Media_News_2026_02_15.pdf`.
- **Content Check**: Verified that the PDF contains specific sections for Strategic Signals, categorized news with signal levels, and the WhatsApp summary.
- **Visual Check**: Confirmed "Signal Level" badges render correctly in the HTML/PDF.
