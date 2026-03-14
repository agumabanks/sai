# User Testing Knowledge — Sanaa AI Platform

## Testing Surfaces

### API (curl)
- **Base URL:** `http://127.0.0.1:8101`
- **Authentication:** Bearer token via `Authorization: Bearer $MAC_CLIENT_API_KEY` (from backend .env)
- **Health endpoint (no auth):** `GET /api/health` → 200 JSON `{"status":"ok","service":"Sanaa AI","version":"2.2.0","channels":["web","telegram"]}`
- **Skills endpoint (auth required):** `GET /api/skills` → 200 JSON `{"count": N, "skills": [...]}`
- **Skill run (auth required):** `POST /api/skills/{name}/run` with JSON body

### PHPUnit (Laravel)
- **Command:** `cd /var/www/ai.sanaa.co/frontend && php artisan test`
- **In-memory SQLite** — doesn't need real backend
- **Pre-existing failing tests (ignore):** ExampleTest, LivewireLoginTest, LoginErrorTest

### Backend Tests (pytest)
- **Command:** `cd /var/www/ai.sanaa.co/backend && /opt/antigravity/venv/bin/python3 -m pytest tests/ -v --tb=short -x`
- **Python venv:** `/opt/antigravity/venv/bin/python3`
- **242 tests currently collected**

### Browser (agent-browser)
- Use sparingly — max 1 concurrent instance
- Frontend URL: `https://ai.sanaa.co`
- Login page: `https://ai.sanaa.co/login`

## Validation Concurrency

### curl surface
- **Max concurrent validators:** 2
- **Reasoning:** API is read-mostly for these tests, low resource cost per validator

### pytest surface
- **Max concurrent validators:** 1
- **Reasoning:** Tests may share database state, concurrent pytest runs risk port/DB conflicts

### phpunit surface
- **Max concurrent validators:** 1
- **Reasoning:** Uses in-memory SQLite so isolated, but CPU/memory constrained system

## Flow Validator Guidance: curl

### Isolation Rules
- Each validator uses the same API key for auth: `$MAC_CLIENT_API_KEY` (from backend .env)
- API calls are stateless reads for most foundation assertions
- Validators should NOT modify global state (don't create/delete users, change settings)
- For POST endpoints (skill runs), use non-destructive parameters

### Boundaries
- Only use `http://127.0.0.1:8101` — do not start new services
- Do not restart services during validation
- Do not modify .env or config files

## Flow Validator Guidance: pytest

### Isolation Rules
- Run tests in the backend directory: `cd /var/www/ai.sanaa.co/backend`
- Use the venv: `/opt/antigravity/venv/bin/python3 -m pytest`
- Tests are self-contained with fixtures/mocks
- Only one pytest session at a time

### Boundaries
- Do not modify test files during validation
- Report test results as-is

## Flow Validator Guidance: phpunit

### Isolation Rules
- Run in frontend directory: `cd /var/www/ai.sanaa.co/frontend`
- Uses `php artisan test` with PHPUnit
- In-memory SQLite — no shared state with backend

### Pre-existing Failures (Ignore)
- ExampleTest — missing SQLite migration
- LivewireLoginTest — wrong status code expectation
- LoginErrorTest — wrong status code expectation

### Boundaries
- Do not modify test files during validation
- Report pass/fail for mission-related tests only
