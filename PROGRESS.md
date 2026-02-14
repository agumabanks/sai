# ANTIGRAVITY v2 — Progress Tracker

> Last updated: 2026-02-14
> Cross-reference this against `docs/research/antigravity-v2-blueprint.md` for full specs

---

## OVERALL STATUS

```
Phase 1: Foundation     [######----] 60%  ← Current
Phase 2: Connectivity   [----------]  0%
Phase 3: Intelligence   [----------]  0%
Phase 4: Polish         [----------]  0%
```

---

## CORE INFRASTRUCTURE

| Component | Status | File(s) | Notes |
|-----------|--------|---------|-------|
| FastAPI App | DONE | `core/main.py` | v2 rewrite: SessionMiddleware, proper CORS, htmx+JSON API |
| Pydantic Settings | DONE | `core/config.py` | Validated config from .env, cached singleton |
| Database Models | DONE | `core/database.py` | 11 models (4 original + 7 new) |
| Alembic Migrations | DONE | `migrations/` | Async env.py, first migration applied |
| pgvector Extension | DONE | PostgreSQL | v0.6.0, IVFFlat + GIN indexes on agent_memory |
| Celery Beat | DONE | `core/tasks.py` | 5 scheduled tasks running |
| Systemd Services | DONE | `docs/systemd/*.service` | web, worker, beat — all active |
| .env Configuration | DONE | `.env.example` | Template created (secrets in /opt only) |
| .gitignore | DONE | `.gitignore` | Excludes .env, venv, cloned-repos |
| README | DONE | `README.md` | Full project documentation |

### TODO — Core Infrastructure
- [x] Alembic migrations setup
- [x] PostgreSQL schema upgrade (add pgvector, all new tables)
- [x] Enhanced config validation (pydantic Settings)
- [x] CORS configuration hardening (removed wildcard `*`)
- [ ] Rate limiting middleware
- [ ] Audit logging middleware (table exists, middleware pending)

---

## AGENTS

| Agent | Status | File | What It Does |
|-------|--------|------|-------------|
| LLM Brain | DONE | `core/agents/llm_brain.py` | LiteLLM routing, local/cloud tiering |
| Server Health | DONE | `core/agents/server_health.py` | CPU/RAM/Disk/services/Docker |
| App Monitor | DONE | `core/agents/app_monitor.py` | Laravel log scanning |
| Report Agent | DONE | `core/agents/report_agent.py` | Email alerts + daily reports |
| Email Agent | DONE | `core/agents/email_agent.py` | IMAP inbox monitoring |
| Web Test | DONE | `core/agents/web_test_agent.py` | Playwright uptime testing |
| Device Agent | PARTIAL | `core/agents/device_agent.py` | Receives reports, needs processing |
| News Agent | STUB | `core/agents/news_agent.py` | Needs search API integration |

### TODO — Agents
- [ ] Context Builder agent (assemble context for LLM calls)
- [ ] Tool Executor agent (dispatch tool calls with approval flow)
- [ ] Enhance LLM Brain with failover chain (Tier 1->2->3)
- [ ] Cost tracking per conversation
- [ ] Context window guard (detect overflow, trigger compaction)

---

## CHANNELS

| Channel | Status | File(s) | Notes |
|---------|--------|---------|-------|
| Web Dashboard | DONE | `web/templates/dashboard.html` | v2 rewrite: services panel, htmx commands, recent commands |
| Web Login | DONE | `web/templates/login.html` | Signed cookie sessions (survives restarts) |
| WhatsApp | NOT STARTED | `channels/whatsapp/` | Needs Node.js Baileys sidecar |
| Telegram | NOT STARTED | `channels/telegram/` | Needs python-telegram-bot |

### TODO — Channels
- [ ] Create abstract ChannelAdapter base class
- [ ] Create Message Router
- [ ] Build WhatsApp sidecar (Node.js + Baileys)
- [ ] Build WhatsApp Python adapter
- [ ] Build Telegram bot adapter
- [ ] QR pairing endpoint for WhatsApp
- [ ] Message chunking for long responses
- [ ] Media handling (images, voice notes, documents)

---

## MEMORY SYSTEM

