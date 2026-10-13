#!/usr/bin/env python3
import argparse
import json
import os
import smtplib
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Optional, Tuple


REPO_ROOT = Path(os.getenv("FX_AUTONOMOUS_REPO_ROOT", "/var/www/fx.sanaa.co/sanaa-fx/sanaa-fx"))
NGINX_SITE = Path(os.getenv("FX_AUTONOMOUS_NGINX_SITE", "/etc/nginx/sites-available/fx.sanaa.co.conf"))
STATE_DIR = Path(os.getenv("FX_AUTONOMOUS_STATE_DIR", "/var/lib/fx-autonomous-ops"))
INCIDENT_LOG = STATE_DIR / "incidents.jsonl"
STATUS_FILE = STATE_DIR / "status.json"

FRONTEND_PM2 = os.getenv("FX_AUTONOMOUS_FRONTEND_PM2", "fx-frontend")
BACKEND_PM2 = os.getenv("FX_AUTONOMOUS_BACKEND_PM2", "fx-backend")
FRONTEND_PORT = int(os.getenv("FX_AUTONOMOUS_FRONTEND_PORT", "3100"))
BACKEND_PORT = int(os.getenv("FX_AUTONOMOUS_BACKEND_PORT", "4000"))
PUBLIC_HOST = os.getenv("FX_AUTONOMOUS_PUBLIC_HOST", "fx.sanaa.co")


@dataclass
class CommandResult:
    cmd: List[str]
    returncode: int
    stdout: str
    stderr: str


