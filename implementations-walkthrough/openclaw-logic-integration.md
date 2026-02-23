# Sanaa Intelligence Core: OpenClaw Logic Integration

This plan details how we will apply advanced architectural patterns from the **OpenClaw** framework (found in `/opt/antigravity`) to the Sanaa News Agent.

## OpenClaw Logic to Apply

1.  **Crash-Resistant Watchdog**:
    -   Apply the "independent check" pattern to RSS fetching. If one feed fails, it shouldn't block others.
    -   Implement "exponential escalation" for critical failures (e.g., SMTP down).
2.  **Structured Event Sourcing**:
    -   Adopt the `WatchdogEvent` pattern (Hash ID, Category, Severity, Metadata).
    -   Every news briefing becomes a permanent event in the system audit log.
3.  **Self-Correction (Healer Pattern)**:
    -   If Tier 1 filtering returns invalid JSON, the agent will catch the error and use a "Self-Fix" prompt to regenerate it correctly.

## Proposed Changes

### [core/agents/news_agent.py](file:///var/www/ai.sanaa.co/core/agents/news_agent.py)
-   Add `NewsEvent` class.
-   Wrap article ingestion in a crash-resistant loop.
-   Implement `_emit_event` to log events locally or to a database (audit trail).

## Verification Plan

### Automated Tests
-   Run a test with a "corrupt" RSS feed to verify the watchdog continues regardless.
-   Verify `NewsEvents` are generated with unique IDs.
