# User Testing

Testing surface, validation approach, and resource cost classification.

---

## Validation Surface

### API Testing (Primary)
- **Tool:** curl
- **Target:** http://127.0.0.1:8101/api/*
- **Auth:** Bearer token from SANAA_ENGINE_KEY env var
- **Scope:** All backend API endpoints (health, skills, tenants, alerts, etc.)

### UI Testing (Limited)
- **Tool:** agent-browser
- **Target:** https://ai.sanaa.co (production URL via Cloudflare)
- **Scope:** Unauthenticated pages only (login page rendering)
- **Limitation:** Skip authenticated UI testing per user preference

### PHP Testing
- **Tool:** PHPUnit via `php artisan test`
- **Target:** Frontend feature tests and unit tests
- **Scope:** Filament page loading, Livewire component behavior, form submissions
- **Note:** Can test authenticated pages via Laravel test framework (no browser needed)

### Python Testing
- **Tool:** pytest via `/opt/antigravity/venv/bin/python3 -m pytest`
- **Target:** Backend unit and integration tests
- **Scope:** Skills, agents, memory, API routes, security

## Validation Concurrency

### curl-based validators
- **Resource cost:** ~5MB RAM each, negligible CPU
- **Max concurrent:** 5
- **Rationale:** Low overhead, safe on resource-constrained system

### agent-browser validators
- **Resource cost:** ~300-500MB RAM each, 0.5-1 CPU core
- **Max concurrent:** 1
- **Rationale:** System has only ~5GB available RAM with swap fully used and load avg >8 on 8 cores. Running more than 1 Chromium instance risks OOM.

### Overall max concurrent validators: 2
(1 agent-browser + 1 curl, or 2 curl)

## Known Constraints
- Frontend only reachable via HTTPS at ai.sanaa.co (not localhost:80)
- No authenticated browser testing — validators must use PHPUnit for authenticated page tests
- High system load (avg > 8 on 8 cores) — keep validator processes minimal
- sanaa-cloud.service is crash-looping (pre-existing, ignore)