class FxAutopilot:
    def __init__(self, dry_run: bool = False, email: bool = True):
        self.dry_run = dry_run
        self.email_enabled = email
        self.actions_run: List[Dict[str, object]] = []
        self.ensure_state_dir()

    def ensure_state_dir(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
        check: bool = False,
        timeout: int = 180,
    ) -> CommandResult:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        result = CommandResult(
            cmd=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
        if check and result.returncode != 0:
            raise RuntimeError(self.format_result(result))
        return result

    def format_result(self, result: CommandResult) -> str:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        parts = [
            f"cmd={' '.join(result.cmd)}",
            f"rc={result.returncode}",
        ]
        if stdout:
            parts.append(f"stdout={stdout[:1500]}")
        if stderr:
            parts.append(f"stderr={stderr[:1500]}")
        return "\n".join(parts)

    def record_action(self, name: str, ok: bool, details: str) -> None:
        self.actions_run.append(
            {
                "action": name,
                "ok": ok,
                "details": details.strip(),
                "ts": int(time.time()),
            }
        )

    def file_contains(self, path: Path, needle: str) -> bool:
        try:
            return needle in path.read_text()
        except FileNotFoundError:
            return False

    def gather_pm2(self) -> Tuple[List[dict], str]:
        result = self.run(["pm2", "jlist"], timeout=30)
        apps = json.loads(result.stdout) if result.returncode == 0 and result.stdout else []
        return apps, result.stdout

    def recent_logs(self, app_name: str, lines: int = 80) -> str:
        result = self.run(["pm2", "logs", app_name, "--lines", str(lines), "--nostream"], timeout=45)
        return (result.stdout + "\n" + result.stderr).strip()

    def curl_code(self, url: str, extra: Optional[List[str]] = None) -> int:
        cmd = ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", url]
        if extra:
            cmd = ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", *extra, url]
        result = self.run(cmd, timeout=30)
        try:
            return int(result.stdout.strip())
        except ValueError:
            return 0

    def curl_body(self, url: str, extra: Optional[List[str]] = None) -> str:
        cmd = ["curl", "-sS", url]
        if extra:
            cmd = ["curl", "-sS", *extra, url]
        result = self.run(cmd, timeout=45)
        return result.stdout

    def port_listeners(self) -> str:
        result = self.run(["ss", "-ltnp"], timeout=30)
        return result.stdout

    def validate(self) -> Dict[str, object]:
        check = self.run(["pnpm", "check:fx"], cwd=REPO_ROOT, timeout=180)
        en_code = self.curl_code(f"https://{PUBLIC_HOST}/en")
        root_code = self.curl_code(f"https://{PUBLIC_HOST}/")
        api_code = self.curl_code(f"https://{PUBLIC_HOST}/api")
        pm2 = self.run(["pm2", "ls"], timeout=45)
        ok = (
            check.returncode == 0
            and "CHECK PASSED" in check.stdout
            and en_code == 200
            and root_code in (200, 307)
            and api_code == 200
            and FRONTEND_PM2 in pm2.stdout
            and BACKEND_PM2 in pm2.stdout
        )
        return {
            "ok": ok,
            "check_output": check.stdout.strip() or check.stderr.strip(),
            "public_en": en_code,
            "public_root": root_code,
            "public_api": api_code,
            "pm2_ls": pm2.stdout.strip(),
        }

    def snapshot(self) -> Dict[str, object]:
        apps, _ = self.gather_pm2()
        app_map = {app.get("name"): app for app in apps}
        listeners = self.port_listeners()
        frontend_logs = self.recent_logs(FRONTEND_PM2)
        backend_logs = self.recent_logs(BACKEND_PM2)
        frontend_online = app_map.get(FRONTEND_PM2, {}).get("pm2_env", {}).get("status") == "online"
        backend_online = app_map.get(BACKEND_PM2, {}).get("pm2_env", {}).get("status") == "online"
        frontend_restarts = app_map.get(FRONTEND_PM2, {}).get("pm2_env", {}).get("restart_time", 0)
        local_frontend_code = self.curl_code(f"http://127.0.0.1:{FRONTEND_PORT}/en")
        local_backend_code = self.curl_code(f"http://127.0.0.1:{BACKEND_PORT}/api")
        public_en = self.curl_code(f"https://{PUBLIC_HOST}/en")
        public_root = self.curl_code(f"https://{PUBLIC_HOST}/")
        public_api = self.curl_code(f"https://{PUBLIC_HOST}/api")
        local_frontend_body = ""
        if local_frontend_code:
            local_frontend_body = self.curl_body(f"http://127.0.0.1:{FRONTEND_PORT}/en")
        nginx_text = NGINX_SITE.read_text() if NGINX_SITE.exists() else ""
        return {
            "pm2_apps": sorted(app_map.keys()),
            "frontend_online": frontend_online,
            "backend_online": backend_online,
            "frontend_restarts": frontend_restarts,
            "listeners": listeners,
            "local_frontend_code": local_frontend_code,
            "local_backend_code": local_backend_code,
            "local_frontend_body": local_frontend_body[:4000],
            "public_en": public_en,
            "public_root": public_root,
            "public_api": public_api,
            "frontend_logs": frontend_logs[-6000:],
            "backend_logs": backend_logs[-4000:],
            "nginx_text": nginx_text,
        }

    def classify(self, snap: Dict[str, object]) -> Dict[str, object]:
        symptoms: List[str] = []
        candidates: List[str] = []
        logs = str(snap["frontend_logs"])
        body = str(snap["local_frontend_body"])
        listeners = str(snap["listeners"])
        nginx_text = str(snap["nginx_text"])

        if (
            snap["public_en"] == 200
            and snap["public_api"] == 200
            and snap["public_root"] in (200, 307)
            and snap["local_frontend_code"] == 200
            and snap["local_backend_code"] == 200
            and snap["frontend_online"]
            and snap["backend_online"]
        ):
            return {"signature": "healthy", "symptoms": ["healthy"], "candidates": []}

        if FRONTEND_PM2 not in snap["pm2_apps"] or BACKEND_PM2 not in snap["pm2_apps"]:
            symptoms.append("pm2_stack_missing")
            candidates.extend(["start_pm2_stack", "save_pm2"])

        if not snap["frontend_online"]:
            symptoms.append("frontend_pm2_unhealthy")

        if not snap["backend_online"] or snap["local_backend_code"] != 200 or snap["public_api"] != 200:
            symptoms.append("backend_unhealthy")
            candidates.extend(["restart_backend", "start_pm2_stack"])

        if f":{FRONTEND_PORT}" not in listeners or snap["local_frontend_code"] != 200:
            symptoms.append("frontend_3100_unhealthy")

        if "Could not find a production build" in logs or "production-start-no-build-id" in logs:
            symptoms.append("frontend_build_missing")
            candidates.extend(["build_frontend", "restart_frontend"])

        if "EADDRINUSE" in logs and str(FRONTEND_PORT) in logs:
            symptoms.append("frontend_port_collision")
            candidates.extend(["kill_3100_owner", "restart_frontend"])

        if "Cannot GET /en" in body or (snap["public_en"] in (502, 503) and ":3000" in listeners and f":{FRONTEND_PORT}" not in listeners):
            symptoms.append("wrong_process_symptom")
            candidates.extend(["build_frontend", "restart_frontend"])

        if f"127.0.0.1:{FRONTEND_PORT}" not in nginx_text or f"127.0.0.1:{BACKEND_PORT}" not in nginx_text:
            symptoms.append("nginx_contract_drift")
            candidates.extend(["repair_nginx_contract", "reload_nginx"])

        if snap["public_en"] == 502 and "frontend_build_missing" not in symptoms:
            symptoms.append("public_frontend_bad_gateway")
            candidates.extend(["restart_frontend", "build_frontend"])

        if not symptoms:
            symptoms.append("unknown_runtime_issue")
            candidates.extend(["restart_frontend", "restart_backend", "start_pm2_stack"])

        ordered = self.rank_actions(symptoms, candidates)
        signature = "+".join(sorted(set(symptoms)))
        return {"signature": signature, "symptoms": sorted(set(symptoms)), "candidates": ordered}

    def load_history(self) -> List[dict]:
        if not INCIDENT_LOG.exists():
            return []
        rows = []
        for line in INCIDENT_LOG.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def rank_actions(self, symptoms: List[str], candidates: List[str]) -> List[str]:
        unique_candidates = []
        for action in candidates:
            if action not in unique_candidates:
                unique_candidates.append(action)

        history = self.load_history()
        scores: Dict[str, float] = {action: 0.0 for action in unique_candidates}

        symptom_set = set(symptoms)
        for record in history[-300:]:
            record_symptoms = set(record.get("symptoms", []))
            overlap = len(symptom_set.intersection(record_symptoms))
            if overlap == 0:
                continue
            weight = overlap / max(len(symptom_set.union(record_symptoms)), 1)
            for action in record.get("actions", []):
                name = action.get("action")
                if name not in scores:
                    continue
                scores[name] += weight * (2.0 if action.get("ok") else -1.0)

        return sorted(unique_candidates, key=lambda item: (-scores[item], unique_candidates.index(item)))

    def maybe_write(self, path: Path, content: str) -> None:
        if self.dry_run:
            return
        path.write_text(content)

    def action_build_frontend(self) -> Tuple[bool, str]:
        if self.dry_run:
            return True, "dry-run: would execute pnpm build:frontend"
        result = self.run(["pnpm", "build:frontend"], cwd=REPO_ROOT, timeout=1800)
        ok = result.returncode == 0
        return ok, (result.stdout + "\n" + result.stderr)[-8000:]

    def action_restart_frontend(self) -> Tuple[bool, str]:
        if self.dry_run:
            return True, f"dry-run: would execute pm2 restart {FRONTEND_PM2}"
        result = self.run(["pm2", "restart", FRONTEND_PM2], timeout=120)
        return result.returncode == 0, (result.stdout + "\n" + result.stderr).strip()

    def action_restart_backend(self) -> Tuple[bool, str]:
        if self.dry_run:
            return True, f"dry-run: would execute pm2 restart {BACKEND_PM2}"
        result = self.run(["pm2", "restart", BACKEND_PM2], timeout=120)
        return result.returncode == 0, (result.stdout + "\n" + result.stderr).strip()

    def action_start_pm2_stack(self) -> Tuple[bool, str]:
        if self.dry_run:
            return True, "dry-run: would execute pm2 start production.config.js --env production"
        result = self.run(["pm2", "start", "production.config.js", "--env", "production"], cwd=REPO_ROOT, timeout=180)
        return result.returncode == 0, (result.stdout + "\n" + result.stderr).strip()

    def action_save_pm2(self) -> Tuple[bool, str]:
        if self.dry_run:
            return True, "dry-run: would execute pm2 save"
        result = self.run(["pm2", "save"], timeout=120)
        return result.returncode == 0, (result.stdout + "\n" + result.stderr).strip()

    def action_kill_3100_owner(self) -> Tuple[bool, str]:
        if self.dry_run:
            return True, f"dry-run: would execute fuser -k {FRONTEND_PORT}/tcp"
        result = self.run(["fuser", "-k", f"{FRONTEND_PORT}/tcp"], timeout=30)
        return result.returncode == 0, (result.stdout + "\n" + result.stderr).strip()

    def action_repair_nginx_contract(self) -> Tuple[bool, str]:
        if not NGINX_SITE.exists():
            return False, f"missing nginx site file: {NGINX_SITE}"
        before = NGINX_SITE.read_text()
        after = before
        after = after.replace("proxy_pass http://127.0.0.1:3000;", f"proxy_pass http://127.0.0.1:{FRONTEND_PORT};")
        if f"proxy_pass http://127.0.0.1:{FRONTEND_PORT};" not in after:
            return False, "frontend upstream repair could not be applied safely"
        if f"proxy_pass http://127.0.0.1:{BACKEND_PORT};" not in after:
            after = after.replace("proxy_pass http://127.0.0.1:4001;", f"proxy_pass http://127.0.0.1:{BACKEND_PORT};")
        if self.dry_run:
            return True, "dry-run: would enforce Nginx upstream ports for FX contract"
        if before != after:
            backup = NGINX_SITE.with_suffix(".conf.bak")
            backup.write_text(before)
            NGINX_SITE.write_text(after)
        return True, "enforced expected FX upstreams in nginx site file"

    def action_reload_nginx(self) -> Tuple[bool, str]:
        if self.dry_run:
            return True, "dry-run: would run nginx -t && systemctl reload nginx"
        test = self.run(["nginx", "-t"], timeout=30)
        if test.returncode != 0:
            return False, (test.stdout + "\n" + test.stderr).strip()
        reload_result = self.run(["systemctl", "reload", "nginx"], timeout=60)
        ok = reload_result.returncode == 0
        return ok, (test.stdout + "\n" + test.stderr + "\n" + reload_result.stdout + "\n" + reload_result.stderr).strip()

    def execute_action(self, action: str) -> Tuple[bool, str]:
        method = getattr(self, f"action_{action}", None)
        if method is None:
            return False, f"unknown action: {action}"
        return method()

    def persist_incident(self, incident: Dict[str, object], validation: Dict[str, object]) -> None:
        payload = {
            "ts": int(time.time()),
            "signature": incident["signature"],
            "symptoms": incident["symptoms"],
            "actions": self.actions_run,
            "validation": {
                "ok": validation["ok"],
                "public_en": validation["public_en"],
                "public_root": validation["public_root"],
                "public_api": validation["public_api"],
            },
        }
        with INCIDENT_LOG.open("a") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def load_status(self) -> Dict[str, object]:
        if not STATUS_FILE.exists():
            return {}
        try:
            return json.loads(STATUS_FILE.read_text())
        except json.JSONDecodeError:
            return {}

    def save_status(self, status: Dict[str, object]) -> None:
        self.maybe_write(STATUS_FILE, json.dumps(status, indent=2, sort_keys=True) + "\n")

    def email_configured(self) -> bool:
        return all(
            os.getenv(key)
            for key in [
                "FX_AUTONOMOUS_EMAIL_TO",
                "FX_AUTONOMOUS_EMAIL_FROM",
                "FX_AUTONOMOUS_SMTP_HOST",
            ]
        )

    def send_email(self, subject: str, body: str) -> None:
        if not self.email_enabled or not self.email_configured():
            return

        host = os.getenv("FX_AUTONOMOUS_SMTP_HOST")
        port = int(os.getenv("FX_AUTONOMOUS_SMTP_PORT", "587"))
        user = os.getenv("FX_AUTONOMOUS_SMTP_USER")
        password = os.getenv("FX_AUTONOMOUS_SMTP_PASS")
        starttls = os.getenv("FX_AUTONOMOUS_SMTP_STARTTLS", "true").lower() != "false"

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = os.getenv("FX_AUTONOMOUS_EMAIL_FROM")
        msg["To"] = os.getenv("FX_AUTONOMOUS_EMAIL_TO")
        msg.set_content(body)

        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            if starttls:
                smtp.starttls(context=context)
                smtp.ehlo()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)

    def build_report(
        self,
        incident: Dict[str, object],
        validation: Dict[str, object],
        snap: Dict[str, object],
    ) -> Tuple[str, str]:
        status = "RECOVERED" if validation["ok"] else "FAILED"
        subject = f"[fx-autonomous-ops] {status.lower()} {PUBLIC_HOST} ({incident['signature']})"
        lines = [
            f"Host: {PUBLIC_HOST}",
            f"Result: {status}",
            f"Incident: {incident['signature']}",
            f"Symptoms: {', '.join(incident['symptoms'])}",
            "",
            "Actions:",
        ]
        if self.actions_run:
            for action in self.actions_run:
                lines.append(f"- {action['action']}: {'ok' if action['ok'] else 'failed'}")
                details = str(action["details"]).strip()
                if details:
                    lines.append(f"  {details[:1500]}")
        else:
            lines.append("- no repair action was necessary")

        lines.extend(
            [
                "",
                "Validation:",
                f"- pnpm check:fx: {'ok' if validation['ok'] else 'failed'}",
                f"- public /en: {validation['public_en']}",
                f"- public /: {validation['public_root']}",
                f"- public /api: {validation['public_api']}",
                "",
                "Context:",
                f"- frontend_online: {snap['frontend_online']}",
                f"- backend_online: {snap['backend_online']}",
                f"- frontend_restarts: {snap['frontend_restarts']}",
            ]
        )
        return subject, "\n".join(lines)

    def should_email(self, incident: Dict[str, object], validation: Dict[str, object]) -> bool:
        previous = self.load_status()
        current = {
            "signature": incident["signature"],
            "ok": validation["ok"],
            "actions": [{"action": a["action"], "ok": a["ok"]} for a in self.actions_run],
        }
        email_healthy = os.getenv("FX_AUTONOMOUS_EMAIL_ON_HEALTHY", "false").lower() == "true"

        changed = previous != current
        self.save_status(current)
        if self.actions_run:
            return True
        if not validation["ok"]:
            return changed
        return changed and email_healthy

    def run_once(self) -> int:
        snap = self.snapshot()
        incident = self.classify(snap)

        if incident["signature"] != "healthy":
            for action in incident["candidates"]:
                ok, details = self.execute_action(action)
                self.record_action(action, ok, details)
                if not ok:
                    continue
                post_action = self.snapshot()
                if self.classify(post_action)["signature"] == "healthy":
                    snap = post_action
                    break
                snap = post_action

        validation = self.validate()
        self.persist_incident(incident, validation)

        if self.should_email(incident, validation):
            subject, body = self.build_report(incident, validation, snap)
            self.send_email(subject, body)

        if validation["ok"]:
            print("FX AUTOPILOT: stack healthy")
            return 0

        print("FX AUTOPILOT: stack still unhealthy", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor and self-heal fx.sanaa.co")
    parser.add_argument("--run-once", action="store_true", help="Run a single monitor and repair pass")
    parser.add_argument("--dry-run", action="store_true", help="Print intent without making changes")
    parser.add_argument("--no-email", action="store_true", help="Do not send email even if configured")
    args = parser.parse_args()

    if not args.run_once:
        parser.error("only --run-once is currently supported")

    pilot = FxAutopilot(dry_run=args.dry_run, email=not args.no_email)
    return pilot.run_once()


if __name__ == "__main__":
    raise SystemExit(main())
