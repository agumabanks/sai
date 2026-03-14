# Environment

Environment variables, external dependencies, and setup notes.

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `.factory/services.yaml`).

---

## Python Backend
- **Venv path:** `/opt/antigravity/venv`
- **Python:** 3.12.3
- **Working directory:** `/var/www/ai.sanaa.co/backend`
- **Config:** Pydantic BaseSettings loaded from `/var/www/ai.sanaa.co/backend/.env`
- **Key env vars:** DATABASE_URL, REDIS_URL, GROQ_API_KEY, OLLAMA_BASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_PASSWORD_HASH, SMTP_HOST, SMTP_PORT, SMTP_USER
- **ADMIN_PASSWORD_HASH:** bcrypt hash of admin password; set by `core/utils/migrate_password.py` or auto-computed on startup. If present, login uses bcrypt verification. If absent, falls back to plaintext comparison.
- **Test dependencies:** pytest, pytest-asyncio, pytest-cov, httpx are installed in venv but NOT in requirements.txt. Must be installed manually after venv recreation.

## PHP Frontend
- **Framework:** Laravel 12 + Filament 3.2
- **PHP:** 8.4
- **Working directory:** `/var/www/ai.sanaa.co/frontend`
- **Database:** SQLite at `frontend/database/database.sqlite`
- **Config:** `.env` with APP_URL=https://ai.sanaa.co
- **Backend connection:** `SANAA_ENGINE_URL=http://127.0.0.1:8101` + `SANAA_ENGINE_KEY` bearer token

## External Services
- **SMTP:** mail.undpf.org:587 (TLS), from alert@undpf.org
- **IMAP:** Same server for inbox monitoring
- **Groq API:** Primary LLM provider (llama-3.3-70b-versatile)
- **Ollama:** Local LLM at localhost:11434 (qwen2.5:1.5b, nomic-embed-text)
- **Cloudflare:** CDN/proxy for ai.sanaa.co

## Server
- **OS:** Ubuntu with kernel 6.8.0-101-generic
- **RAM:** 24GB total, ~5GB available, swap 8GB (fully used)
- **CPUs:** 8 cores
- **Disk:** 387GB, 76% used
- **Load:** Consistently high (>8 avg)
