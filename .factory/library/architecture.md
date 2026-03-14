# Architecture

Architectural decisions, patterns, and conventions discovered during the mission.

---

## Backend Architecture
- **Pattern:** Monolithic FastAPI with Celery async task queue
- **Entry point:** `backend/core/main.py` (305 lines — app setup, lifespan, middleware). Routes split into 13 APIRouter modules in `backend/core/routes/` (auth, commands, skills, status, channels, intelligence, devices, alerts, sessions, config, workflows, misc, webhooks)
- **Route shared state:** `backend/core/routes/deps.py` — `init_shared_state()` wires all singletons (brain, skill_registry, etc.) during app lifespan startup
- **Brain engine:** `backend/core/brain/engine.py` — 3-tier LLM failover (fast/balanced/powerful) via LiteLLM
- **Provider chain:** Groq -> Anthropic -> OpenRouter -> Ollama (only Groq key configured)
- **Skills:** `backend/skills/{name}/manifest.yaml` + `handler.py` pattern, loaded by `core/skills/loader.py`
- **Memory:** `backend/core/memory/context.py` — pgvector + FTS with RRF fusion
- **Agents:** `backend/core/agents/` — 13 agents (watchdog, healer, reflection, news, report, email, etc.)
- **Database:** SQLAlchemy 2.0 async with asyncpg, 18 tables in PostgreSQL
- **Scheduling:** Celery Beat with 15+ periodic tasks

## Frontend Architecture
- **Pattern:** Laravel 12 + Filament 3.2 admin panel (full-page, not embedded)
- **UI:** Glassmorphic dark theme with custom Tailwind CSS v4
- **Components:** Filament pages + Livewire components (SanaaTerminal, SanaaFab)
- **Backend integration:** `SanaaEngineService` PHP class hitting http://127.0.0.1:8101/api with bearer token
- **Auth:** Filament built-in session auth, SQLite database
- **Design system:** Custom `@theme` block with Sanaa brand colors, glass utilities, premium gradients

## Shared Brain Factory
- **Pattern:** Module-level singleton via `get_shared_brain()` in `core/brain/engine.py`
- **Reset:** `reset_shared_brain()` for test isolation
- **Agent constructors:** All agents accept optional `brain` param: `def __init__(self, brain=None)` → `self.brain = brain or get_shared_brain()`
- **Import convention:** `from core.brain import get_shared_brain` (NOT `from core.brain.engine import Brain`)
- **Remaining direct Brain():** `core/main.py`, `core/intelligence/scanner.py`, `core/intelligence/briefing.py` still use `Brain()` directly

## API Key Encryption
- **Module:** `core/utils/crypto.py` — Fernet symmetric encryption with PBKDF2 key derivation
- **Key derivation:** PBKDF2HMAC (SHA256, 480k iterations) from `app_secret` + fixed salt `b'sanaa-ai-crypto-v1'`
- **Prefix:** Encrypted values prefixed with `enc:v1:` — changing the salt or prefix breaks all encrypted data
- **Transparent:** `SystemKnowledge.get_pref()` auto-decrypts, `.set_pref()` / `.upsert()` auto-encrypt for sensitive keys
- **Sensitive key patterns:** Keys matching `api_key`, `api.key`, `secret`, `smtp_pass`, `imap_pass`

## Security Utilities
- **Module:** `core/utils/sanitize.py` — input validation for subprocess calls
- **Functions:** `sanitize_command_string()`, `sanitize_service_name()`, `sanitize_ip_address()`, `sanitize_file_path()`, `contains_shell_metacharacters()`
- **Rule:** All subprocess calls with user/dynamic input MUST use `shell=False` + argument lists + sanitize helpers

## Skill Scanner Permissions
- **Permission-aware scanning:** Skills declaring `permissions: [shell]` in manifest.yaml get subprocess findings downgraded from critical to warning
- **PERMISSION_ALLOWLIST:** Defined in `core/skills/scanner.py` — maps permissions to allowed patterns
- **Gating:** Manifests can specify `requires.env` and `requires.bins` for conditional loading

## Test Infrastructure
- **pytest config:** `backend/pytest.ini` with `asyncio_mode=auto`
- **sys.path quirk:** `conftest.py` inserts `BACKEND_DIR` into `sys.path` so `core.*` imports resolve
- **DB fixtures:** Use real PostgreSQL via `settings.database_url_async` with rollback for isolation
- **Async fixtures:** Use `@pytest.fixture` (not `@pytest_asyncio.fixture`) — pytest-asyncio auto mode handles it
- **asyncpg safety:** In async cleanup fixtures, create a one-shot engine for teardown operations; do NOT reuse the same engine that ran the test (prevents `InterfaceError: cannot perform operation: another operation is in progress`)

## Conventions
- **Python skills:** Always `manifest.yaml` + `handler.py` in `backend/skills/{skill_name}/`
- **Manifest parameter formats:** Two styles exist (list-style and dict-style) — `parse_manifest()` only handles list-style. 13/33 skills use dict-style. New skills should use list-style.
- **Filament pages:** `app/Filament/Pages/{PageName}.php` with optional Blade view in `resources/views/filament/pages/`
- **Livewire components:** `app/Livewire/` with Blade views in `resources/views/livewire/`
- **API integration:** All backend calls go through `App\Services\SanaaEngineService`
- **Styling:** Tailwind utilities + custom glass/gradient classes, dark theme only
