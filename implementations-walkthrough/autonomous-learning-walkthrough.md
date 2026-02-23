# Sanaa Intelligence Core: Autonomous Self-Learning

I have successfully implemented an autonomous self-learning loop that allows the News Agent to grow its domain knowledge by scanning sibling repositories.

## How it Works

1.  **Autonomous Scanner**: The `IntelligenceScanner` module identifies sibling repositories in `/var/www/` (e.g., `soko`, `fx.sanaa.co`, `sanaa-cloud`).
2.  **Strategic Extraction**: It reads key documentation and uses the Groq 70B model to distill the core business purpose, key terms, and strategic impact areas of each repository.
3.  **Domain Memory**: These insights are persisted in `data/intelligence/domain_context.json`.
4.  **Grounded Synthesis**: The `NewsAgent` now loads this context into its memory. When the **Chief Editor** synthesizes news, it is explicitly instructed to prioritize news that aligns with Sanaa's actual business ecosystem (e.g., e-commerce, FX trading, mobile money).

## Key Components

-   [memory.py](file:///var/www/ai.sanaa.co/core/intelligence/memory.py): Handles persistence of domain knowledge.
-   [scanner.py](file:///var/www/ai.sanaa.co/core/intelligence/scanner.py): The "Eye" of the system that discovers and analyzes repo documentation.
-   [domain_context.json](file:///var/www/ai.sanaa.co/data/intelligence/domain_context.json): The structured "Brain" of the ecosystem knowledge.

## Results

In the latest verification run, the agent successfully:
-   Identified the **Soko** and **FX** platforms.
-   Updated the news briefing to connect global e-commerce trends (Amazon) and regional stability (UN missions) to Sanaa's impact areas.
-   Ensured the "Chief Editor" persona is no longer just a generic journalist, but a **Sanaa-Embedded Strategist**.

This satisfies the requirement for the agent to "self-learn and keep getting better."
