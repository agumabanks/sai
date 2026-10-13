---
name: fx_autonomous_ops
description: Sanaa-native FX production self-heal package for fx.sanaa.co. Detects missing frontend builds, PM2 drift, wrong frontend/backend ports, nginx upstream drift, and public route failures, then runs bounded repairs and re-validates the stack.
---

# FX Autonomous Ops

This package is installed in the Sanaa AI backend at:

- `/var/www/ai.sanaa.co/backend/skills/fx_autonomous_ops`

It is not a Codex-only skill anymore. The live Sanaa backend exposes it through the native skill loader and `/api/skills` after hot-reload.

## Runtime Contract

Always enforce these values:

- Frontend PM2 app: `fx-frontend`
- Backend PM2 app: `fx-backend`
- Frontend port: `3100`
- Backend port: `4000`
- Nginx site file: `/etc/nginx/sites-available/fx.sanaa.co.conf`
- Frontend upstream: `127.0.0.1:3100`
- Backend upstream: `127.0.0.1:4000`

Never switch the frontend back to `3000`. Never rename the PM2 apps to `frontend` or `backend`.

## What It Handles

- missing Next.js production build
- PM2 stack drift or missing FX app names
- frontend/backend port mismatches
- Nginx upstream drift
- public `/en`, `/`, or `/api` failures
- bounded remediation ordering based on past successful incidents

## Native Sanaa Actions

- `run_once`: run detection, bounded repair, validation, and incident logging
- `dry_run`: inspect and classify without changing the stack
- `validate`: run `pnpm check:fx`, public curls, and `pm2 ls`
- `incidents`: show recent incident history from `/var/lib/fx-autonomous-ops/incidents.jsonl`
- `install_timer`: install the systemd unit/timer files, with optional explicit enablement
- `show_contract`: return the runtime contract and package notes

## Sanaa Runtime Assets

- script: `/var/www/ai.sanaa.co/backend/skills/fx_autonomous_ops/scripts/fx_autopilot.py`
- installer: `/var/www/ai.sanaa.co/backend/skills/fx_autonomous_ops/scripts/install_systemd.sh`
- reference: `/var/www/ai.sanaa.co/backend/skills/fx_autonomous_ops/references/fx-runtime-contract.md`

## Explicit Timer Policy

The installer writes the systemd unit and timer, but it does not enable the timer unless `--enable-now` is passed. This prevents silently introducing an unattended root service.

If SMTP credentials are not configured, `--enable-now` is blocked unless `--allow-without-email` is also passed.
