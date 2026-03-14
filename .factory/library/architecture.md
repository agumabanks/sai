# Architecture

Architectural decisions, patterns, and conventions discovered during the mission.

---

## Backend Architecture
- **Pattern:** Monolithic FastAPI with Celery async task queue
- **Entry point:** `backend/core/main.py` (currently 2200+ lines, being refactored into APIRouter modules)
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

## Conventions
- **Python skills:** Always `manifest.yaml` + `handler.py` in `backend/skills/{skill_name}/`
- **Filament pages:** `app/Filament/Pages/{PageName}.php` with optional Blade view in `resources/views/filament/pages/`
- **Livewire components:** `app/Livewire/` with Blade views in `resources/views/livewire/`
- **API integration:** All backend calls go through `App\Services\SanaaEngineService`
- **Styling:** Tailwind utilities + custom glass/gradient classes, dark theme only
