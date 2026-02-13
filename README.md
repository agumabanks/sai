# Sanaa AI - Antigravity Operations Agent

AI-powered operations agent for the Sanaa fintech platform ecosystem. Monitors servers, applications, email, and connected devices. Sends alerts, generates daily reports, and executes approved commands via a web dashboard.

## Stack

- **Backend**: Python 3.11+, FastAPI, Celery, SQLAlchemy (async)
- **Database**: PostgreSQL
- **Queue**: Redis + Celery Beat
- **LLM**: LiteLLM (Ollama local + cloud fallback)
- **Monitoring**: psutil, Playwright
- **Frontend**: Jinja2 templates, TailwindCSS, htmx

## Project Structure

```
ai.sanaa.co/
├── core/                   # FastAPI application
│   ├── main.py             # App entry point, routes, auth
│   ├── database.py         # SQLAlchemy models (async)
│   ├── tasks.py            # Celery scheduled tasks
│   └── agents/             # Agent modules
│       ├── llm_brain.py    # LLM routing (local/cloud tiering)
│       ├── server_health.py # CPU/RAM/Disk/services monitoring
│       ├── app_monitor.py  # Laravel log scanner
│       ├── report_agent.py # Email alerts + daily reports
│       ├── email_agent.py  # IMAP inbox monitoring
│       ├── web_test_agent.py # Playwright uptime testing
│       ├── device_agent.py # Device report handler
│       └── news_agent.py   # News aggregation (placeholder)
├── web/templates/          # Dashboard HTML
│   ├── dashboard.html      # Main operations dashboard
│   └── login.html          # Authentication page
├── mac-client/             # macOS device reporter
│   └── mac-reporter.py     # Reports device health to API
├── docs/
│   ├── research/           # Architecture analysis & specs
│   │   ├── analysis-report.md
│   │   ├── antigravity-v2-blueprint.md
│   │   ├── memory-spec.md
│   │   ├── security-hardening.md
│   │   ├── skills-spec.md
│   │   ├── whatsapp-spec.md
│   │   └── walkthrough.md
│   └── systemd/            # Service unit files
│       ├── antigravity-web.service
│       ├── antigravity-worker.service
│       └── antigravity-beat.service
├── scripts/                # Utility scripts
├── data/                   # Runtime data (gitignored)
├── logs/                   # Runtime logs (gitignored)
├── .env.example            # Environment template
├── requirements.txt        # Python dependencies
└── index.html              # Nginx landing page
```

## Agents

| Agent | Purpose | Schedule |
|-------|---------|----------|
| ServerHealth | CPU, RAM, disk, services, Docker monitoring | Every 5 min |
| AppMonitor | Scans Laravel logs for errors | Every 15 min |
| WebTest | Playwright-based uptime checks on all Sanaa apps | Every 15 min |
| EmailInbox | Monitors IMAP inbox for important messages | Every hour |
| ReportAgent | Compiles and sends email alerts + daily reports | 7 AM EAT daily |
| LLMBrain | Routes commands to local Ollama or cloud LLMs | On demand |
| DeviceAgent | Receives health reports from Mac/mobile clients | On API call |

## Sanaa Ecosystem Monitored

- cards.sanaa.ug - Card/Identity platform
- fx.sanaa.co - FX Trading platform
- soko.sanaa.ug - Soko 24 Marketplace
- sanaa.co - Main website
- ai.sanaa.co - This agent

## Setup

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with real values

# 2. Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 3. Setup PostgreSQL
createdb antigravity_db

# 4. Run
uvicorn core.main:app --host 127.0.0.1 --port 8100

# 5. Run Celery worker + beat (separate terminals)
celery -A core.tasks worker --loglevel=info
celery -A core.tasks beat --loglevel=info
```

## Deployment (systemd)

Service files are in `docs/systemd/`. Copy to `/etc/systemd/system/` and enable:

```bash
sudo systemctl enable --now antigravity-web antigravity-worker antigravity-beat
```

## Security Notes

- Never commit `.env` - it contains credentials
- The dashboard requires session-based authentication
- API endpoints require Bearer token authentication
- All shell commands executed by the LLM have a 60-second timeout
- Destructive operations require manual approval via the web UI
# sai
# sai
