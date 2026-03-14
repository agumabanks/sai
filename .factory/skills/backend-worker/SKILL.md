---
name: backend-worker
description: Python FastAPI backend worker for skills, agents, memory, security, API routes, and tests
---

# Backend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for any feature that modifies the Python FastAPI backend:
- New or modified skills (manifest.yaml + handler.py in backend/skills/)
- Agent improvements (backend/core/agents/)
- Brain/memory system changes (backend/core/brain/, backend/core/memory/)
- API route additions or modifications (backend/core/main.py or new router modules)
- Database model changes (backend/core/database.py)
- Security fixes (backend/core/security/, backend/core/utils/)
- Celery task changes (backend/core/tasks.py)
- Backend test creation (backend/tests/)

## Work Procedure

### 1. Understand the Feature
- Read the feature description, preconditions, expectedBehavior, and verificationSteps carefully
- Read AGENTS.md for mission boundaries and coding conventions
- Read relevant existing code to understand patterns. Key files:
  - `backend/core/main.py` — API routes (being refactored into modules)
  - `backend/core/config.py` — Settings via Pydantic BaseSettings
  - `backend/core/database.py` — SQLAlchemy models
  - `backend/core/brain/engine.py` — Brain LLM engine
  - `backend/core/memory/context.py` — Memory system
  - `backend/core/skills/loader.py` — Skill loading
  - `backend/core/tasks.py` — Celery tasks
- Check `.factory/library/` for relevant knowledge

### 2. Write Tests FIRST (Red Phase)
- Create test file in `backend/tests/` following pytest conventions
- Write tests that cover: primary behavior, edge cases, error handling
- Use `pytest-asyncio` for async tests
- Use `httpx.AsyncClient` with FastAPI TestClient for API endpoint tests
- Run tests to confirm they FAIL: `/opt/antigravity/venv/bin/python3 -m pytest tests/{test_file} -v`
- Tests MUST fail before implementation begins

### 3. Implement the Feature (Green Phase)
- Follow existing code patterns and conventions from AGENTS.md
- For new skills: create `backend/skills/{name}/manifest.yaml` + `handler.py`
- For API routes: use APIRouter pattern, register in main app
- For models: add to `backend/core/database.py`, ensure table creation
- Use async patterns for all DB operations
- NEVER use `subprocess` with `shell=True` on user input
- Always parameterize SQL queries
- Hash passwords with bcrypt
- Encrypt sensitive data before storing

### 4. Make Tests Pass
- Run tests: `/opt/antigravity/venv/bin/python3 -m pytest tests/{test_file} -v`
- Fix implementation until all tests pass
- Run full test suite to check for regressions: `/opt/antigravity/venv/bin/python3 -m pytest tests/ -v --tb=short`

### 5. Manual Verification
- Restart backend if needed: `sudo systemctl restart antigravity-web`
- Verify with curl:
  - `curl -sf http://127.0.0.1:8101/api/health` — confirm API is up
  - Test specific endpoints relevant to the feature
- For skills: verify they appear in `curl http://127.0.0.1:8101/api/skills` (with auth)
- Check logs for errors: `sudo journalctl -u antigravity-web --since "5 min ago" --no-pager | tail -30`

### 6. Cleanup
- Ensure no test processes left running
- Verify backend service is stable after restart

## Example Handoff

```json
{
  "salientSummary": "Implemented social_media skill with manifest.yaml + handler.py supporting create_content and schedule_post actions. Wrote 5 pytest tests (all passing). Verified skill loads via GET /api/skills and executes via POST /api/skills/social_media/run.",
  "whatWasImplemented": "Created backend/skills/social_media/manifest.yaml defining actions (create_content, schedule_post, analytics) with network permissions. Created handler.py with SocialMediaHandler class using Brain for content generation. Added platform-specific templates for Twitter/LinkedIn/Facebook. Registered skill category as 'marketing'.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {
        "command": "/opt/antigravity/venv/bin/python3 -m pytest tests/skills/test_social_media.py -v",
        "exitCode": 0,
        "observation": "5 tests passed: test_skill_loads, test_create_content_twitter, test_create_content_linkedin, test_schedule_post, test_invalid_platform_error"
      },
      {
        "command": "/opt/antigravity/venv/bin/python3 -m pytest tests/ -v --tb=short",
        "exitCode": 0,
        "observation": "Full suite: 23 passed, 0 failed"
      },
      {
        "command": "sudo systemctl restart antigravity-web && sleep 3 && curl -sf http://127.0.0.1:8101/api/health",
        "exitCode": 0,
        "observation": "{\"status\":\"ok\",\"service\":\"Sanaa AI\",\"version\":\"2.2.0\"}"
      },
      {
        "command": "curl -s http://127.0.0.1:8101/api/skills | python3 -m json.tool | grep social_media",
        "exitCode": 0,
        "observation": "social_media skill listed with category 'marketing', status 'enabled'"
      }
    ],
    "interactiveChecks": [
      {
        "action": "POST /api/skills/social_media/run with {\"action\": \"create_content\", \"args\": {\"topic\": \"fintech innovation\", \"platform\": \"twitter\"}}",
        "observed": "200 OK with generated tweet content, appropriate hashtags, under 280 chars"
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "backend/tests/skills/test_social_media.py",
        "cases": [
          { "name": "test_skill_loads", "verifies": "manifest validates and handler imports" },
          { "name": "test_create_content_twitter", "verifies": "generates Twitter content under 280 chars" },
          { "name": "test_create_content_linkedin", "verifies": "generates LinkedIn professional content" },
          { "name": "test_schedule_post", "verifies": "creates scheduled post entry" },
          { "name": "test_invalid_platform_error", "verifies": "returns error for unsupported platform" }
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Feature depends on a database migration that doesn't exist yet
- Existing code has bugs that block this feature (describe specifically)
- The skill manifest format has changed from what's documented
- Cannot restart antigravity-web (service won't come up)
- A precondition listed in the feature is not met
- Tests for other features started failing after your changes (regression)
