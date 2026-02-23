# News Agent: Chief Editor Implementation Plan

This plan details the upgrade of the `NewsAgent` to the "Chief Editor" persona for Sanaa Media Intelligence. The goal is to curate high-signal intelligence for East African decision-makers, removing noise and focusing on strategic signals.

## Editorial Standard (The "Sanaa Standard")

- **Audience**: Entrepreneurs, Traders, Government, Investors in Uganda/EAC.
- **Focus**: Finance, Policy, Infrastructure, Trade, Tax, Mining, Energy.
- **Tone**: Analytical, Executive, Neutral. No fluff.
- **Structure**:
    - **TOP STRATEGIC SIGNALS**: 3-5 macro signals.
    - **Categorized Stories**:
        - **Headline**: Executive summary.
        - **What Happened**: Concise facts.
        - **Why It Matters**: Business/Strategic impact.
        - **Signal Level**: High/Medium/Low.
        - **Source**: Publication name.
    - **Opportunity Watch**: Tenders, contracts, policy openings.
    - **WHATSAPP VERSION**: Short, sharp bullet points for distribution.

## Proposed Changes

### [core/agents/news_agent.py](file:///var/www/ai.sanaa.co/core/agents/news_agent.py)

#### [MODIFY] [news_agent.py](file:///var/www/ai.sanaa.co/core/agents/news_agent.py)
- **Fix Import**: Change `LinkLLMBrain` (or incorrectly named class) to `Brain` from `core.brain`.
- **Prompt Engineering**:
    - Update `get_daily_summary` system prompt to enforce the "Sanaa Choice" editorial rules.
    - Instruct LLM to output specific markdown headers for easy parsing.
- **HTML Formatting**:
    - Update `_format_summary_to_html` to style specific sections:
        - `## TOP STRATEGIC SIGNALS` -> Highlighted box or bold section.
        - `### [CATEGORY]` -> Section headers.
        - `**Highlight**` -> Bold text.
        - `Signal Level: High` -> Color-coded badges (Red/Orange/Green).
- **WhatsApp Output**:
    - Extract the "WHATSAPP VERSION" section from the LLM output.
    - This section will NOT be in the PDF body but returned/logged separately (or appended at the end if desired, but user asked for it "After generating the full briefing"). We will likely include it in the email body as a separate block or text file, or just log it for now as we don't have a WhatsApp sender yet.

## Verification Plan

### Automated Tests
- Run `python3 scripts/test_news_agent.py` to generate the newsletter.

### Manual Verification
- Check the generated PDF in `/var/www/ai.sanaa.co/data/news/`.
- Verify the content flow: Strategic Signals -> Categories -> Opportunities.
- Verify the tone is "Executive" and not "Marketing".
- Verify the WhatsApp version is generated and logged/printed.
