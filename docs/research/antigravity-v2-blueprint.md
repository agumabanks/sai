# ANTIGRAVITY v2 — Complete Engineering Blueprint

> Version: 2.0 | Last updated: 2026-02-13
> Status: Phase 1 (Foundation) — 40% complete
> Cross-reference: `PROGRESS.md` for implementation tracking

---

## Table of Contents

1. [Vision & Goals](#1-vision--goals)
2. [Core Architecture](#2-core-architecture)
3. [Database Schema](#3-database-schema)
4. [Target File Structure](#4-target-file-structure)
5. [API Specification](#5-api-specification)
6. [Message Router Architecture](#6-message-router-architecture)
7. [LLM Brain — Model Routing](#7-llm-brain--model-routing)
8. [Memory System](#8-memory-system)
9. [Skill/Plugin System](#9-skillplugin-system)
10. [Workflow Engine](#10-workflow-engine)
11. [Security Hardening](#11-security-hardening)
12. [WhatsApp Integration](#12-whatsapp-integration)
13. [Celery Task Schedule](#13-celery-task-schedule)
14. [Implementation Phases](#14-implementation-phases)
15. [SaaS Preparation](#15-saas-preparation)
16. [Monitoring & Observability](#16-monitoring--observability)
17. [Decision Log](#17-decision-log)

---

## 1. Vision & Goals

Antigravity is an autonomous AI operations agent for the **Sanaa fintech platform ecosystem**. It monitors servers, applications, databases, and connected devices across all Sanaa properties. It thinks, acts, learns, and communicates through multiple channels.

### What Antigravity Does

- **Monitors** 5 production web apps (sanaa.co, cards.sanaa.ug, fx.sanaa.co, soko.sanaa.ug, ai.sanaa.co)
- **Detects** infrastructure problems before they become outages (CPU, RAM, disk, SSL, services)
- **Scans** Laravel application logs for error patterns and anomalies
- **Tests** website uptime using headless browser checks (Playwright)
- **Reads** important incoming emails and surfaces actionable items
- **Reports** daily operations briefings at 7 AM EAT via email
- **Accepts** commands via web dashboard, WhatsApp, and Telegram
- **Executes** approved operations (deploy, restart, database queries) with safety gates
- **Learns** from its environment and retains knowledge across sessions
- **Tracks** connected devices (MacBook, phones) for ecosystem awareness

### Design Principles

1. **Python-first**: Everything in Python 3.11+ except the WhatsApp sidecar (Node.js required by Baileys)
2. **PostgreSQL as the brain**: Single database for state, memory, vectors, logs, and workflows
3. **Celery as the backbone**: All async work, scheduled tasks, and workflow execution through Celery
4. **Tiered intelligence**: Local Ollama for cheap tasks, cloud LLMs for complex reasoning
5. **Zero-trust security**: Every action audited, every input sanitized, every tool sandboxed
6. **Channel-agnostic**: Same agent logic regardless of whether the user talks via web, WhatsApp, or Telegram
7. **Operator-only skills**: No marketplace, no community plugins — all skills reviewed and deployed by us

### Reference Architectures

This design is informed by deep study of three open-source projects:

| Project | What We Took | What We Changed |
|---------|-------------|-----------------|
| **OpenClaw** | Gateway pattern, session management, hybrid memory search, tool policy framework, tiered model routing | Replaced TypeScript with Python, replaced SQLite with PostgreSQL, fixed CVE-2026-25253 token exfiltration, added per-tool sandboxing |
| **ClawHub** | Skill manifest format, plugin validation pipeline, lifecycle hooks | Simplified to YAML manifests, removed marketplace (operator-only), added static security scanner |
| **Lobster** | Typed JSON pipelines, approval gates, resume tokens, workflow YAML format | Replaced Node.js SDK with Celery chains, replaced CLI with web/WhatsApp approval, added database state persistence |

---

## 2. Core Architecture

### 2.1 System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        ANTIGRAVITY v2                           │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ Web      │  │ WhatsApp │  │ Telegram │   CHANNELS            │
│  │ Dashboard│  │ (Baileys)│  │ (Bot)    │                       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                      │
│       │              │              │                            │
│       └──────────────┼──────────────┘                           │
│                      │                                          │
│              ┌───────▼───────┐                                  │
│              │ Message Router │  Normalizes all input            │
│              │ (FastAPI)      │  to InternalMessage              │
│              └───────┬───────┘                                  │
│                      │                                          │
│       ┌──────────────┼──────────────┐                           │
│       │              │              │                            │
│  ┌────▼────┐  ┌──────▼─────┐  ┌────▼─────┐                     │
│  │ Auth &  │  │ LLM Brain  │  │ Context  │   CORE               │
│  │ ACL     │  │ (LiteLLM)  │  │ Builder  │                      │
│  └─────────┘  └──────┬─────┘  └──────────┘                     │
│                      │                                          │
│       ┌──────────────┼──────────────┐                           │
│       │              │              │                            │
│  ┌────▼────┐  ┌──────▼─────┐  ┌────▼─────┐                     │
│  │ Tool    │  │ Workflow   │  │ Memory   │   EXECUTION           │
│  │ Executor│  │ Engine     │  │ Manager  │                       │
│  └────┬────┘  └────┬──────┘  └────┬─────┘                      │
│       │            │              │                              │
│  ┌────▼────────────▼──────────────▼─────┐                       │
│  │         Skill Registry               │   SKILLS               │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐    │                       │
│  │  │SrvHp│ │Dploy│ │FXMon│ │SecAd│... │                       │
│  │  └─────┘ └─────┘ └─────┘ └─────┘    │                       │
│  └──────────────────────────────────────┘                       │
│                      │                                          │
│  ┌───────────────────▼──────────────────┐                       │
│  │         PostgreSQL + pgvector        │   STORAGE              │
│  │  logs | memory | workflows | alerts  │                       │
│  └──────────────────────────────────────┘                       │
│                                                                 │
│  ┌──────────────────────────────────────┐                       │
│  │   Celery + Redis (Task Queue)        │   SCHEDULING           │
│  │   Beat scheduler + Worker pool       │                       │
│  └──────────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘

External:
  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ Ollama   │  │ Cloud    │  │ SMTP/    │
  │ (Local)  │  │ LLMs     │  │ IMAP     │
  └──────────┘  └──────────┘  └──────────┘
```

### 2.2 Component Responsibilities

| Component | Responsibility | Key Pattern |
|-----------|---------------|-------------|
| **Message Router** | Receives input from all channels, normalizes to `InternalMessage`, dispatches to agent core | OpenClaw Gateway pattern |
| **Auth & ACL** | Session auth for web, bearer tokens for API, sender allowlists for WhatsApp/Telegram | Zero-trust, per-channel auth |
| **LLM Brain** | Routes queries to appropriate model tier, manages failover chain, tracks token costs | OpenClaw tiered provider pattern |
| **Context Builder** | Assembles system prompt + memories + history + tool results within token budget | OpenClaw session DAG |
| **Tool Executor** | Dispatches tool calls to skills, enforces permissions, sandboxes shell commands | OpenClaw tool policy groups |
| **Workflow Engine** | Executes multi-step workflows with approval gates, saves state between runs | Lobster typed pipelines |
| **Memory Manager** | Hybrid vector+FTS search, context assembly, memory lifecycle management | OpenClaw SQLite-vec → pgvector |
| **Skill Registry** | Discovers, validates, loads, and manages Python skill modules | ClawHub validation pipeline |

### 2.3 Request Flow

```
1. User sends "check server health" via WhatsApp
2. Baileys sidecar receives → forwards to Python via WebSocket
3. WhatsAppAdapter.receive_message() → InternalMessage
4. Message Router checks auth (sender allowlist) → passes to Agent Core
5. Context Builder assembles:
   - System prompt (agent identity)
   - Relevant memories ("server IPs", "last health check")
   - Recent conversation history (last 5 turns)
   - Available tools (server_health skill)
6. LLM Brain routes to Tier 1 (Ollama) — simple status query
7. LLM responds with tool call: server_health.check()
8. Tool Executor validates permission → runs ServerHealthSkill.execute()
9. Skill runs psutil checks, returns structured JSON
10. LLM formats human-readable response
11. Response flows back: Agent → Router → WhatsAppAdapter → Baileys → WhatsApp
12. Memory Manager auto-extracts: "Server CPU was at 23% on 2026-02-13"
13. Action logged to audit table
```

---

## 3. Database Schema

PostgreSQL 16+ with the **pgvector** extension for vector similarity search.

### 3.1 Existing Tables (Phase 1 — Already Implemented)

```sql
-- Logs: General system log entries
CREATE TABLE logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    level VARCHAR(20) NOT NULL,        -- info, warning, error, critical
    source VARCHAR(100) NOT NULL,       -- agent name or system component
    message TEXT NOT NULL,
    details JSONB                       -- structured metadata
);

-- Commands: User commands and agent responses
CREATE TABLE commands (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    user_id VARCHAR(100),              -- who issued it
    channel VARCHAR(50),               -- web, whatsapp, telegram, api
    command TEXT NOT NULL,
    response TEXT,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, done, failed
    thinking TEXT,                      -- LLM reasoning trace
    tools_used JSONB                   -- list of tools invoked
);

-- Device Reports: Health reports from connected devices
CREATE TABLE device_reports (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    device_id VARCHAR(100) NOT NULL,
    device_name VARCHAR(200),
    report JSONB NOT NULL              -- CPU, RAM, disk, battery, etc.
);

-- Alerts: Generated alerts from monitoring
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    severity VARCHAR(20) NOT NULL,     -- info, warning, critical
    source VARCHAR(100) NOT NULL,
    title VARCHAR(500) NOT NULL,
    message TEXT NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMPTZ
);
```

### 3.2 New Tables (Phase 1-3)

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Agent Memory: Long-term knowledge store with vector embeddings
CREATE TABLE agent_memory (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    category VARCHAR(50) NOT NULL,      -- fact, preference, procedure, observation
    content TEXT NOT NULL,               -- the actual knowledge
    embedding vector(1536),             -- OpenAI ada-002 or local embedding
    source VARCHAR(200),                -- where this was learned
    confidence FLOAT DEFAULT 0.5,       -- 0.0 to 1.0
    verified BOOLEAN DEFAULT FALSE,     -- admin verified
    expires_at TIMESTAMPTZ,            -- NULL = never expires
    access_count INTEGER DEFAULT 0,     -- popularity tracking
    last_accessed_at TIMESTAMPTZ,
    metadata JSONB                     -- flexible extra data
);

-- Indexes for hybrid search
CREATE INDEX idx_memory_embedding ON agent_memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_memory_fts ON agent_memory
    USING gin (to_tsvector('english', content));
CREATE INDEX idx_memory_category ON agent_memory (category);
CREATE INDEX idx_memory_expires ON agent_memory (expires_at)
    WHERE expires_at IS NOT NULL;

-- System Knowledge: Infrastructure facts (auto-populated by agents)
CREATE TABLE system_knowledge (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    domain VARCHAR(100) NOT NULL,       -- server, database, application, network
    key VARCHAR(200) NOT NULL,          -- e.g., "cards.sanaa.ug.ip"
    value TEXT NOT NULL,
    value_type VARCHAR(20) DEFAULT 'string',  -- string, number, json, boolean
    source VARCHAR(100) NOT NULL,       -- which agent/skill discovered this
    last_verified TIMESTAMPTZ,
    UNIQUE(domain, key)
);

-- Conversation History: Per-session chat storage
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    channel VARCHAR(50) NOT NULL,
    sender_id VARCHAR(200) NOT NULL,
    sender_name VARCHAR(200),
    role VARCHAR(20) NOT NULL,          -- user, assistant, system
    content TEXT NOT NULL,
    tool_calls JSONB,                  -- tool calls made in this turn
    token_count INTEGER,               -- tokens used
    model VARCHAR(100),                -- which model responded
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_conversations_session ON conversations (session_id, created_at);
CREATE INDEX idx_conversations_sender ON conversations (sender_id, created_at DESC);

-- Skill Runs: Execution log for every skill invocation
CREATE TABLE skill_runs (
    id SERIAL PRIMARY KEY,
    skill_name VARCHAR(100) NOT NULL,
    action VARCHAR(100),
    triggered_by VARCHAR(100),          -- user, schedule, workflow, agent
    input JSONB,
    output JSONB,
    status VARCHAR(20) NOT NULL,        -- running, success, failed, timeout
    error_message TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER
);

CREATE INDEX idx_skill_runs_name ON skill_runs (skill_name, started_at DESC);

-- Workflows: Workflow execution state
CREATE TABLE workflow_runs (
    id SERIAL PRIMARY KEY,
    workflow_name VARCHAR(100) NOT NULL,
    started_by VARCHAR(100) NOT NULL,
    channel VARCHAR(50),
    status VARCHAR(20) NOT NULL,        -- running, paused, completed, failed, cancelled
    current_step INTEGER DEFAULT 0,
    state JSONB NOT NULL DEFAULT '{}',  -- saved pipeline state
    resume_token TEXT,                  -- base64url encoded resume token
    input_args JSONB,
    output JSONB,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    paused_at TIMESTAMPTZ
);

CREATE INDEX idx_workflow_status ON workflow_runs (status)
    WHERE status IN ('running', 'paused');

-- Audit Log: Every significant action recorded
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    actor VARCHAR(200) NOT NULL,        -- user ID, agent name, or "system"
    action VARCHAR(100) NOT NULL,       -- command.execute, skill.run, file.read, etc.
    resource VARCHAR(200),              -- what was acted upon
    channel VARCHAR(50),
    details JSONB,
    ip_address INET,
    success BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_audit_timestamp ON audit_log (timestamp DESC);
CREATE INDEX idx_audit_actor ON audit_log (actor, timestamp DESC);

-- Devices: Registered device inventory (separate from reports)
CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(100) UNIQUE NOT NULL,
    device_name VARCHAR(200),
    device_type VARCHAR(50),            -- macbook, iphone, android, server
    owner VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',  -- pending, paired, active, inactive
    api_key_hash VARCHAR(256),          -- hashed API key for auth
    paired_at TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    metadata JSONB                     -- OS version, model, etc.
);

-- LLM Usage: Token and cost tracking
CREATE TABLE llm_usage (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    model VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,      -- ollama, anthropic, openai
    tier INTEGER NOT NULL,              -- 1=local, 2=cloud_cheap, 3=cloud_premium
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd DECIMAL(10, 6),           -- estimated cost
    session_id UUID,
    channel VARCHAR(50),
    latency_ms INTEGER
);

CREATE INDEX idx_llm_usage_date ON llm_usage (timestamp::date);
```

### 3.3 Entity Relationship Summary

```
conversations ──── session_id ────── commands
      │
      └── sender_id ─── devices.device_id
                              │
                              └── device_reports.device_id

agent_memory (standalone, searched by vector + FTS)
system_knowledge (standalone, keyed by domain + key)
skill_runs ──── triggered by workflows or commands
workflow_runs ──── contains step state, links to skill_runs
audit_log ──── records everything
llm_usage ──── tracks costs per model/provider
alerts ──── generated by skill_runs or scheduled checks
```

---

## 4. Target File Structure

The complete file tree for Antigravity v2 at full implementation:

```
/var/www/ai.sanaa.co/              ← Git repo (development)
/opt/antigravity/                   ← Deployment (production, symlinked or rsynced)

ai.sanaa.co/
├── core/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, routes, middleware
│   ├── config.py                  # Pydantic Settings (validated .env loading)
│   ├── database.py                # SQLAlchemy async engine + models
│   ├── dependencies.py            # FastAPI dependency injection
│   └── agents/
│       ├── __init__.py
│       ├── llm_brain.py           # LiteLLM routing, tiered failover
│       ├── context_builder.py     # Assembles LLM context window
│       ├── server_health.py       # CPU/RAM/Disk/services/Docker
│       ├── app_monitor.py         # Laravel log scanner
│       ├── report_agent.py        # Email alerts + daily reports
│       ├── email_agent.py         # IMAP inbox monitoring
│       ├── web_test_agent.py      # Playwright uptime testing
│       ├── device_agent.py        # Device report processing
│       └── news_agent.py          # News aggregation
├── router/
│   ├── __init__.py
│   ├── message_router.py         # Central message dispatch
│   ├── internal_message.py       # InternalMessage dataclass
│   └── response_formatter.py    # Format responses per channel
├── channels/
│   ├── __init__.py
│   ├── base.py                    # Abstract ChannelAdapter
│   ├── web/
│   │   ├── __init__.py
│   │   └── adapter.py            # Web dashboard channel
│   ├── whatsapp/
│   │   ├── __init__.py
│   │   ├── adapter.py            # WhatsApp channel adapter
│   │   ├── sidecar.py            # Node.js Baileys IPC manager
│   │   ├── media.py              # Media download/upload
│   │   └── sidecar/              # Node.js sidecar app
│   │       ├── package.json
│   │       ├── index.js          # Baileys WebSocket bridge
│   │       └── auth/             # Session auth files (gitignored)
│   └── telegram/
│       ├── __init__.py
│       └── adapter.py            # Telegram bot adapter
├── memory/
│   ├── __init__.py
│   ├── manager.py                 # Memory search manager
│   ├── embeddings.py              # Embedding provider abstraction
│   ├── context_assembler.py       # Builds context for LLM calls
│   ├── pruner.py                  # Expiry and cleanup
│   └── sync.py                    # File → database sync
├── skills/
│   ├── __init__.py
│   ├── base.py                    # BaseSkill abstract class
│   ├── loader.py                  # Skill discovery and loading
│   ├── scanner.py                 # Static analysis security check
│   ├── registry.py                # Runtime skill registry
│   ├── server_health/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── laravel_logs/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── database_health/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── fx_monitor/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── card_system/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── soko_marketplace/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── debt_collection/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── client_comms/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── deploy/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── security_audit/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── whatsapp_commands/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── daily_briefing/
│   │   ├── manifest.yaml
│   │   └── main.py
│   ├── news_research/
│   │   ├── manifest.yaml
│   │   └── main.py
│   └── web_test/
│       ├── manifest.yaml
│       └── main.py
├── workflows/
│   ├── __init__.py
│   ├── engine.py                  # Celery-based workflow runtime
│   ├── approval.py                # Approval gate + resume tokens
│   ├── state.py                   # Workflow state persistence
│   └── definitions/
│       ├── daily_triage.yaml
│       ├── deploy_app.yaml
│       └── incident_response.yaml
├── security/
│   ├── __init__.py
│   ├── auth.py                    # Token/session auth helpers
│   ├── sandbox.py                 # Command execution sandbox
│   ├── audit.py                   # Audit log writer
│   ├── input_sanitizer.py         # Prompt injection detection
│   └── credential_store.py        # Separated credential management
├── devices/
│   ├── __init__.py
│   ├── manager.py                 # Device registration and status
│   ├── pairing.py                 # Device pairing protocol
│   └── reporter.py                # Device health report processing
├── web/
│   ├── templates/
│   │   ├── base.html              # Base template with nav
│   │   ├── dashboard.html         # Main operations dashboard
│   │   ├── login.html             # Authentication page
│   │   ├── skills.html            # Skill management page
│   │   ├── workflows.html         # Workflow monitoring page
│   │   ├── devices.html           # Device status page
│   │   ├── memory.html            # Memory browser page
│   │   └── audit.html             # Audit log viewer
│   └── static/
│       ├── css/
│       └── js/
├── tasks/
│   ├── __init__.py
│   ├── celery_app.py              # Celery configuration
│   ├── scheduled.py               # Beat schedule definitions
│   └── workers.py                 # Task implementations
├── migrations/
│   ├── env.py                     # Alembic environment
│   ├── alembic.ini                # Alembic config
│   └── versions/                  # Migration scripts
├── tests/
│   ├── conftest.py
│   ├── test_agents.py
│   ├── test_channels.py
│   ├── test_memory.py
│   ├── test_skills.py
│   ├── test_workflows.py
│   └── test_security.py
├── mac-client/
│   └── mac-reporter.py            # macOS device reporter
├── docs/
│   ├── research/                  # Architecture specs
│   │   ├── antigravity-v2-blueprint.md  ← This file
│   │   ├── analysis-report.md
│   │   ├── memory-spec.md
│   │   ├── security-hardening.md
│   │   ├── skills-spec.md
│   │   ├── whatsapp-spec.md
│   │   └── walkthrough.md
│   └── systemd/
│       ├── antigravity-web.service
│       ├── antigravity-worker.service
│       └── antigravity-beat.service
├── cloned-repos/                  # Read-only reference (gitignored)
│   ├── openclaw-src/
│   ├── clawhub-src/
│   └── lobster-src/
├── data/                          # Runtime data (gitignored)
├── logs/                          # Runtime logs (gitignored)
├── .env.example
├── .gitignore
├── requirements.txt
├── alembic.ini
├── PROGRESS.md
└── README.md
```

### File Count Targets

| Category | Current | Target |
|----------|---------|--------|
| Core (main, config, database) | 3 | 5 |
| Agents | 8 | 10 |
| Router | 0 | 3 |
| Channels | 0 | 7 |
| Memory | 0 | 5 |
| Skills (framework) | 0 | 4 |
| Skills (implementations) | 0 | 28 (14 skills × 2 files each) |
| Workflows | 0 | 6 |
| Security | 0 | 5 |
| Devices | 0 | 3 |
| Tasks | 1 | 3 |
| Tests | 0 | 7 |
| Web templates | 2 | 8 |
| **Total Python files** | **13** | **~65** |

---

## 5. API Specification

All endpoints are served by FastAPI on `127.0.0.1:8100`, reverse-proxied by Nginx with TLS.

### 5.1 Authentication Endpoints

```
POST /auth/login
  Body: { email: string, password: string }
  Response: Set-Cookie (session) + redirect to /
  Auth: None (public)

POST /auth/logout
  Response: Clear session cookie + redirect to /auth/login
  Auth: Session

GET /auth/me
  Response: { user_id: string, email: string, role: string }
  Auth: Session or Bearer
```

### 5.2 Dashboard

```
GET /
  Response: HTML dashboard page
  Auth: Session (redirect to /auth/login if not authenticated)

GET /api/status
  Response: {
    server: { cpu: float, ram: float, disk: float, uptime: string },
    services: { nginx: string, postgresql: string, redis: string, celery: string },
    alerts: { unacknowledged: int, last_24h: int },
    devices: { active: int, total: int },
    llm: { today_tokens: int, today_cost_usd: float, model_stats: {} }
  }
  Auth: Session or Bearer
```

### 5.3 Command API

```
POST /api/command
  Body: {
    command: string,
    channel?: string,          # "web" (default), "api"
    context?: { key: value }   # additional context for the LLM
  }
  Response: {
    id: int,
    response: string,
    thinking?: string,          # LLM reasoning trace (if enabled)
    tools_used?: string[],      # skills invoked
    model: string,              # which model handled it
    tokens: { input: int, output: int },
    duration_ms: int
  }
  Auth: Session or Bearer
  Rate limit: 10 req/min
```

### 5.4 Device API

```
POST /api/device/report
  Body: {
    device_id: string,
    device_name: string,
    report: {
      cpu_percent: float,
      ram_percent: float,
      disk_percent: float,
      battery_percent?: float,
      os_version: string,
      uptime: string,
      processes: int,
      ...
    }
  }
  Auth: Bearer (device API key)
  Rate limit: 60 req/min

GET /api/devices
  Response: [{ device_id, device_name, device_type, status, last_seen, ... }]
  Auth: Session or Bearer

POST /api/devices/pair
  Body: { device_id: string, device_name: string, device_type: string }
  Response: { pairing_token: string, status: "pending" }
  Auth: Session (admin only)

POST /api/devices/{id}/approve
  Response: { api_key: string, status: "paired" }
  Auth: Session (admin only)
  Note: API key returned once, must be saved by device
```

### 5.5 Skills API

```
GET /api/skills
  Response: [{
    name: string,
    version: string,
    description: string,
    permissions: string[],
    schedule?: string,
    last_run?: { status, timestamp, duration_ms },
    enabled: boolean
  }]
  Auth: Session or Bearer

POST /api/skills/{name}/run
  Body: { action?: string, args?: {} }
  Response: { run_id: int, status: string, output: {} }
  Auth: Session or Bearer
  Rate limit: 5 req/min per skill

GET /api/skills/{name}/status
  Response: { name, enabled, last_run, run_count_24h, avg_duration_ms, error_rate }
  Auth: Session or Bearer
```

### 5.6 Workflows API

```
GET /api/workflows
  Response: [{
    name: string,
    description: string,
    steps: int,
    active_runs: int,
    last_run?: { status, started_at, completed_at }
  }]
  Auth: Session or Bearer

POST /api/workflows/{name}/run
  Body: { args?: {} }
  Response: { run_id: int, status: "running", resume_token?: string }
  Auth: Session or Bearer

POST /api/workflows/{run_id}/approve
  Body: { resume_token: string, approved: boolean, note?: string }
  Response: { status: "running" | "cancelled" }
  Auth: Session or Bearer (must match started_by or be admin)

GET /api/workflows/{run_id}/status
  Response: {
    run_id: int,
    workflow_name: string,
    status: string,
    current_step: int,
    total_steps: int,
    state: {},
    started_at: string,
    completed_at?: string,
    output?: {}
  }
  Auth: Session or Bearer
```

### 5.7 Alerts API

```
GET /api/alerts
  Query: ?severity=critical&acknowledged=false&limit=50&offset=0
  Response: { alerts: [...], total: int }
  Auth: Session or Bearer

POST /api/alerts/{id}/acknowledge
  Body: { note?: string }
  Response: { acknowledged: true, acknowledged_by: string }
  Auth: Session or Bearer

GET /api/alerts/stats
  Response: {
    total_24h: int,
    by_severity: { info: int, warning: int, critical: int },
    by_source: { server_health: int, app_monitor: int, ... },
    unacknowledged: int
  }
  Auth: Session or Bearer
```

### 5.8 Memory API

```
GET /api/memory/search
  Query: ?q=server+ip+cards&limit=10
  Response: [{
    id: int,
    content: string,
    category: string,
    confidence: float,
    source: string,
    relevance_score: float,
    created_at: string
  }]
  Auth: Session or Bearer

POST /api/memory
  Body: { content: string, category: string, source?: string, expires_at?: string }
  Response: { id: int, created_at: string }
  Auth: Session or Bearer

DELETE /api/memory/{id}
  Auth: Session (admin only)

GET /api/memory/stats
  Response: {
    total_memories: int,
    by_category: { fact: int, procedure: int, ... },
    verified: int,
    expiring_soon: int,
    embedding_coverage: float
  }
  Auth: Session or Bearer
```

### 5.9 Channel Endpoints

```
POST /api/channels/whatsapp/pair
  Response: { qr_code: string (base64), session_id: string }
  Auth: Session (admin only)

GET /api/channels/whatsapp/status
  Response: { connected: boolean, phone_number?: string, last_message_at?: string }
  Auth: Session or Bearer

POST /api/channels/telegram/webhook
  Body: Telegram Update object
  Auth: Telegram webhook secret validation
  Note: Registered with Telegram via setWebhook
```

---

## 6. Message Router Architecture

Learned from OpenClaw's gateway pattern — all channels are decoupled from agent logic.

### 6.1 InternalMessage Format

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class MediaAttachment:
    type: str                  # image, video, audio, document, voice
    url: str                   # local path or remote URL
    mime_type: str
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    caption: Optional[str] = None

@dataclass
class InternalMessage:
    id: str                            # unique message ID
    channel: str                       # "web", "whatsapp", "telegram"
    sender_id: str                     # channel-specific user ID
    sender_name: str                   # display name
    text: str                          # message text content
    media: list[MediaAttachment] = field(default_factory=list)
    is_group: bool = False
    group_id: Optional[str] = None
    reply_to: Optional[str] = None     # message ID being replied to
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw: dict = field(default_factory=dict)  # original channel payload
    metadata: dict = field(default_factory=dict)  # routing metadata
```

### 6.2 ChannelAdapter Abstract Base

```python
from abc import ABC, abstractmethod

class ChannelAdapter(ABC):
    """Abstract base for all channel integrations."""

    channel_id: str  # "web", "whatsapp", "telegram"

    @abstractmethod
    async def receive_message(self, raw: dict) -> InternalMessage:
        """Convert raw channel input to InternalMessage."""
        ...

    @abstractmethod
    async def send_response(self, message: InternalMessage, response: str) -> None:
        """Send text response back through the channel."""
        ...

    @abstractmethod
    async def send_media(self, to: str, media_url: str, caption: str = "") -> None:
        """Send media (image, file, voice) through the channel."""
        ...

    async def send_typing(self, chat_id: str, active: bool = True) -> None:
        """Show typing indicator (optional, not all channels support)."""
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection to channel service."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean shutdown."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status."""
        ...
```

### 6.3 Message Router

```python
class MessageRouter:
    """Routes normalized messages to agent core and back to channels."""

    def __init__(self, channels: dict[str, ChannelAdapter], agent_core, auth):
        self.channels = channels
        self.agent_core = agent_core
        self.auth = auth

    async def route(self, message: InternalMessage) -> str:
        """
        1. Validate sender auth (per-channel rules)
        2. Load conversation context
        3. Dispatch to agent core
        4. Format response for channel
        5. Send back through channel adapter
        6. Log to audit trail
        """
        # Auth check
        if not await self.auth.check_channel_access(message.channel, message.sender_id):
            return  # silently ignore unauthorized

        # Get or create session
        session = await self._get_session(message)

        # Dispatch to agent
        response = await self.agent_core.process(message, session)

        # Send response back through channel
        channel = self.channels[message.channel]
        await self._send_chunked(channel, message, response)

        return response

    async def _send_chunked(self, channel, message, response):
        """Split long responses into channel-appropriate chunks."""
        max_length = {
            "whatsapp": 4096,
            "telegram": 4096,
            "web": 100000,  # essentially unlimited
        }.get(message.channel, 4096)

        if len(response) <= max_length:
            await channel.send_response(message, response)
        else:
            chunks = self._split_at_boundaries(response, max_length)
            for chunk in chunks:
                await channel.send_response(message, chunk)
```

---

## 7. LLM Brain — Model Routing

Learned from OpenClaw's tiered provider system with auth profile rotation and failover.

### 7.1 Tiered Intelligence

```
┌─────────────────────────────────────────────────────┐
│                   Query Arrives                      │
│                                                     │
│  Complexity Estimation:                             │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐          │
│  │ Simple  │  │ Moderate │  │ Complex   │          │
│  │ status? │  │ analyze  │  │ plan the  │          │
│  │ restart │  │ this log │  │ migration │          │
│  └────┬────┘  └────┬─────┘  └─────┬─────┘          │
│       │            │              │                  │
│       ▼            ▼              ▼                  │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐          │
│  │ Tier 1  │  │ Tier 2   │  │ Tier 3    │          │
│  │ Ollama  │  │ Haiku/   │  │ Opus/     │          │
│  │ qwen2.5 │  │ GPT-mini │  │ GPT-4o   │          │
│  │ FREE    │  │ ~$0.001  │  │ ~$0.05   │          │
│  └─────────┘  └──────────┘  └───────────┘          │
│                                                     │
│  Failover: Tier 3 fails → Tier 2 → Tier 1          │
└─────────────────────────────────────────────────────┘
```

### 7.2 Model Configuration

```python
TIERS = {
    1: {
        "name": "local",
        "models": [
            {"id": "ollama/qwen2.5:7b", "provider": "ollama", "context": 32768},
        ],
        "max_tokens": 2048,
        "use_for": ["status_check", "simple_query", "format_response"],
        "cost_per_1k_tokens": 0.0,
    },
    2: {
        "name": "cloud_cheap",
        "models": [
            {"id": "claude-haiku-4-5-20251001", "provider": "anthropic", "context": 200000},
            {"id": "gpt-4o-mini", "provider": "openai", "context": 128000},
        ],
        "max_tokens": 4096,
        "use_for": ["log_analysis", "email_summary", "moderate_reasoning"],
        "cost_per_1k_tokens": 0.001,
    },
    3: {
        "name": "cloud_premium",
        "models": [
            {"id": "claude-sonnet-4-5-20250929", "provider": "anthropic", "context": 200000},
            {"id": "gpt-4o", "provider": "openai", "context": 128000},
        ],
        "max_tokens": 8192,
        "use_for": ["complex_analysis", "code_review", "planning", "security_audit"],
        "cost_per_1k_tokens": 0.015,
    },
}
```

### 7.3 Routing Logic

```python
class LLMBrain:
    async def route_and_call(self, prompt: str, context: dict, task_type: str = "auto") -> str:
        """Route to appropriate tier and call LLM with failover."""

        tier = self._determine_tier(prompt, task_type)

        for attempt_tier in range(tier, 0, -1):  # failover: 3→2→1
            models = TIERS[attempt_tier]["models"]
            for model in models:
                try:
                    response = await litellm.acompletion(
                        model=model["id"],
                        messages=context["messages"],
                        max_tokens=TIERS[attempt_tier]["max_tokens"],
                        temperature=0.3,
                        timeout=30,
                    )
                    await self._track_usage(model, response.usage, attempt_tier)
                    return response.choices[0].message.content
                except Exception as e:
                    logger.warning(f"Tier {attempt_tier} model {model['id']} failed: {e}")
                    continue

        return "All models unavailable. Please try again later."

    def _determine_tier(self, prompt: str, task_type: str) -> int:
        """Estimate query complexity to choose starting tier."""
        if task_type != "auto":
            for tier_num, tier_config in TIERS.items():
                if task_type in tier_config["use_for"]:
                    return tier_num

        # Heuristic: token count + keyword analysis
        token_estimate = len(prompt.split()) * 1.3
        complex_keywords = ["analyze", "plan", "review", "audit", "debug", "explain why"]
        simple_keywords = ["status", "check", "restart", "list", "show"]

        if any(kw in prompt.lower() for kw in complex_keywords) or token_estimate > 500:
            return 3
        elif any(kw in prompt.lower() for kw in simple_keywords) and token_estimate < 100:
            return 1
        else:
            return 2
```

### 7.4 Cost Tracking

```python
async def _track_usage(self, model: dict, usage, tier: int):
    """Record token usage and estimated cost."""
    cost = (usage.prompt_tokens + usage.completion_tokens) / 1000 * TIERS[tier]["cost_per_1k_tokens"]

    await db.execute(
        insert(LLMUsage).values(
            model=model["id"],
            provider=model["provider"],
            tier=tier,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_usd=cost,
        )
    )
```

### 7.5 Context Window Guard

```python
async def _check_context_budget(self, messages: list, model: dict) -> list:
    """Ensure messages fit within model's context window."""
    max_context = model["context"]
    budget = max_context - 2048  # reserve for output

    total_tokens = sum(self._estimate_tokens(m) for m in messages)

    if total_tokens <= budget:
        return messages

    # Compaction strategy: keep system + last N turns + summarize older
    system_msg = messages[0]  # always keep system prompt
    recent = messages[-6:]     # keep last 3 exchanges

    if self._estimate_tokens(system_msg) + sum(self._estimate_tokens(m) for m in recent) <= budget:
        # Summarize middle messages
        middle = messages[1:-6]
        summary = await self._summarize_context(middle)
        return [system_msg, {"role": "system", "content": f"Previous context summary: {summary}"}] + recent

    # Extreme case: truncate to just system + last 2 turns
    return [system_msg] + messages[-4:]
```

---

## 8. Memory System

Learned from OpenClaw's SQLite-vec + SOUL.md/MEMORY.md pattern, upgraded to PostgreSQL pgvector.

### 8.1 Hybrid Search (Vector + FTS + RRF)

```python
class MemoryManager:
    """Hybrid memory search combining vector similarity and full-text search."""

    async def search(self, query: str, limit: int = 10, category: str = None) -> list[dict]:
        """
        Reciprocal Rank Fusion (RRF) merge of vector and FTS results.
        RRF score = sum(1 / (k + rank_i)) for each retrieval method
        """
        # Get embedding for query
        query_embedding = await self.embeddings.encode(query)

        # Vector search (cosine similarity via pgvector)
        vector_results = await self._vector_search(query_embedding, limit=limit * 2, category=category)

        # Full-text search (PostgreSQL tsvector)
        fts_results = await self._fts_search(query, limit=limit * 2, category=category)

        # Reciprocal Rank Fusion merge
        k = 60  # RRF constant (standard value)
        scores = {}

        for rank, result in enumerate(vector_results):
            scores[result["id"]] = scores.get(result["id"], 0) + 1 / (k + rank + 1)
            scores[result["id"] + "_data"] = result

        for rank, result in enumerate(fts_results):
            scores[result["id"]] = scores.get(result["id"], 0) + 1 / (k + rank + 1)
            if result["id"] + "_data" not in scores:
                scores[result["id"] + "_data"] = result

        # Sort by RRF score, return top N
        ranked = sorted(
            [(mid, score) for mid, score in scores.items() if not str(mid).endswith("_data")],
            key=lambda x: x[1],
            reverse=True,
        )[:limit]

        return [scores[str(mid) + "_data"] | {"relevance_score": score} for mid, score in ranked]

    async def _vector_search(self, embedding, limit, category=None):
        """Cosine similarity search via pgvector."""
        query = """
            SELECT id, content, category, confidence, source, created_at,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM agent_memory
            WHERE ($2::text IS NULL OR category = $2)
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """
        return await self.db.fetch_all(query, [embedding, category, limit])

    async def _fts_search(self, query_text, limit, category=None):
        """Full-text search via PostgreSQL tsvector."""
        query = """
            SELECT id, content, category, confidence, source, created_at,
                   ts_rank(to_tsvector('english', content), plainto_tsquery('english', $1)) AS rank
            FROM agent_memory
            WHERE to_tsvector('english', content) @@ plainto_tsquery('english', $1)
              AND ($2::text IS NULL OR category = $2)
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY rank DESC
            LIMIT $3
        """
        return await self.db.fetch_all(query, [query_text, category, limit])
```

### 8.2 Embedding Provider Abstraction

```python
class EmbeddingProvider(ABC):
    @abstractmethod
    async def encode(self, text: str) -> list[float]: ...

class OpenAIEmbeddings(EmbeddingProvider):
    """OpenAI text-embedding-ada-002 (1536 dimensions)."""
    async def encode(self, text: str) -> list[float]:
        response = await litellm.aembedding(model="text-embedding-ada-002", input=[text])
        return response.data[0].embedding

class OllamaEmbeddings(EmbeddingProvider):
    """Local Ollama embeddings (e.g., nomic-embed-text, 768 dimensions)."""
    async def encode(self, text: str) -> list[float]:
        response = await litellm.aembedding(model="ollama/nomic-embed-text", input=[text])
        return response.data[0].embedding
```

### 8.3 Context Assembly Pipeline

```python
class ContextAssembler:
    """Builds the context window for each LLM call."""

    TOKEN_BUDGETS = {
        "system_prompt": 1000,     # agent identity + capabilities
        "memories": 2000,          # relevant memories
        "system_knowledge": 500,   # infrastructure facts
        "recent_history": 3000,    # last N conversation turns
        "tool_results": 2000,      # active tool outputs
    }

    async def assemble(self, message: InternalMessage, session) -> list[dict]:
        """
        Priority order (highest first):
        1. System prompt (never trimmed)
        2. Active tool results (needed for current turn)
        3. Recent conversation history (last 5 turns)
        4. Relevant memories (semantic search)
        5. System knowledge (infrastructure facts)
        6. Older history (summarized if needed)
        """
        messages = []

        # 1. System prompt
        messages.append({
            "role": "system",
            "content": self._build_system_prompt(session)
        })

        # 2. Relevant memories
        memories = await self.memory.search(message.text, limit=5)
        if memories:
            memory_text = "\n".join(f"- {m['content']} (confidence: {m['confidence']})" for m in memories)
            messages.append({
                "role": "system",
                "content": f"Relevant knowledge:\n{memory_text}"
            })

        # 3. System knowledge (infrastructure context)
        knowledge = await self._get_relevant_knowledge(message.text)
        if knowledge:
            messages.append({
                "role": "system",
                "content": f"Infrastructure context:\n{knowledge}"
            })

        # 4. Recent history
        history = await self._get_history(session.id, limit=10)
        messages.extend(history)

        # 5. Current message
        messages.append({"role": "user", "content": message.text})

        return messages
```

### 8.4 Auto-Extraction

```python
async def auto_extract_facts(self, conversation: list[dict]):
    """After each conversation, extract key facts for long-term memory."""
    extraction_prompt = """Review this conversation and extract any NEW facts worth remembering.
    Focus on: server IPs, service configurations, user preferences, problem solutions, infrastructure changes.
    Return JSON array: [{"content": "...", "category": "fact|procedure|preference|observation"}]
    Return empty array [] if nothing new to remember."""

    facts_json = await self.llm.route_and_call(
        prompt=extraction_prompt,
        context={"messages": [{"role": "system", "content": extraction_prompt}] + conversation},
        task_type="moderate_reasoning",
    )

    facts = json.loads(facts_json)
    for fact in facts:
        # Check for duplicates via semantic search
        existing = await self.search(fact["content"], limit=1)
        if existing and existing[0]["relevance_score"] > 0.9:
            # Update confidence of existing memory
            await self._bump_confidence(existing[0]["id"])
        else:
            await self.store(fact["content"], fact["category"], source="auto_extraction")
```

### 8.5 Memory Pruning

```python
async def prune(self):
    """Remove expired, low-confidence, and stale memories."""
    # Delete expired
    await self.db.execute("DELETE FROM agent_memory WHERE expires_at < NOW()")

    # Reduce confidence of unaccessed memories (decay)
    await self.db.execute("""
        UPDATE agent_memory
        SET confidence = confidence * 0.95
        WHERE last_accessed_at < NOW() - INTERVAL '30 days'
          AND confidence > 0.1
    """)

    # Delete very low confidence, old memories
    await self.db.execute("""
        DELETE FROM agent_memory
        WHERE confidence < 0.1
          AND created_at < NOW() - INTERVAL '90 days'
          AND verified = FALSE
    """)
```

---

## 9. Skill/Plugin System

Learned from OpenClaw's SKILL.md format and ClawHub's plugin validation pipeline.

### 9.1 Base Skill Class

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class SkillContext:
    """Context provided to every skill execution."""
    triggered_by: str          # "user", "schedule", "workflow", "agent"
    channel: Optional[str]     # which channel triggered this
    sender_id: Optional[str]
    args: dict[str, Any]
    db: Any                    # database session
    memory: Any                # memory manager
    llm: Any                   # LLM brain for AI-powered skills

@dataclass
class SkillResult:
    """Standardized skill output."""
    success: bool
    output: dict[str, Any]     # structured data
    summary: str               # human-readable summary
    alerts: list[dict] = None  # any alerts to raise
    memories: list[dict] = None  # any facts to remember

class BaseSkill(ABC):
    """Abstract base class for all Antigravity skills."""

    name: str
    version: str
    description: str
    permissions: list[str]     # ["shell", "network", "database", "email", "filesystem"]

    @abstractmethod
    async def execute(self, context: SkillContext) -> SkillResult:
        """Main skill execution."""
        ...

    def get_actions(self) -> list[str]:
        """List available actions (for skills with multiple capabilities)."""
        return ["execute"]

    def get_schedule(self) -> Optional[dict]:
        """Return crontab schedule if this skill runs periodically."""
        return None

    def get_tools(self) -> list[dict]:
        """Return tool definitions for LLM function calling."""
        return []
```

### 9.2 Manifest Format (manifest.yaml)

```yaml
# Example: skills/server_health/manifest.yaml
name: server_health
version: "1.0.0"
description: Monitors server CPU, RAM, disk, services, and Docker containers
author: sanaa
permissions:
  - shell      # needs to run shell commands (ps, systemctl)
  - network    # needs to check service ports
schedule:
  cron: "*/5 * * * *"    # every 5 minutes
  action: execute
dependencies:
  python:
    - psutil>=6.0
thresholds:
  cpu_warning: 80
  cpu_critical: 95
  ram_warning: 85
  ram_critical: 95
  disk_warning: 80
  disk_critical: 90
actions:
  - name: execute
    description: Run full server health check
  - name: check_service
    description: Check a specific service status
    args:
      service_name: { type: string, required: true }
```

### 9.3 Skill Loader

```python
class SkillLoader:
    """Discovers and loads skills from the skills directory."""

    def __init__(self, skills_dir: str, scanner: SkillScanner):
        self.skills_dir = skills_dir
        self.scanner = scanner

    async def discover(self) -> list[dict]:
        """Find all valid skill directories."""
        skills = []
        for entry in Path(self.skills_dir).iterdir():
            if entry.is_dir() and (entry / "manifest.yaml").exists():
                manifest = yaml.safe_load((entry / "manifest.yaml").read_text())
                manifest["_path"] = str(entry)
                skills.append(manifest)
        return skills

    async def load(self, skill_path: str) -> BaseSkill:
        """Load a skill after security scanning."""
        # Security scan first
        issues = await self.scanner.scan(skill_path)
        if issues:
            raise SecurityError(f"Skill failed security scan: {issues}")

        # Dynamic import
        spec = importlib.util.spec_from_file_location("skill", f"{skill_path}/main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find the BaseSkill subclass
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, BaseSkill) and attr is not BaseSkill:
                return attr()

        raise ValueError(f"No BaseSkill subclass found in {skill_path}/main.py")
```

### 9.4 Skill Scanner (Static Security Analysis)

```python
class SkillScanner:
    """Scans skill code for prohibited patterns before loading."""

    PROHIBITED_PATTERNS = [
        (r"os\.system\(", "Direct OS command execution (use subprocess with timeout)"),
        (r"subprocess\.(?!run)", "Subprocess without .run() (use subprocess.run with timeout)"),
        (r"eval\(", "eval() is prohibited"),
        (r"exec\(", "exec() is prohibited"),
        (r"__import__\(", "Dynamic imports prohibited"),
        (r"open\(['\"]\.env", "Direct .env file access prohibited"),
        (r"open\(['\"].*credential", "Direct credential file access prohibited"),
        (r"open\(['\"].*secret", "Direct secret file access prohibited"),
        (r"open\(['\"]\/etc\/shadow", "Shadow file access prohibited"),
        (r"socket\.connect", "Raw socket connections prohibited (use httpx/requests)"),
    ]

    ALLOWED_NETWORK_DOMAINS = [
        "sanaa.co", "sanaa.ug",          # Our domains
        "api.anthropic.com",              # Claude API
        "api.openai.com",                 # OpenAI API
        "smtp.gmail.com",                 # Email
        "imap.gmail.com",                 # Email
    ]

    async def scan(self, skill_path: str) -> list[str]:
        """Scan all .py files in skill directory. Returns list of issues."""
        issues = []
        for py_file in Path(skill_path).glob("**/*.py"):
            content = py_file.read_text()
            for pattern, description in self.PROHIBITED_PATTERNS:
                if re.search(pattern, content):
                    issues.append(f"{py_file.name}: {description}")
        return issues
```

### 9.5 The 14 Sanaa-Specific Skills

| # | Skill | Permissions | Schedule | Description |
|---|-------|------------|----------|-------------|
| 1 | `server_health` | shell, network | Every 5 min | CPU/RAM/disk/Docker/systemd services via psutil |
| 2 | `laravel_logs` | filesystem | Every 15 min | Parse `/var/www/*/storage/logs/laravel.log` for errors |
| 3 | `database_health` | database, shell | Every 30 min | pg_stat_activity, slow queries, backup age, replication lag |
| 4 | `fx_monitor` | database, network | Every 15 min | fx.sanaa.co trade volume, open positions, settlement status |
| 5 | `card_system` | database, network | Every 15 min | cards.sanaa.ug card issuance, transaction errors, KYC queue |
| 6 | `soko_marketplace` | database, network | Every hour | soko.sanaa.ug new orders, listings, payment status |
| 7 | `debt_collection` | database, email | Daily 8 AM | Outstanding balances, payment reminders, aging report |
| 8 | `client_comms` | email, network | On demand | Draft client emails, summarize threads, schedule follow-ups |
| 9 | `deploy` | shell, network | On demand | `git pull`, `composer install`, `artisan migrate`, `systemctl restart` |
| 10 | `security_audit` | shell, network | Daily 6 AM | SSH auth.log, UFW status, SSL cert expiry, open ports |
| 11 | `whatsapp_commands` | network | On message | Parse and route WhatsApp-specific command syntax |
| 12 | `daily_briefing` | all | Daily 7 AM | Compile all agent outputs into morning report email |
| 13 | `news_research` | network | Daily 6 AM | Fintech, Uganda, tech news via search API |
| 14 | `web_test` | network | Every 15 min | Playwright headless tests on all 5 Sanaa properties |

---

## 10. Workflow Engine

Learned from Lobster's typed JSON pipelines, approval gates, and resume tokens.

### 10.1 Core Concepts

```
Lobster pattern:
  pipe("step1") → pipe("step2") → approve("Deploy?") → pipe("step3")
                                        │
                                   [HARD STOP]
                                   Save state to DB
                                   Return resume token
                                        │
                            User approves via web/WhatsApp
                                        │
                                   [RESUME]
                                   Load state from DB
                                   Verify resume token
                                   Continue from step3
```

### 10.2 Workflow YAML Format

```yaml
# workflows/definitions/deploy_app.yaml
name: deploy-sanaa-app
description: Safely deploy a Sanaa application with backup and verification
version: "1.0"
args:
  app:
    type: string
    required: true
    description: Application name (e.g., "fx.sanaa.co")
  branch:
    type: string
    default: main

steps:
  - id: pre_check
    skill: web_test
    action: health_check
    args:
      url: "https://${app}"
    description: "Verify app is currently healthy"

  - id: backup
    skill: database_health
    action: backup
    args:
      database: "${app}"
    description: "Create database backup before deploy"

  - id: pull_code
    skill: deploy
    action: git_pull
    args:
      path: "/var/www/${app}"
      branch: "${branch}"
    description: "Pull latest code"

  - id: approve_deploy
    type: approval
    prompt: |
      Deploy ${app} from branch ${branch}?
      Pre-check: ${pre_check.output.status}
      Backup: ${backup.output.backup_file}
      Git changes: ${pull_code.output.commits} new commits
    channels: [web, whatsapp]
    timeout: 3600  # 1 hour to approve

  - id: install_deps
    skill: deploy
    action: composer_install
    args:
      path: "/var/www/${app}"
    condition: "${approve_deploy.approved}"

  - id: migrate
    skill: deploy
    action: migrate
    args:
      path: "/var/www/${app}"
    condition: "${approve_deploy.approved}"

  - id: restart
    skill: deploy
    action: restart_service
    args:
      service: "${app}"
    condition: "${approve_deploy.approved}"

  - id: post_check
    skill: web_test
    action: health_check
    args:
      url: "https://${app}"
    description: "Verify app is healthy after deploy"

  - id: notify
    skill: client_comms
    action: send_notification
    args:
      message: "Deployed ${app}: ${post_check.output.status}"
    condition: "${approve_deploy.approved}"
```

### 10.3 Workflow Engine (Python + Celery)

```python
import base64
import json
from celery import chain

class WorkflowEngine:
    """Executes YAML-defined workflows with approval gates."""

    async def run(self, workflow_name: str, args: dict, started_by: str) -> dict:
        """Start a workflow execution."""
        definition = self._load_definition(workflow_name)
        run = await self._create_run(workflow_name, args, started_by)

        for i, step in enumerate(definition["steps"]):
            run.current_step = i

            # Check condition
            if "condition" in step:
                if not self._evaluate_condition(step["condition"], run.state):
                    run.state[step["id"]] = {"skipped": True}
                    continue

            if step.get("type") == "approval":
                # HARD STOP — save state and return
                run.status = "paused"
                run.resume_token = self._generate_resume_token(run.id, i)
                run.paused_at = datetime.utcnow()
                await self._save_run(run)

                # Send approval request to channels
                await self._request_approval(run, step)
                return {"status": "paused", "resume_token": run.resume_token, "prompt": step["prompt"]}

            else:
                # Execute skill step
                result = await self._execute_step(step, run.state, args)
                run.state[step["id"]] = {"output": result.output, "status": result.success}

                if not result.success:
                    run.status = "failed"
                    run.state[step["id"]]["error"] = result.summary
                    await self._save_run(run)
                    return {"status": "failed", "error": result.summary, "failed_step": step["id"]}

        run.status = "completed"
        run.completed_at = datetime.utcnow()
        await self._save_run(run)
        return {"status": "completed", "output": run.state}

    async def resume(self, run_id: int, resume_token: str, approved: bool) -> dict:
        """Resume a paused workflow after approval."""
        run = await self._load_run(run_id)

        if run.status != "paused":
            raise ValueError(f"Workflow {run_id} is not paused (status: {run.status})")

        if run.resume_token != resume_token:
            raise ValueError("Invalid resume token")

        # Record approval
        step_id = run.state.get("_pending_approval_step")
        run.state[step_id] = {"approved": approved}
        run.status = "running"
        run.resume_token = None

        if not approved:
            run.status = "cancelled"
            await self._save_run(run)
            return {"status": "cancelled"}

        # Continue from next step
        await self._save_run(run)
        return await self._continue_from(run, run.current_step + 1)

    def _generate_resume_token(self, run_id: int, step_index: int) -> str:
        """Generate a base64url resume token (Lobster pattern)."""
        payload = json.dumps({"run_id": run_id, "step": step_index, "ts": time.time()})
        return base64.urlsafe_b64encode(payload.encode()).decode()
```

### 10.4 Planned Workflows

| Workflow | Trigger | Steps | Approval Required |
|----------|---------|-------|-------------------|
| `deploy_app` | On demand | 9 steps | Yes — before install/migrate/restart |
| `daily_triage` | 7 AM EAT | 6 steps | No — fully automated |
| `incident_response` | On critical alert | 7 steps | Yes — before restart/rollback |

---

## 11. Security Hardening

Every OpenClaw vulnerability addressed with a specific countermeasure.

### 11.1 Vulnerability Mitigations

| OpenClaw Vulnerability | Risk | Antigravity Fix |
|----------------------|------|-----------------|
| **CVE-2026-25253**: `gatewayUrl` from query params allows token exfiltration | Critical | Gateway URL **only** from `.env`. All API endpoints validate `Origin` header. No URL params for config. |
| **Default 0.0.0.0 binding** on port 18789 | High | Bind to `127.0.0.1:8100` only. Nginx reverse proxy with TLS handles external. |
| **Skills execute with full OS privileges** | High | Permission-based sandboxing. Shell commands have 60s timeout. Network restricted to approved domains. |
| **No prompt injection protection** on channels | High | All external content wrapped in `<<<EXTERNAL_UNTRUSTED_CONTENT>>>` boundary markers. Pattern detection for jailbreak attempts. |
| **Memory poisoning** via persistent SOUL.md/MEMORY.md | Medium | Memories in DB with source tracking, confidence scores, verified flags. Admin review. Auto-expiry. |
| **Credentials in .env readable by skills** | Medium | Separate credential store. Skills request creds via API with audit logging. No direct file access. |
| **No rate limiting** on any endpoint | Medium | Per-endpoint limits: 60 req/min general, 10 req/min command API, 5 req/min skill trigger. |
| **No audit trail** of agent actions | Medium | Every action logged to `audit_log` table with actor, action, resource, timestamp, IP. |

### 11.2 Input Sanitization

```python
class InputSanitizer:
    """Detect and neutralize prompt injection attempts."""

    INJECTION_PATTERNS = [
        r"ignore (?:all |your )?(?:previous |above )?instructions",
        r"you are now",
        r"new system prompt",
        r"disregard (?:all |your )?(?:previous )?(?:instructions|rules)",
        r"pretend (?:you are|to be)",
        r"act as (?:if|though)",
        r"jailbreak",
        r"DAN mode",
        r"bypass (?:your |all )?(?:safety|security|restrictions)",
    ]

    def sanitize(self, text: str, source: str) -> str:
        """Wrap external content with boundary markers."""
        # Check for injection patterns
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Potential prompt injection from {source}: {text[:100]}")
                # Still process but flag it
                return self._wrap_with_warning(text, source)

        return self._wrap(text, source)

    def _wrap(self, text: str, source: str) -> str:
        return f"<<<EXTERNAL_CONTENT source=\"{source}\">>>\n{text}\n<<<END_EXTERNAL_CONTENT>>>"

    def _wrap_with_warning(self, text: str, source: str) -> str:
        return (
            f"<<<EXTERNAL_UNTRUSTED_CONTENT source=\"{source}\" WARNING=\"potential injection detected\">>>\n"
            f"{text}\n"
            f"<<<END_EXTERNAL_UNTRUSTED_CONTENT>>>"
        )
```

### 11.3 Command Sandbox

```python
class CommandSandbox:
    """Sandboxed shell command execution."""

    BLOCKED_COMMANDS = [
        "rm -rf /", "mkfs", "dd if=", "> /dev/sd",
        "chmod 777", "curl | sh", "wget | sh",
        "cat /etc/shadow", "cat .env",
    ]

    TIMEOUT = 60  # seconds

    async def execute(self, command: str, cwd: str = None, env: dict = None) -> dict:
        """Execute a shell command with safety checks."""
        # Block dangerous commands
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command:
                return {"success": False, "error": f"Blocked command pattern: {blocked}"}

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd or "/opt/antigravity",
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.TIMEOUT)
            return {
                "success": proc.returncode == 0,
                "stdout": stdout.decode()[:10000],  # truncate large output
                "stderr": stderr.decode()[:5000],
                "return_code": proc.returncode,
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {"success": False, "error": f"Command timed out after {self.TIMEOUT}s"}
```

### 11.4 WhatsApp PIN Confirmation

```python
async def require_pin_for_destructive(self, message: InternalMessage, action: str) -> bool:
    """Require PIN confirmation for destructive actions via WhatsApp."""
    DESTRUCTIVE_ACTIONS = ["deploy", "restart", "delete", "migrate", "rollback"]

    if message.channel != "whatsapp":
        return True  # web dashboard has its own confirmation UI

    if action not in DESTRUCTIVE_ACTIONS:
        return True

    # Ask for PIN
    await self.channels["whatsapp"].send_response(
        message,
        f"This action ({action}) requires PIN confirmation.\nReply with your 4-digit PIN:"
    )

    # Wait for PIN response (with 60s timeout)
    pin_response = await self._wait_for_reply(message.sender_id, timeout=60)
    return pin_response and await self._verify_pin(message.sender_id, pin_response.text)
```

---

## 12. WhatsApp Integration

Learned from OpenClaw's Baileys-based channel plugin.

### 12.1 Architecture

```
┌──────────────┐     WebSocket      ┌──────────────────┐     WhatsApp
│ Python       │◄──────────────────►│ Node.js Sidecar  │◄──────────►│ Servers
│ WhatsApp     │  (localhost:3001)  │ (Baileys)         │            │
│ Adapter      │                    │                    │            │
│              │  ← messages.upsert │  ← QR code        │            │
│              │  → sendMessage()   │  → auth state      │            │
└──────────────┘                    └──────────────────┘
```

### 12.2 Node.js Sidecar (Baileys Bridge)

```javascript
// channels/whatsapp/sidecar/index.js
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require("@whiskeysockets/baileys");
const WebSocket = require("ws");

const wss = new WebSocket.Server({ port: 3001, host: "127.0.0.1" });

let sock = null;
let pythonWs = null;

wss.on("connection", (ws) => {
    pythonWs = ws;

    ws.on("message", async (data) => {
        const msg = JSON.parse(data);

        switch (msg.type) {
            case "connect":
                await startBaileys();
                break;
            case "send_message":
                await sock.sendMessage(msg.to, { text: msg.text });
                break;
            case "send_media":
                await sock.sendMessage(msg.to, {
                    [msg.media_type]: { url: msg.url },
                    caption: msg.caption || "",
                });
                break;
        }
    });
});

async function startBaileys() {
    const { state, saveCreds } = await useMultiFileAuthState("./auth");

    sock = makeWASocket({ auth: state, printQRInTerminal: false });

    sock.ev.on("connection.update", (update) => {
        const { connection, qr, lastDisconnect } = update;

        if (qr) {
            pythonWs?.send(JSON.stringify({ type: "qr", data: qr }));
        }

        if (connection === "open") {
            pythonWs?.send(JSON.stringify({ type: "connected" }));
        }

        if (connection === "close") {
            const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
            if (shouldReconnect) setTimeout(startBaileys, 5000);
        }
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("messages.upsert", ({ messages }) => {
        for (const msg of messages) {
            if (!msg.key.fromMe && msg.message) {
                pythonWs?.send(JSON.stringify({
                    type: "message",
                    data: {
                        id: msg.key.id,
                        from: msg.key.remoteJid,
                        participant: msg.key.participant,
                        text: msg.message.conversation
                            || msg.message.extendedTextMessage?.text
                            || "",
                        timestamp: msg.messageTimestamp,
                        raw: msg,
                    },
                }));
            }
        }
    });
}
```

### 12.3 Python WhatsApp Adapter

```python
class WhatsAppAdapter(ChannelAdapter):
    channel_id = "whatsapp"

    def __init__(self, sidecar_url="ws://127.0.0.1:3001", allowed_numbers=None):
        self.sidecar_url = sidecar_url
        self.ws = None
        self.connected = False
        self.allowed_numbers = set(allowed_numbers or [])
        self._message_queue = asyncio.Queue()

    async def connect(self):
        self.ws = await websockets.connect(self.sidecar_url)
        await self.ws.send(json.dumps({"type": "connect"}))
        asyncio.create_task(self._listen())

    async def _listen(self):
        async for raw in self.ws:
            data = json.loads(raw)
            if data["type"] == "message":
                msg = await self.receive_message(data["data"])
                if msg:
                    await self._message_queue.put(msg)
            elif data["type"] == "qr":
                # Store QR for web dashboard display
                self._current_qr = data["data"]
            elif data["type"] == "connected":
                self.connected = True

    async def receive_message(self, raw: dict) -> InternalMessage:
        sender = raw["from"].replace("@s.whatsapp.net", "")

        # Auth: only process from allowed numbers
        if self.allowed_numbers and sender not in self.allowed_numbers:
            return None

        return InternalMessage(
            id=raw["id"],
            channel="whatsapp",
            sender_id=sender,
            sender_name=raw.get("pushName", sender),
            text=raw["text"],
            is_group="@g.us" in raw["from"],
            group_id=raw["from"] if "@g.us" in raw["from"] else None,
            timestamp=datetime.fromtimestamp(raw["timestamp"]),
            raw=raw,
        )

    async def send_response(self, message: InternalMessage, response: str):
        jid = message.raw.get("from", f"{message.sender_id}@s.whatsapp.net")
        await self.ws.send(json.dumps({
            "type": "send_message",
            "to": jid,
            "text": response,
        }))

    async def send_media(self, to: str, media_url: str, caption: str = ""):
        await self.ws.send(json.dumps({
            "type": "send_media",
            "to": f"{to}@s.whatsapp.net",
            "url": media_url,
            "media_type": self._detect_media_type(media_url),
            "caption": caption,
        }))

    def is_connected(self) -> bool:
        return self.connected
```

### 12.4 QR Pairing Flow

```
1. Admin clicks "Connect WhatsApp" on web dashboard
2. POST /api/channels/whatsapp/pair
3. Python tells sidecar: {"type": "connect"}
4. Baileys generates QR code → sends to Python via WebSocket
5. Python stores QR and returns base64 to web dashboard
6. Dashboard renders QR code (auto-refreshes every 20s)
7. Admin scans QR with WhatsApp on phone
8. Baileys fires connection.update with connection="open"
9. Session auth state saved to data/whatsapp/auth/
10. Dashboard shows "Connected" status with phone number
```

---

## 13. Celery Task Schedule

Complete beat schedule for all recurring tasks:

```python
# tasks/scheduled.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # === MONITORING (High Frequency) ===
    "server-health-check": {
        "task": "tasks.workers.server_health_check",
        "schedule": 300,  # every 5 minutes
        "options": {"queue": "monitoring"},
    },
    "app-log-scan": {
        "task": "tasks.workers.app_log_scan",
        "schedule": 900,  # every 15 minutes
        "options": {"queue": "monitoring"},
    },
    "web-uptime-test": {
        "task": "tasks.workers.web_uptime_test",
        "schedule": 900,  # every 15 minutes
        "options": {"queue": "monitoring"},
    },
    "device-stale-check": {
        "task": "tasks.workers.device_stale_check",
        "schedule": 1800,  # every 30 minutes
        "options": {"queue": "monitoring"},
    },

    # === DATA (Medium Frequency) ===
    "email-inbox-check": {
        "task": "tasks.workers.email_inbox_check",
        "schedule": 3600,  # every hour
        "options": {"queue": "data"},
    },
    "fx-monitor": {
        "task": "tasks.workers.fx_monitor",
        "schedule": 900,  # every 15 minutes
        "options": {"queue": "data"},
    },
    "card-system-monitor": {
        "task": "tasks.workers.card_system_monitor",
        "schedule": 900,  # every 15 minutes
        "options": {"queue": "data"},
    },
    "soko-marketplace-monitor": {
        "task": "tasks.workers.soko_marketplace_monitor",
        "schedule": 3600,  # every hour
        "options": {"queue": "data"},
    },

    # === DAILY TASKS ===
    "security-audit": {
        "task": "tasks.workers.security_audit",
        "schedule": crontab(hour=6, minute=0),  # 6 AM EAT
        "options": {"queue": "daily"},
    },
    "news-research": {
        "task": "tasks.workers.news_research",
        "schedule": crontab(hour=6, minute=30),  # 6:30 AM EAT
        "options": {"queue": "daily"},
    },
    "daily-briefing": {
        "task": "tasks.workers.daily_briefing",
        "schedule": crontab(hour=7, minute=0),  # 7 AM EAT
        "options": {"queue": "daily"},
    },
    "debt-collection-report": {
        "task": "tasks.workers.debt_collection_report",
        "schedule": crontab(hour=8, minute=0),  # 8 AM EAT
        "options": {"queue": "daily"},
    },
    "ssl-cert-check": {
        "task": "tasks.workers.ssl_cert_check",
        "schedule": crontab(hour=6, minute=0),  # 6 AM EAT
        "options": {"queue": "daily"},
    },

    # === MAINTENANCE ===
    "memory-sync": {
        "task": "tasks.workers.memory_sync",
        "schedule": 21600,  # every 6 hours
        "options": {"queue": "maintenance"},
    },
    "memory-prune": {
        "task": "tasks.workers.memory_prune",
        "schedule": crontab(hour=2, minute=0),  # 2 AM EAT
        "options": {"queue": "maintenance"},
    },
    "backup-verify": {
        "task": "tasks.workers.backup_verify",
        "schedule": crontab(hour=3, minute=0),  # 3 AM EAT
        "options": {"queue": "maintenance"},
    },
    "database-health": {
        "task": "tasks.workers.database_health",
        "schedule": 1800,  # every 30 minutes
        "options": {"queue": "maintenance"},
    },
}
```

### Task Count Summary

| Category | Tasks | Frequency |
|----------|-------|-----------|
| Monitoring | 4 | 5-30 min |
| Data | 4 | 15 min - 1 hour |
| Daily | 5 | Once per day |
| Maintenance | 4 | 30 min - daily |
| **Total** | **17** | |

---

## 14. Implementation Phases

### Phase 1: Foundation (Current — Target: Week 2)

**Goal**: Solid infrastructure, database, memory, and skill framework.

| Task | Priority | Status | Depends On |
|------|----------|--------|-----------|
| PostgreSQL pgvector setup | P0 | NOT STARTED | — |
| Alembic migrations | P0 | NOT STARTED | pgvector |
| Enhanced database models (all new tables) | P0 | NOT STARTED | Alembic |
| Pydantic Settings config | P1 | NOT STARTED | — |
| Memory system (hybrid search + embeddings) | P0 | NOT STARTED | pgvector, new tables |
| Context assembly pipeline | P0 | NOT STARTED | Memory system |
| BaseSkill class + loader + scanner + registry | P0 | NOT STARTED | — |
| Migrate server_health to skill format | P1 | NOT STARTED | Skill framework |
| Migrate laravel_logs to skill format | P1 | NOT STARTED | Skill framework |
| Migrate web_test to skill format | P1 | NOT STARTED | Skill framework |
| Security: audit logging middleware | P0 | NOT STARTED | New tables |
| Security: input sanitization | P1 | NOT STARTED | — |
| Security: rate limiting | P1 | NOT STARTED | — |
| Enhanced LLM Brain (failover chain) | P1 | NOT STARTED | — |
| LLM cost tracking | P2 | NOT STARTED | New tables |

**Deliverables**: Database with all tables, memory search working, 3 skills migrated, audit logging active.

### Phase 2: Connectivity (Target: Week 4)

**Goal**: Multi-channel communication via WhatsApp and Telegram.

| Task | Priority | Status | Depends On |
|------|----------|--------|-----------|
| ChannelAdapter base class | P0 | NOT STARTED | — |
| Message Router | P0 | NOT STARTED | ChannelAdapter |
| InternalMessage format | P0 | NOT STARTED | — |
| Web channel adapter | P0 | NOT STARTED | ChannelAdapter |
| WhatsApp Node.js sidecar | P0 | NOT STARTED | — |
| WhatsApp Python adapter | P0 | NOT STARTED | Sidecar |
| QR pairing endpoint | P0 | NOT STARTED | WhatsApp adapter |
| WhatsApp sender allowlist | P1 | NOT STARTED | WhatsApp adapter |
| Telegram bot adapter | P1 | NOT STARTED | ChannelAdapter |
| Message chunking (long responses) | P1 | NOT STARTED | Router |
| Media handling (images, voice, docs) | P2 | NOT STARTED | WhatsApp adapter |
| Device pairing protocol | P1 | NOT STARTED | Phase 1 tables |
| Device status dashboard | P2 | NOT STARTED | Device pairing |

**Deliverables**: WhatsApp connected and receiving commands, Telegram bot running, message routing working.

### Phase 3: Intelligence (Target: Month 2)

**Goal**: Full skill suite, workflow engine, and smart model routing.

| Task | Priority | Status | Depends On |
|------|----------|--------|-----------|
| Workflow engine (Lobster-inspired) | P0 | NOT STARTED | Skill framework |
| Approval gates + resume tokens | P0 | NOT STARTED | Workflow engine |
| deploy_app.yaml workflow | P0 | NOT STARTED | Workflow engine |
| daily_triage.yaml workflow | P1 | NOT STARTED | Workflow engine |
| incident_response.yaml workflow | P1 | NOT STARTED | Workflow engine |
| DatabaseHealth skill | P1 | NOT STARTED | Skill framework |
| FXMonitor skill | P1 | NOT STARTED | Skill framework |
| CardSystem skill | P1 | NOT STARTED | Skill framework |
| Deploy skill | P1 | NOT STARTED | Skill framework |
| SecurityAudit skill | P1 | NOT STARTED | Skill framework |
| DailyBriefing skill (enhanced) | P1 | NOT STARTED | Skill framework |
| SokoMarketplace skill | P2 | NOT STARTED | Skill framework |
| DebtCollection skill | P2 | NOT STARTED | Skill framework |
| ClientComms skill | P2 | NOT STARTED | Skill framework |
| WhatsAppCommands skill | P1 | NOT STARTED | WhatsApp adapter |
| NewsResearch skill | P3 | NOT STARTED | Search API key |
| Tiered model routing (auto-selection) | P1 | NOT STARTED | Enhanced LLM Brain |
| Context window guard | P1 | NOT STARTED | Context assembler |
| Cost optimization (token budgets) | P2 | NOT STARTED | Cost tracking |

**Deliverables**: All 14 skills running, workflow engine with approval gates, smart model routing.

### Phase 4: Polish (Target: Month 3)

**Goal**: Testing, performance, documentation, and SaaS groundwork.

| Task | Priority | Status | Depends On |
|------|----------|--------|-----------|
| Test suite (agents, channels, memory, skills, workflows) | P0 | NOT STARTED | Everything |
| Voice note transcription (WhatsApp) | P2 | NOT STARTED | WhatsApp adapter |
| Enhanced web dashboard (skill mgmt, workflow viewer) | P1 | NOT STARTED | Skills, workflows |
| Memory browser page | P2 | NOT STARTED | Memory system |
| Audit log viewer page | P1 | NOT STARTED | Audit logging |
| Performance optimization | P1 | NOT STARTED | Test suite |
| Credential store (separated from .env) | P1 | NOT STARTED | — |
| Network egress control | P2 | NOT STARTED | — |
| SaaS tenant isolation groundwork | P3 | NOT STARTED | Everything |
| API documentation (OpenAPI/Swagger) | P2 | NOT STARTED | All endpoints |

**Deliverables**: 60%+ test coverage, polished dashboard, SaaS-ready architecture.

---

## 15. SaaS Preparation

Architecture decisions for eventual multi-tenant deployment.

### 15.1 Tenant Isolation Strategy

```
Option A: Schema-per-tenant (Recommended for <100 tenants)
  - Each tenant gets their own PostgreSQL schema
  - Shared tables (plans, billing) in public schema
  - Tenant-specific tables (memory, conversations, skills) in tenant schema
  - Pros: Strong isolation, easy backup/restore per tenant
  - Cons: Migration complexity, connection pool management

Option B: Row-Level Security (For 100+ tenants)
  - All data in shared tables with tenant_id column
  - PostgreSQL RLS policies enforce isolation
  - Pros: Simpler operations, single migration path
  - Cons: Harder to debug, risk of data leakage if RLS misconfigured
```

### 15.2 Per-Tenant Customization

| Feature | How |
|---------|-----|
| Skills | Each tenant has own `skills/` directory, loaded in isolation |
| Channels | Per-tenant WhatsApp numbers, Telegram bots |
| LLM Config | Per-tenant model preferences and token budgets |
| Branding | White-label: custom domain, logo, email templates |
| Billing | Track tokens, API calls, storage per tenant_id |
| Onboarding | Guided wizard: connect channels → configure alerts → add skills |

### 15.3 Billing Hooks

```python
# Every LLM call, skill run, and storage operation increments tenant counters
BILLABLE_EVENTS = {
    "llm_call": "per 1K tokens",
    "skill_run": "per execution",
    "memory_store": "per 1K memories",
    "storage_gb": "per GB/month",
    "channel_message": "per message sent",
    "workflow_run": "per workflow execution",
}
```

---

## 16. Monitoring & Observability

### 16.1 Structured Logging

```python
# All logs as JSON to /opt/antigravity/logs/
import structlog

logger = structlog.get_logger()

# Example log entry:
# {"timestamp": "2026-02-13T10:05:23Z", "level": "info", "event": "skill_executed",
#  "skill": "server_health", "duration_ms": 234, "status": "success",
#  "alerts_raised": 0, "cpu": 23.4, "ram": 67.2}
```

### 16.2 Dashboard Widgets

| Widget | Data Source | Refresh |
|--------|-----------|---------|
| System Health Gauge | server_health skill | 5 min |
| Active Alerts | alerts table | Real-time (htmx polling) |
| Conversation Feed | commands table | Real-time |
| LLM Cost Tracker | llm_usage table | Hourly |
| Skill Status Grid | skill_runs table | 5 min |
| Device Status | devices + device_reports | 5 min |
| Workflow Monitor | workflow_runs table | Real-time |

### 16.3 Alert Escalation

```
Level 1 (Info):     Dashboard only
Level 2 (Warning):  Dashboard + Email
Level 3 (Critical): Dashboard + Email + WhatsApp
Level 4 (Emergency): Dashboard + Email + WhatsApp + SMS (future)
```

---

## 17. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-13 | Python/FastAPI stack | Team expertise, async support, LiteLLM compatibility |
| 2026-02-13 | PostgreSQL + pgvector | Single DB for everything: state, vectors, FTS. Replaces SQLite-vec |
| 2026-02-13 | Node.js Baileys sidecar for WhatsApp | No mature Python WhatsApp Web library exists |
| 2026-02-13 | No skill marketplace | Security: operator-only skills, all reviewed by us |
| 2026-02-13 | Celery for workflows | Already in stack, chains/chords replicate Lobster patterns |
| 2026-02-13 | /opt/antigravity as deployment dir | Separation from git repo at /var/www/ai.sanaa.co |
| 2026-02-13 | Hybrid search (vector+FTS) | Better recall than vector-only, proven by OpenClaw's approach |
| 2026-02-13 | Resume tokens for approvals | Lobster pattern: stateless approval gates with base64url tokens |
| 2026-02-13 | YAML workflow definitions | Declarative, version-controlled, non-developer readable |
| 2026-02-13 | Manifest.yaml for skills | Cleaner than Python decorators, validated before loading |
| 2026-02-13 | Tiered model routing | Cost control: most queries handled by free local Ollama |
| 2026-02-13 | Schema-per-tenant for SaaS | Strong isolation for fintech data, easy per-tenant backup |

---

*This document is the single source of truth for Antigravity v2 architecture. All implementation should follow these specifications. Update this document when designs change.*
