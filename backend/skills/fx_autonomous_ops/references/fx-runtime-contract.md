# FX Runtime Contract

## Scope

This reference is for `fx.sanaa.co` only.

Sanaa-native skill package:

- `/var/www/ai.sanaa.co/backend/skills/fx_autonomous_ops`

Repository root:

- `/var/www/fx.sanaa.co/sanaa-fx/sanaa-fx`

Key runtime files:

- PM2 config: `/var/www/fx.sanaa.co/sanaa-fx/sanaa-fx/production.config.js`
- Health check: `/var/www/fx.sanaa.co/sanaa-fx/sanaa-fx/scripts/check-fx-stack.sh`
- Nginx site: `/etc/nginx/sites-available/fx.sanaa.co.conf`

## Contract

- Frontend PM2 app: `fx-frontend`
- Backend PM2 app: `fx-backend`
- Frontend port: `3100`
- Backend port: `4000`
- Public host: `fx.sanaa.co`

## Common Incidents

### 1. Frontend build missing

Indicators:

- public `/en` returns `502`
- nothing listens on `3100`
- PM2 `fx-frontend` restarts repeatedly
- logs contain `Could not find a production build in the '.next' directory`

Preferred actions:

1. `pnpm build:frontend`
2. `pm2 restart fx-frontend`
3. validate with `pnpm check:fx`

### 2. Wrong process on frontend path

Indicators:

- `/en` returns `Cannot GET /en`
- `3000` is occupied by some unrelated process
- `3100` is absent or not serving Next.js HTML

Preferred actions:

1. ensure Nginx points to `127.0.0.1:3100`
2. restore the frontend on `3100`
3. validate publicly

### 3. PM2 stack drift

Indicators:

- `fx-frontend` or `fx-backend` missing from `pm2 ls`
- app names changed to `frontend` or `backend`

Preferred actions:

1. `pm2 start production.config.js --env production`
2. `pm2 save`
3. validate

### 4. Nginx contract drift

Indicators:

- upstream points to frontend `3000` or wrong backend port
- `nginx -t` fails

Preferred actions:

1. restore expected upstreams
2. `nginx -t`
3. `systemctl reload nginx`
4. validate publicly

## Email Environment

The automation script supports SMTP delivery through an env file or process environment.

Required for email:

- `FX_AUTONOMOUS_EMAIL_TO`
- `FX_AUTONOMOUS_EMAIL_FROM`
- `FX_AUTONOMOUS_SMTP_HOST`

Optional:

- `FX_AUTONOMOUS_SMTP_PORT` default `587`
- `FX_AUTONOMOUS_SMTP_USER`
- `FX_AUTONOMOUS_SMTP_PASS`
- `FX_AUTONOMOUS_SMTP_STARTTLS` default `true`
- `FX_AUTONOMOUS_EMAIL_ON_HEALTHY` default `false`
- `FX_AUTONOMOUS_REPO_ROOT`
- `FX_AUTONOMOUS_NGINX_SITE`
- `FX_AUTONOMOUS_STATE_DIR`
- `FX_AUTONOMOUS_FRONTEND_PM2`
- `FX_AUTONOMOUS_BACKEND_PM2`
- `FX_AUTONOMOUS_FRONTEND_PORT`
- `FX_AUTONOMOUS_BACKEND_PORT`
- `FX_AUTONOMOUS_PUBLIC_HOST`

## Escalation Rules

Escalate instead of continuing if:

- `pnpm build:frontend` fails
- `nginx -t` fails after a contract repair attempt
- the validation checks still fail after the approved action set is exhausted
- the issue would require code edits, package changes, database changes, or credential changes

## Suggested Future Extensions

- attach structured excerpts from PM2 and Nginx error logs in alert emails
- quarantine or report recurring orphan processes on `3000`
- add latency and restart-rate thresholds, not just up/down checks
- expose a compact incident dashboard from the JSONL history
