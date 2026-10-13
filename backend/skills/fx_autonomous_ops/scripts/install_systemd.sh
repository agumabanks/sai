#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="/var/www/ai.sanaa.co/backend/skills/fx_autonomous_ops"
SCRIPT_PATH="${SKILL_DIR}/scripts/fx_autopilot.py"
ENV_FILE="/etc/sanaa-fx-autonomous-ops.env"
SERVICE_NAME="sanaa-fx-autonomous-ops.service"
TIMER_NAME="sanaa-fx-autonomous-ops.timer"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
TIMER_FILE="/etc/systemd/system/${TIMER_NAME}"

ENABLE_NOW=0
ALLOW_WITHOUT_EMAIL=0

while (($# > 0)); do
  case "$1" in
    --enable-now)
      ENABLE_NOW=1
      ;;
    --allow-without-email)
      ALLOW_WITHOUT_EMAIL=1
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

if [ ! -f "${SCRIPT_PATH}" ]; then
  echo "missing script: ${SCRIPT_PATH}" >&2
  exit 1
fi

if [ ! -f "${ENV_FILE}" ]; then
  install -m 600 /dev/null "${ENV_FILE}"
  {
    echo "# Sanaa FX Autonomous Ops email settings"
    echo "FX_AUTONOMOUS_EMAIL_TO="
    echo "FX_AUTONOMOUS_EMAIL_FROM="
    echo "FX_AUTONOMOUS_SMTP_HOST="
    echo "FX_AUTONOMOUS_SMTP_PORT=587"
    echo "FX_AUTONOMOUS_SMTP_USER="
    echo "FX_AUTONOMOUS_SMTP_PASS="
    echo "FX_AUTONOMOUS_SMTP_STARTTLS=true"
    echo "FX_AUTONOMOUS_EMAIL_ON_HEALTHY=false"
    echo "# Optional overrides for non-default runtime contract values:"
    echo "# FX_AUTONOMOUS_REPO_ROOT=/var/www/fx.sanaa.co/sanaa-fx/sanaa-fx"
    echo "# FX_AUTONOMOUS_NGINX_SITE=/etc/nginx/sites-available/fx.sanaa.co.conf"
    echo "# FX_AUTONOMOUS_STATE_DIR=/var/lib/fx-autonomous-ops"
    echo "# FX_AUTONOMOUS_FRONTEND_PM2=fx-frontend"
    echo "# FX_AUTONOMOUS_BACKEND_PM2=fx-backend"
    echo "# FX_AUTONOMOUS_FRONTEND_PORT=3100"
    echo "# FX_AUTONOMOUS_BACKEND_PORT=4000"
    echo "# FX_AUTONOMOUS_PUBLIC_HOST=fx.sanaa.co"
  } >> "${ENV_FILE}"
fi

install -d /var/lib/fx-autonomous-ops

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Sanaa FX Autonomous Ops self-heal pass
After=network-online.target pm2-root.service nginx.service
Wants=network-online.target

[Service]
Type=oneshot
User=root
WorkingDirectory=/var/www/fx.sanaa.co/sanaa-fx/sanaa-fx
EnvironmentFile=-${ENV_FILE}
ExecStart=/usr/bin/python3 ${SCRIPT_PATH} --run-once
EOF

cat > "${TIMER_FILE}" <<EOF
[Unit]
Description=Run Sanaa FX Autonomous Ops every 2 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
AccuracySec=15s
Unit=${SERVICE_NAME}

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload

if [[ "${ENABLE_NOW}" -eq 1 ]]; then
  if [[ "${ALLOW_WITHOUT_EMAIL}" -ne 1 ]]; then
    source "${ENV_FILE}"
    if [[ -z "${FX_AUTONOMOUS_EMAIL_TO:-}" || -z "${FX_AUTONOMOUS_EMAIL_FROM:-}" || -z "${FX_AUTONOMOUS_SMTP_HOST:-}" ]]; then
      echo "timer not enabled: configure SMTP/email in ${ENV_FILE} or pass --allow-without-email" >&2
      exit 1
    fi
  fi

  systemctl enable --now "${TIMER_NAME}"
  systemctl restart "${TIMER_NAME}"
  systemctl status "${TIMER_NAME}" --no-pager
  exit 0
fi

echo "installed ${SERVICE_NAME} and ${TIMER_NAME}"
echo "timer remains disabled by default"
echo "configure ${ENV_FILE}, then enable explicitly with:"
echo "  systemctl enable --now ${TIMER_NAME}"