| Component | Status | File(s) | Notes |
|-----------|--------|---------|-------|
| PostgreSQL pgvector | DONE | — | Extension v0.6.0 installed and enabled |
| Agent Memory table | DONE | `core/database.py` | vector(1536), IVFFlat + GIN indexes |
| System Knowledge table | DONE | `core/database.py` | domain+key unique index |
| Conversation History table | DONE | `core/database.py` | session_id + sender indexes |
| Embedding Providers | DONE | `core/memory/embeddings.py` | LiteLLM, Ollama, NullEmbeddings fallback |
| Hybrid Search (Vector + FTS) | DONE | `core/memory/manager.py` | OR-based FTS + pgvector + RRF merge |
| Context Assembly Pipeline | DONE | `core/memory/context.py` | Token-budgeted: prompt + memories + knowledge + history |
| Memory Pruning | DONE | `core/memory/manager.py` | Expiry, confidence decay, low-score removal |
| Memory Stats | DONE | `core/memory/manager.py` | Category counts, embedding coverage |

### TODO — Memory
- [x] Install pgvector extension on PostgreSQL
- [x] Create memory tables with proper indexes
- [x] Implement embedding provider abstraction (OpenAI/Ollama/null)
- [x] Implement hybrid search (vector + FTS + RRF merge)
- [x] Implement context assembly pipeline
- [x] Memory expiry and pruning
- [ ] Auto-extract facts from conversations (needs LLM integration)
- [ ] Memory pruning cron task (code exists, needs Celery task)
- [ ] Wire context assembler into LLM Brain

---

## SKILL/PLUGIN SYSTEM

| Component | Status | Notes |
|-----------|--------|-------|
| Base Skill class | NOT STARTED | Abstract class with permissions |
| Skill Loader | NOT STARTED | Discovery + dynamic loading |
| Skill Scanner | NOT STARTED | Static analysis security check |
| Skill Registry | NOT STARTED | Runtime registry of loaded skills |
| manifest.yaml format | NOT STARTED | Skill metadata format |

### Sanaa-Specific Skills

| Skill | Status | Priority | Description |
|-------|--------|----------|-------------|
| ServerHealth | DONE (as agent) | P0 | Exists as agent, needs skill migration |
| LaravelLogs | DONE (as agent) | P0 | Exists as agent, needs skill migration |
| DatabaseHealth | NOT STARTED | P1 | PG health, slow queries, backups |
| FXMonitor | NOT STARTED | P1 | fx.sanaa.co trading activity |
| CardSystem | NOT STARTED | P1 | cards.sanaa.ug monitoring |
| SokoMarketplace | NOT STARTED | P2 | soko.sanaa.ug orders/listings |
| DebtCollection | NOT STARTED | P2 | Outstanding balances, reminders |
| ClientComms | NOT STARTED | P2 | Email drafting, client summaries |
| Deploy | NOT STARTED | P1 | git pull, composer, migrate, restart |
| SecurityAudit | NOT STARTED | P1 | SSH, firewall, SSL certs |
| WhatsAppCommands | NOT STARTED | P1 | Process WhatsApp commands |
| DailyBriefing | PARTIAL (report_agent) | P0 | Needs enhancement with real intelligence |
| NewsResearch | STUB | P3 | Needs search API key |
| WebTest | DONE (as agent) | P0 | Exists as agent, needs skill migration |

---

## WORKFLOW ENGINE

| Component | Status | Notes |
|-----------|--------|-------|
| Workflow Runtime | NOT STARTED | Celery-based, Lobster-inspired |
| Approval Gates | NOT STARTED | Halt + resume token pattern |
| YAML Workflow Files | NOT STARTED | Step definitions |
| Workflow State Persistence | NOT STARTED | Save/load workflow state (table exists) |

### Planned Workflows
- [ ] `daily_triage.yaml` — Morning email/alert triage
- [ ] `deploy_app.yaml` — Safe application deployment
- [ ] `incident_response.yaml` — Automated incident handling

---

## SECURITY

| Measure | Status | Notes |
|---------|--------|-------|
| Session Auth (web) | DONE | Signed cookies via SessionMiddleware (survives restarts) |
| API Key Auth (devices) | DONE | Bearer token for mac-client |
| CORS Hardened | DONE | Only `https://ai.sanaa.co` (removed `*` wildcard) |
| Audit Log Table | DONE | `audit_log` table with actor/action/resource/IP |
| Input Sanitization | NOT STARTED | Prompt injection detection |
| Content Wrapping | NOT STARTED | Boundary markers for untrusted input |
| Skill Scanner | NOT STARTED | Static analysis before loading |
| Audit Logging Middleware | NOT STARTED | Auto-log every request |
| Credential Store | NOT STARTED | Separated from .env |
| Rate Limiting | NOT STARTED | Per-endpoint limits |
| Network Egress Control | NOT STARTED | Approved domains only |
| PIN Confirmation | NOT STARTED | For destructive WhatsApp commands |
| Command Timeout | PARTIAL | 60s in tasks.py |

---

## DEVICE NODES

| Component | Status | Notes |
|-----------|--------|-------|
| Mac Reporter | DONE | `mac-client/mac-reporter.py` |
| Device API Endpoint | DONE | POST /api/device/report |
| Device Pairing Protocol | NOT STARTED | Secure pairing flow |
| Device Status Dashboard | NOT STARTED | Widget on web dashboard |
| iOS/Android Node | NOT STARTED | Future consideration |

---

## RESEARCH & DOCUMENTATION

| Document | Status | Location |
|----------|--------|----------|
| OpenClaw Architecture Analysis | DONE | `docs/research/analysis-report.md` |
| Antigravity v2 Blueprint | DONE | `docs/research/antigravity-v2-blueprint.md` (2,351 lines) |
| Memory System Spec | DONE | `docs/research/memory-spec.md` |
| Security Hardening Guide | DONE | `docs/research/security-hardening.md` |
| Skills System Spec | DONE | `docs/research/skills-spec.md` |
| WhatsApp Integration Spec | DONE | `docs/research/whatsapp-spec.md` |
| Research Walkthrough | DONE | `docs/research/walkthrough.md` |

### Reference Material (read-only, not in git)
| Repo | Location | Purpose |
|------|----------|---------|
| OpenClaw | `cloned-repos/openclaw-src/` | Gateway, memory, tools, channels |
| ClawHub | `cloned-repos/clawhub-src/` | Skill registry, validation pipeline |
| Lobster | `cloned-repos/lobster-src/` | Workflow engine, approval gates |

---

## KEY METRICS

| Metric | Current | Target |
|--------|---------|--------|
| Total Python files | 17 | ~65 |
| Total lines of code | ~2,000 | ~8,000 |
| Agents/Skills | 8 agents | 14 skills + 8 agents |
| Channels | 1 (web) | 3 (web, WhatsApp, Telegram) |
| Database tables | 12 | 12 (done) |
| Scheduled tasks | 5 | 17 |
| Test coverage | 0% | 60%+ |
| Security measures | 4 | 10+ |
| Memory system | Working (FTS + vector ready) | Fully wired |

---

## DATABASE TABLES

| # | Table | Status | Records |
|---|-------|--------|---------|
| 1 | `logs` | Active | Growing |
| 2 | `commands` | Active | Growing |
| 3 | `device_reports` | Active | Growing |
| 4 | `alerts` | Active | Growing |
| 5 | `agent_memory` | Ready | Empty (needs seeding) |
| 6 | `system_knowledge` | Ready | Empty (needs seeding) |
| 7 | `conversations` | Ready | Empty (needs wiring) |
| 8 | `skill_runs` | Ready | Empty (needs skill system) |
| 9 | `workflow_runs` | Ready | Empty (needs workflow engine) |
| 10 | `audit_log` | Ready | Empty (needs middleware) |
| 11 | `llm_usage` | Ready | Empty (needs tracking) |
| 12 | `alembic_version` | Active | Migration tracking |

---

## DECISION LOG

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-13 | Python/FastAPI stack | Team expertise, async support, LiteLLM compatibility |
| 2026-02-13 | PostgreSQL + pgvector | Scalable vector search, replaces SQLite-vec |
| 2026-02-13 | Node.js Baileys sidecar for WhatsApp | No mature Python WhatsApp Web library |
| 2026-02-13 | No skill marketplace | Security: operator-only skills, reviewed by us |
| 2026-02-13 | Celery for workflows | Already in stack, chains/chords replicate Lobster patterns |
| 2026-02-13 | /opt/antigravity as deployment dir | Separation from git repo at /var/www/ai.sanaa.co |
| 2026-02-14 | Starlette SessionMiddleware | Signed cookies survive restarts, no DB session store needed |
| 2026-02-14 | OR-based FTS queries | Better recall than AND — memory search should match ANY keyword |
| 2026-02-14 | NullEmbeddings fallback | Memory system works FTS-only when no embedding API available |
| 2026-02-14 | Separate vector/FTS query paths | asyncpg can't infer NULL param types — cleaner to branch |

---

## HOW TO USE THIS TRACKER

1. Before starting work, check this file for current status
2. After completing a component, update status to DONE
3. When starting a component, update status to IN PROGRESS
4. Add new decisions to the Decision Log
5. Update Key Metrics periodically
6. Cross-reference the blueprint for technical specifications
