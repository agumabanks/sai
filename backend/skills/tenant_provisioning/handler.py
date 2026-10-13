"""
Tenant Provisioning Skill — automates full Sanaa Finance tenant setup.

Steps for a new tenant:
  1. rsync clone source app to /var/www/<domain>
  2. Regenerate APP_KEY (security isolation between tenants)
  3. Update .env (APP_NAME, APP_URL, DB_DATABASE, SANCTUM, REDIRECT_URI)
  4. Create MySQL database and clone from source DB
  5. Grant DB user permissions
  6. Optionally wipe tenant operational data
  7. Write and enable nginx config
  8. Issue TLS certificate via certbot
  9. Run Laravel setup (storage:link, migrations, cache)
  10. Optionally set admin phone/password
  11. Verify the site returns HTTP 200

Actions:
  - provision: Full tenant setup
  - status:    Health check a tenant
  - list:      Show all sanaa tenants
  - disable:   Disable a tenant (nginx down, site offline)
  - enable:    Re-enable a disabled tenant
"""

import asyncio
import base64
import logging
import os
import re
import shlex
import tempfile
from urllib.parse import urlparse

from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TENANT_BASE_DIR = "/var/www"
NGINX_AVAILABLE = "/etc/nginx/sites-available"
NGINX_ENABLED = "/etc/nginx/sites-enabled"
PHP_FPM_SOCK = os.getenv("TENANT_PHP_FPM_SOCK", "/run/php/php8.4-fpm.sock")
DB_HOST = os.getenv("TENANT_MYSQL_HOST", "127.0.0.1")
DB_PORT = os.getenv("TENANT_MYSQL_PORT", "3306")
DB_USER = os.getenv("TENANT_MYSQL_ADMIN_USER")
DB_PASS = os.getenv("TENANT_MYSQL_ADMIN_PASS")
LARAVEL_DB_USER = os.getenv("TENANT_APP_DB_USER", "kalamba_user")


def _db_credentials_ok() -> bool:
    """Fail closed if tenant MySQL admin credentials are not configured."""
    return bool(DB_USER and DB_PASS)
NGINX_BIN = os.getenv("TENANT_NGINX_BIN", "/usr/sbin/nginx")
CERTBOT_BIN = os.getenv("TENANT_CERTBOT_BIN", "/usr/bin/certbot")
SYSTEMCTL_BIN = os.getenv("TENANT_SYSTEMCTL_BIN", "/usr/bin/systemctl")
SUPERVISORCTL_BIN = os.getenv("TENANT_SUPERVISORCTL_BIN", "/usr/bin/supervisorctl")
CRONTAB_BIN = os.getenv("TENANT_CRONTAB_BIN", "/usr/bin/crontab")
HTTP_OK_CODES = {"200", "301", "302"}
INVALID_PUBLIC_MARKERS = (
    "Login -  Sanaa Intelligence",
    "Sanaa Intelligence",
    "<title>404 Not Found</title>",
    "<title>Not Found</title>",
)


def _base_env() -> dict:
    env = os.environ.copy()
    current_path = env.get("PATH", "")
    env["PATH"] = f"/usr/sbin:/usr/bin:/bin:{current_path}" if current_path else "/usr/sbin:/usr/bin:/bin"
    return env


async def _run(args: list[str], timeout: int = 120, cwd: str | None = None) -> tuple[int, str, str]:
    """Run a command via an explicit argument list and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_base_env(),
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", f"Command timed out after {timeout}s"
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def _run_shell(cmd: str, timeout: int = 120, cwd: str | None = None) -> tuple[int, str, str]:
    """Run a hardcoded shell pipeline via ["bash", "-c", cmd].

    Only used when shell syntax is unavoidable. Any user-influenced values
    interpolated into cmd must be validated/quoted beforehand.
    """
    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_base_env(),
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", f"Command timed out after {timeout}s"
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def _mysql_exec(sql: str, database: str | None = None, timeout: int = 120) -> tuple[int, str, str]:
    """Run a single MySQL statement via an explicit argument list.

    This avoids shell interpretation of the SQL statement and credentials.
    """
    if not _db_credentials_ok():
        return -1, "", "tenant mysql admin credentials not configured"

    args = [
        "mysql",
        "-h", DB_HOST,
        "-P", DB_PORT,
        "-u", DB_USER,
        f"-p{DB_PASS}",
        "-N",
        "-e", sql,
    ]
    if database is not None:
        # Only allow simple alphanumerics/underscores to prevent accidental injection.
        if not re.match(r"^[A-Za-z0-9_]+$", database):
            return -1, "", f"invalid database name: {database}"
        args.append(database)

    env = os.environ.copy()
    current_path = env.get("PATH", "")
    env["PATH"] = f"/usr/sbin:/usr/bin:/bin:{current_path}" if current_path else "/usr/sbin:/usr/bin:/bin"
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", f"mysql command timed out after {timeout}s"
    return proc.returncode, stdout.decode(), stderr.decode()


async def _mysql_clone_db(db_source: str, db_name: str, timeout: int = 240) -> tuple[int, str]:
    """Clone one MySQL database to another using argument lists and a temp file.

    Replaces the previous `mysqldump ... | mysql ...` shell pipeline to avoid
    shell interpretation of database names or credentials.
    """
    if not _db_credentials_ok():
        return -1, "tenant mysql admin credentials not configured"
    if not re.match(r"^[A-Za-z0-9_]+$", db_source):
        return -1, f"invalid source database name: {db_source}"
    if not re.match(r"^[A-Za-z0-9_]+$", db_name):
        return -1, f"invalid target database name: {db_name}"

    env = os.environ.copy()
    current_path = env.get("PATH", "")
    env["PATH"] = f"/usr/sbin:/usr/bin:/bin:{current_path}" if current_path else "/usr/sbin:/usr/bin:/bin"

    fd, tmp_path = tempfile.mkstemp(suffix=".sql")
    os.close(fd)
    try:
        dump_args = [
            "mysqldump",
            "-h", DB_HOST,
            "-P", DB_PORT,
            "-u", DB_USER,
            f"-p{DB_PASS}",
            "--single-transaction",
            "--quick",
            "--routines",
            "--triggers",
            db_source,
        ]
        dump_proc = await asyncio.create_subprocess_exec(
            *dump_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            dump_stdout, dump_stderr = await asyncio.wait_for(dump_proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            dump_proc.kill()
            return -1, "mysqldump timed out"
        if dump_proc.returncode != 0:
            return dump_proc.returncode, dump_stderr.decode()

        with open(tmp_path, "wb") as handle:
            handle.write(dump_stdout)

        load_args = [
            "mysql",
            "-h", DB_HOST,
            "-P", DB_PORT,
            "-u", DB_USER,
            f"-p{DB_PASS}",
            db_name,
        ]
        load_proc = await asyncio.create_subprocess_exec(
            *load_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            with open(tmp_path, "rb") as handle:
                load_stdout, load_stderr = await asyncio.wait_for(
                    load_proc.communicate(input=handle.read()), timeout=timeout
                )
        except asyncio.TimeoutError:
            load_proc.kill()
            return -1, "mysql load timed out"
        if load_proc.returncode != 0:
            return load_proc.returncode, load_stderr.decode()
        return 0, ""
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


def _extract_app_name(domain: str) -> str:
    """Extract app name from domain: bukuya.sanaa.ug -> bukuya."""
    return domain.split(".")[0]


def _normalize_domain(raw: str) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return ""

    if "://" not in value and "/" in value:
        value = f"https://{value.lstrip('/')}"

    if "://" in value:
        parsed = urlparse(value)
        if parsed.hostname:
            value = parsed.hostname.lower()
    else:
        value = value.split("/", 1)[0]

    value = value.strip(".")
    if value.startswith("www."):
        candidate = value[4:]
        if re.match(r"^[a-z0-9\-]+\.sanaa\.(ug|co)$", candidate):
            value = candidate

    return value


def _validate_domain(domain: str) -> str | None:
    """Return error message if domain is invalid, else None."""
    if not domain:
        return "domain is required"
    if not re.match(r"^[a-z0-9\-]+\.sanaa\.(ug|co)$", domain):
        return f"Invalid domain: {domain}. Expected <name>.sanaa.ug or <name>.sanaa.co"
    return None


def _read_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not os.path.isfile(path):
        return values

    with open(path, "r") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key] = value.strip().strip('"').strip("'")

    return values


def _upsert_env_value(path: str, key: str, value: str) -> None:
    line = f"{key}={value}"
    escaped_key = "".join(f"\\{char}" if char in r"\.^$*+?{}[]|()" else char for char in key)

    if not os.path.isfile(path):
        with open(path, "w") as handle:
            handle.write(f"{line}\n")
        return

    with open(path, "r") as handle:
        content = handle.read()

    content, replacements = re.subn(rf"^{escaped_key}=.*$", line, content, flags=re.MULTILINE)
    if not replacements:
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"{line}\n"

    with open(path, "w") as handle:
        handle.write(content)


def _reset_runtime_state(app_root: str) -> None:
    for cache_file in (
        f"{app_root}/bootstrap/cache/config.php",
        f"{app_root}/bootstrap/cache/routes-v7.php",
        f"{app_root}/bootstrap/cache/routes-v8.php",
        f"{app_root}/bootstrap/cache/routes-v9.php",
        f"{app_root}/bootstrap/cache/routes.php",
        f"{app_root}/bootstrap/cache/events.php",
    ):
        if os.path.isfile(cache_file):
            os.unlink(cache_file)

    for directory in (
        f"{app_root}/storage/framework/sessions",
        f"{app_root}/storage/framework/views",
        f"{app_root}/storage/framework/cache/data",
    ):
        if not os.path.isdir(directory):
            continue
        for root, _, files in os.walk(directory):
            for filename in files:
                if filename.startswith(".gitignore"):
                    continue
                try:
                    os.unlink(os.path.join(root, filename))
                except FileNotFoundError:
                    pass

    logs_dir = f"{app_root}/storage/logs"
    if os.path.isdir(logs_dir):
        for filename in os.listdir(logs_dir):
            if filename.endswith(".log"):
                try:
                    open(os.path.join(logs_dir, filename), "w").close()
                except OSError:
                    pass


class TenantProvisioningSkill(BaseSkill):
    name = "tenant_provisioning"
    description = (
        "Provision, manage, and monitor Sanaa Finance tenants. "
        "Actions: provision, status, list, disable, enable."
    )
    version = "1.1.0"
    permissions = ["shell", "network", "filesystem"]
    # NOTE: requires_approval = False here so the dashboard can call it directly.
    # The workflow YAML has its own approval step for LLM-triggered provisioning.
    # The Filament page form submission IS the human approval.
    requires_approval = False
    timeout = 300
    tags = ["infrastructure", "provisioning", "tenant", "devops"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "provision")

        if not _db_credentials_ok():
            return SkillResult(
                success=False,
                error="Tenant MySQL admin credentials not configured (TENANT_MYSQL_ADMIN_USER / TENANT_MYSQL_ADMIN_PASS)",
            )

        dispatch = {
            "provision": self._provision,
            "status": self._status,
            "list": self._list_tenants,
            "disable": self._disable_tenant,
            "enable": self._enable_tenant,
        }

        handler = dispatch.get(action)
        if not handler:
            return SkillResult(success=False, error=f"Unknown action: {action}")

        return await handler(args, context)

    async def _table_count(self, schema: str) -> int:
        if not re.match(r"^[A-Za-z0-9_]+$", schema):
            return 0
        sql = (
            "SELECT COUNT(*) FROM information_schema.tables "
            f"WHERE table_schema='{schema}';"
        )
        rc, out, _ = await _mysql_exec(sql, database="information_schema", timeout=10)
        if rc != 0:
            return 0

        try:
            return int(out.strip() or "0")
        except ValueError:
            return 0

    async def _http_status(self, url: str, host: str | None = None) -> str:
        args = ["curl", "-k", "-sS", "-o", "/dev/null", "-w", "%{http_code}"]
        if host:
            args.extend(["-H", f"Host: {host}"])
        args.append(url)
        rc, out, _ = await _run(args, timeout=15)
        return out.strip() if rc == 0 else "000"

    async def _http_body(self, url: str) -> str:
        rc, out, _ = await _run(
            ["curl", "-k", "-L", "-sS", "--max-redirs", "5", url],
            timeout=20,
        )
        return out if rc == 0 else ""

    async def _verify_tenant(self, domain: str, db_name: str, skip_cert: bool) -> dict[str, str | bool | int]:
        nginx_conf = f"{NGINX_AVAILABLE}/{domain}.conf"
        enabled_link = f"{NGINX_ENABLED}/{domain}.conf"
        cert_path = f"/etc/letsencrypt/live/{domain}/fullchain.pem"

        local_code = await self._http_status("http://127.0.0.1/", host=domain)
        protocol = "http" if skip_cert else "https"
        public_code = await self._http_status(f"{protocol}://{domain}/")
        public_body = await self._http_body(f"{protocol}://{domain}/")
        public_body_ok = not any(marker in public_body for marker in INVALID_PUBLIC_MARKERS)
        db_tables = await self._table_count(db_name)

        nginx_ok = os.path.isfile(nginx_conf) and os.path.islink(enabled_link)
        tls_ok = skip_cert or os.path.isfile(cert_path)
        local_ok = local_code in HTTP_OK_CODES
        public_ok = public_code in HTTP_OK_CODES and public_body_ok
        live = nginx_ok and tls_ok and local_ok and public_ok and db_tables > 0

        return {
            "protocol": protocol,
            "local_code": local_code,
            "public_code": public_code,
            "public_body_ok": public_body_ok,
            "nginx_ok": nginx_ok,
            "tls_ok": tls_ok,
            "db_tables": db_tables,
            "live": live,
        }

    # ------------------------------------------------------------------
    # provision
    # ------------------------------------------------------------------
    async def _provision(self, args: dict, context: SkillContext) -> SkillResult:
        domain = _normalize_domain(args.get("domain", ""))
        err = _validate_domain(domain)
        if err:
            return SkillResult(success=False, error=err)

        app_name = (args.get("app_name") or _extract_app_name(domain)).strip().lower()
        source = args.get("source", "/var/www/finance")
        db_source = args.get("db_source", "finance")
        wipe = args.get("wipe_tenant_data", True)
        skip_cert = args.get("skip_cert", False)
        admin_phone = args.get("admin_phone")
        admin_password = args.get("admin_password")

        target = f"{TENANT_BASE_DIR}/{domain}"
        app_root = f"{target}/mbalala"
        env_file = f"{app_root}/.env"
        db_name = re.sub(r"[^a-z0-9_]", "_", app_name)
        nginx_conf = f"{NGINX_AVAILABLE}/{domain}.conf"
        enabled_link = f"{NGINX_ENABLED}/{domain}.conf"
        cert_path = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
        log_lines: list[str] = []

        def log(msg: str):
            logger.info(f"[tenant_provisioning] {msg}")
            log_lines.append(msg)

        # Pre-flight: check source exists
        if not os.path.isdir(source):
            return SkillResult(success=False, error=f"Source not found: {source}")

        # Pre-flight: stop only if a real tenant is already in place.
        existing_state = await self._verify_tenant(domain, db_name, skip_cert)
        if existing_state["live"]:
            protocol = str(existing_state["protocol"])
            message = f"Tenant {domain} is already live at {protocol}://{domain}"
            return SkillResult(
                success=True,
                output=message,
                data={
                    "domain": domain,
                    "app_name": app_name,
                    "target": target,
                    "database": db_name,
                    "db_tables": existing_state["db_tables"],
                    "url": f"{protocol}://{domain}",
                    "http_status": existing_state["public_code"],
                    "local_http_status": existing_state["local_code"],
                    "live": True,
                    "already_live": True,
                },
            )
        if os.path.isdir(target) or os.path.isfile(nginx_conf):
            log(f"[preflight] Existing partial tenant state detected for {domain}; continuing with recovery.")

        # ---- Step 1: Clone codebase ----
        log(f"[1/11] Cloning {source} -> {target}")
        os.makedirs(target, exist_ok=True)
        rc, _, err = await _run(
            ["rsync", "-a", "--delete", f"{source}/", f"{target}/"],
            timeout=120,
        )
        if rc != 0:
            return SkillResult(success=False, error=f"rsync failed: {err}", output="\n".join(log_lines))

        if not os.path.isfile(env_file):
            return SkillResult(success=False, error=f".env not found at {env_file}", output="\n".join(log_lines))

        # Remove copied runtime artifacts before any artisan command so the clone
        # does not boot with the source tenant's cached config/routes/logs.
        _reset_runtime_state(app_root)

        # ---- Step 3: Update .env ----
        log(f"[2/11] Updating .env for {domain}")
        source_env = _read_env(env_file)
        app_db_user = source_env.get("DB_USERNAME", LARAVEL_DB_USER)
        app_db_password = source_env.get("DB_PASSWORD", DB_PASS if app_db_user == DB_USER else "")

        env_updates = {
            "APP_NAME": app_name,
            "APP_URL": f"https://{domain}",
            "DB_DATABASE": db_name,
            "DB_USERNAME": app_db_user,
            "DB_PASSWORD": app_db_password,
            "SANCTUM_STATEFUL_DOMAINS": f"{domain},localhost,127.0.0.1",
            "SANAA_REDIRECT_URI": f"https://{domain}/auth/sanaa/callback",
            "MAIL_FROM_NAME": app_name,
        }
        for key, value in env_updates.items():
            _upsert_env_value(env_file, key, value)

        # ---- Step 3: Regenerate APP_KEY (security isolation) ----
        log(f"[3/11] Regenerating APP_KEY for tenant isolation")
        generated_key = "base64:" + base64.b64encode(os.urandom(32)).decode()
        _upsert_env_value(env_file, "APP_KEY", generated_key)
        log(f"  New APP_KEY generated: {generated_key[:20]}...")

        # ---- Step 4: Create database ----
        existing_tables = await self._table_count(db_name)
        if existing_tables > 0:
            log(f"[4/11] Resetting partial database '{db_name}' ({existing_tables} tables)")
            rc, _, err = await _mysql_exec(f"DROP DATABASE IF EXISTS `{db_name}`;", timeout=10)
            if rc != 0:
                return SkillResult(success=False, error=f"DB reset failed: {err}", output="\n".join(log_lines))

        log(f"[4/11] Creating database '{db_name}'")
        rc, _, err = await _mysql_exec(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
            timeout=10,
        )
        if rc != 0:
            return SkillResult(success=False, error=f"DB creation failed: {err}", output="\n".join(log_lines))

        # ---- Step 5: Clone data from source DB ----
        log(f"[5/11] Cloning data from '{db_source}' -> '{db_name}' (this may take a minute)")
        rc, err = await _mysql_clone_db(db_source, db_name, timeout=240)
        if rc != 0:
            return SkillResult(success=False, error=f"DB clone failed: {err}", output="\n".join(log_lines))

        # Verify table count
        table_count = str(await self._table_count(db_name))
        log(f"  Cloned {table_count} tables")

        # ---- Step 6: Grant DB access ----
        if app_db_user != DB_USER:
            log(f"[6/11] Granting '{app_db_user}' access to '{db_name}'")
            # Quote single quotes in the password for the raw SQL statement.
            grant_password = app_db_password.replace("\\", "\\\\").replace("'", "\\'")
            grant_sql = (
                f"CREATE USER IF NOT EXISTS '{app_db_user}'@'{DB_HOST}' "
                f"IDENTIFIED BY '{grant_password}'; "
                f"ALTER USER '{app_db_user}'@'{DB_HOST}' "
                f"IDENTIFIED BY '{grant_password}'; "
                f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{app_db_user}'@'{DB_HOST}'; "
                f"FLUSH PRIVILEGES;"
            )
            rc, _, err = await _mysql_exec(grant_sql, timeout=30)
            if rc != 0:
                log(f"  WARNING: Grant failed: {err}")
        else:
            log(f"[6/11] Skipping grant because app DB user is '{DB_USER}'")

        # ---- Step 7: Wipe tenant data ----
        if wipe:
            wipe_script = f"{target}/wipe-tenant-data.sh"
            if os.path.isfile(wipe_script):
                log(f"[7/11] Wiping tenant operational data (keeping users + config)")
                rc, out, err = await _run(
                    [
                        "bash", wipe_script,
                        "--db", db_name,
                        "--db-host", DB_HOST,
                        "--db-port", DB_PORT,
                        "--db-user", DB_USER,
                        "--db-pass", DB_PASS,
                        "--force",
                    ],
                    timeout=120,
                )
                if rc != 0:
                    log(f"  WARNING: Wipe failed: {err}")
                else:
                    # Count wiped tables from output
                    wiped = len([l for l in out.splitlines() if l.strip().startswith("- ")])
                    log(f"  Wiped {wiped} operational tables")
            else:
                log(f"[7/11] Wipe script not found at {wipe_script}, skipping")
        else:
            log(f"[7/11] Skipped tenant data wipe (data cloned as-is)")

        # ---- Step 8: Nginx config ----
        log(f"[8/11] Configuring nginx for {domain}")
        nginx_content = f"""server {{
    listen 80;
    server_name {domain} www.{domain};

    client_max_body_size 100M;

    root {app_root}/public;
    index index.php index.html;

    fastcgi_buffer_size 128k;
    fastcgi_buffers 256 16k;
    fastcgi_busy_buffers_size 256k;

    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

    location ~ \\.php$ {{
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:{PHP_FPM_SOCK};
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
    }}

    location ~ /\\.ht {{
        deny all;
    }}
}}
"""
        with open(nginx_conf, "w") as f:
            f.write(nginx_content)

        await _run(["ln", "-sfn", nginx_conf, enabled_link])

        rc, _, err = await _run([NGINX_BIN, "-t"])
        if rc != 0:
            return SkillResult(success=False, error=f"nginx config invalid: {err}", output="\n".join(log_lines))
        await _run([SYSTEMCTL_BIN, "reload", "nginx"])
        log(f"  nginx configured and reloaded")

        # ---- Step 9: TLS certificate ----
        if not skip_cert:
            log(f"[9/11] Issuing TLS certificate for {domain}")
            rc, out, err = await _run(
                [CERTBOT_BIN, "--nginx", "-d", domain, "--non-interactive", "--agree-tos", "--keep-until-expiring"],
                timeout=180,
            )
            if rc != 0:
                log(f"  WARNING: certbot failed: {err}")
                log(f"  Site will be HTTP-only until cert is manually issued")
            else:
                log(f"  TLS certificate issued successfully")
        else:
            log(f"[9/11] Skipping TLS (skip_cert=true)")

        # ---- Step 10: Laravel setup ----
        log(f"[10/11] Laravel setup (permissions, storage, migrations, cache)")

        # Permissions
        await _run([
            "chown", "-R", "www-data:www-data",
            f"{app_root}/storage", f"{app_root}/bootstrap/cache",
        ])
        await _run([
            "chmod", "-R", "775",
            f"{app_root}/storage", f"{app_root}/bootstrap/cache",
        ])

        # Storage symlink (critical for file uploads)
        rc, _, _ = await _run(["php", "artisan", "storage:link", "--force"], cwd=app_root, timeout=15)
        if rc == 0:
            log(f"  Storage symlink created")
        else:
            log(f"  WARNING: storage:link failed")

        # Clear old caches
        await _run(["php", "artisan", "optimize:clear"], cwd=app_root, timeout=30)

        # Migrations
        rc, out, err = await _run(["php", "artisan", "migrate", "--force"], cwd=app_root, timeout=60)
        if rc != 0:
            log(f"  WARNING: Migration failed: {err}")
        else:
            migration_lines = [l for l in out.strip().splitlines() if "DONE" in l]
            log(f"  Migrations applied: {len(migration_lines)} new")

        # Rebuild cache
        await _run(["php", "artisan", "config:cache"], cwd=app_root, timeout=30)
        await _run(["php", "artisan", "route:cache"], cwd=app_root, timeout=30)
        await _run(["php", "artisan", "view:cache"], cwd=app_root, timeout=30)
        log(f"  Config/route/view caches rebuilt")

        # ---- Step 10b: Scheduler cron + queue worker ----
        log(f"[10b/11] Setting up scheduler cron and queue worker")

        # Add cron entry for scheduler
        cron_line = f"* * * * * cd {shlex.quote(app_root)} && php artisan schedule:run >> {shlex.quote(app_root + '/storage/logs/scheduler.log')} 2>&1"
        rc, existing_cron, _ = await _run([CRONTAB_BIN, "-l"])
        if app_root not in (existing_cron if rc == 0 else ""):
            await _run_shell(
                f'({CRONTAB_BIN} -l 2>/dev/null; echo {shlex.quote(cron_line)}) | {CRONTAB_BIN} -'
            )
            log(f"  Scheduler cron added")
        else:
            log(f"  Scheduler cron already exists")

        # Add supervisor queue worker
        supervisor_conf = f"/etc/supervisor/conf.d/{app_name}-worker.conf"
        if not os.path.isfile(supervisor_conf):
            worker_config = (
                f"[program:{app_name}-worker]\n"
                f"process_name=%(program_name)s\n"
                f"command=php {app_root}/artisan queue:work --sleep=3 --tries=3 --max-time=3600 --queue=default,sms\n"
                f"autostart=true\n"
                f"autorestart=true\n"
                f"stopasgroup=true\n"
                f"killasgroup=true\n"
                f"user=www-data\n"
                f"numprocs=1\n"
                f"redirect_stderr=true\n"
                f"stdout_logfile={app_root}/storage/logs/worker.log\n"
                f"stopwaitsecs=3600\n"
            )
            with open(supervisor_conf, "w") as f:
                f.write(worker_config)
            await _run([SUPERVISORCTL_BIN, "reread"], timeout=15)
            await _run([SUPERVISORCTL_BIN, "update"], timeout=15)
            log(f"  Queue worker added and started via supervisor")
        else:
            log(f"  Queue worker config already exists")

        # ---- Step 10c: Admin credentials ----
        if admin_phone or admin_password:
            log(f"[10c/11] Setting admin credentials")
            php_parts = []
            if admin_phone:
                escaped_phone = admin_phone.replace("'", "\\'")
                php_parts.append(f"\\$user->phone = '{escaped_phone}';")
            if admin_password:
                escaped_pass = admin_password.replace("'", "\\'")
                php_parts.append(f"\\$user->password = bcrypt('{escaped_pass}');")
            php_code = (
                f"\\$user = \\App\\Models\\User::find(1); "
                f"{' '.join(php_parts)} "
                f"\\$user->save(); "
                f"echo 'Admin updated: ' . \\$user->f_name . ' ' . \\$user->l_name;"
            )
            rc, out, _ = await _run(
                ["php", "artisan", "tinker", "--execute=" + php_code], cwd=app_root,
                timeout=30,
            )
            if rc == 0:
                log(f"  {out.strip()}")
            else:
                log(f"  WARNING: Admin credential update failed")

        # ---- Step 11: Verify ----
        log(f"[11/11] Verifying tenant is live")
        verification = await self._verify_tenant(domain, db_name, skip_cert)
        if not verification["live"]:
            for attempt in range(1, 7):
                log(f"  Waiting for tenant readiness ({attempt}/6)")
                await asyncio.sleep(5)
                verification = await self._verify_tenant(domain, db_name, skip_cert)
                if verification["live"]:
                    log(f"  Tenant passed verification after retry {attempt}/6")
                    break

        protocol = str(verification["protocol"])
        local_code = str(verification["local_code"])
        public_code = str(verification["public_code"])
        is_live = bool(verification["live"])
        status_emoji = "LIVE" if is_live else "NEEDS ATTENTION"

        log(f"  Local: HTTP {local_code} | Public: HTTP {public_code}")
        if not verification["public_body_ok"]:
            log("  WARNING: Public response body does not match a finance tenant app")
        if not verification["tls_ok"] and not skip_cert:
            log(f"  WARNING: TLS certificate missing at {cert_path}")
        log(f"")
        log(f"{'=' * 50}")
        log(f"  Tenant: {app_name}")
        log(f"  URL:    {protocol}://{domain}")
        log(f"  Dir:    {target}")
        log(f"  DB:     {db_name} ({table_count} tables)")
        log(f"  TLS:    {'yes' if not skip_cert else 'no'}")
        log(f"  Status: {status_emoji}")
        log(f"{'=' * 50}")

        return SkillResult(
            success=is_live,
            output="\n".join(log_lines),
            data={
                "domain": domain,
                "app_name": app_name,
                "target": target,
                "database": db_name,
                "db_tables": table_count,
                "url": f"{protocol}://{domain}",
                "http_status": public_code,
                "local_http_status": local_code,
                "live": is_live,
            },
        )

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------
    async def _status(self, args: dict, context: SkillContext) -> SkillResult:
        domain = _normalize_domain(args.get("domain", ""))
        err = _validate_domain(domain)
        if err:
            return SkillResult(success=False, error=err)

        target = f"{TENANT_BASE_DIR}/{domain}"
        app_root = f"{target}/mbalala"
        env_file = f"{app_root}/.env"
        env_values = _read_env(env_file)
        db_name = env_values.get("DB_DATABASE", _extract_app_name(domain))
        checks: dict[str, str | bool] = {}

        # Filesystem checks
        checks["directory"] = os.path.isdir(target)
        checks["env_file"] = os.path.isfile(env_file)
        checks["storage_link"] = os.path.islink(f"{app_root}/public/storage")
        checks["nginx_config"] = os.path.isfile(f"{NGINX_AVAILABLE}/{domain}.conf")
        checks["nginx_enabled"] = os.path.islink(f"{NGINX_ENABLED}/{domain}.conf")

        # TLS check
        cert_path = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
        checks["tls_cert"] = os.path.isfile(cert_path)

        verification = await self._verify_tenant(domain, db_name, skip_cert=False)
        checks["local_status"] = f"HTTP {verification['local_code']}"
        checks["https_status"] = f"HTTP {verification['public_code']}"
        checks["public_app_match"] = bool(verification["public_body_ok"])

        # Database check
        checks["db_tables"] = str(verification["db_tables"])

        # DB size
        rc, out, _ = await _mysql_exec(
            "SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) "
            f"FROM information_schema.tables WHERE table_schema='{db_name}';",
            database="information_schema",
            timeout=10,
        )
        checks["db_size_mb"] = f"{out.strip()} MB" if rc == 0 and out.strip() != "NULL" else "N/A"

        # Disk usage
        if os.path.isdir(target):
            rc, out, _ = await _run(["du", "-sh", target], timeout=10)
            checks["disk_usage"] = out.strip().split()[0] if rc == 0 and out.strip() else "N/A"

        # Build output
        lines = [f"Tenant Health: {domain}", ""]
        all_ok = True
        for key, val in checks.items():
            if isinstance(val, bool):
                ok = val
                display = "yes" if val else "NO"
            elif key in ("https_status", "local_status"):
                ok = str(val).replace("HTTP ", "") in HTTP_OK_CODES
                display = str(val)
            elif key in ("db_tables",):
                ok = val not in ("0", "N/A", "")
                display = val
            else:
                ok = True
                display = str(val)

            marker = "OK" if ok else "FAIL"
            if not ok:
                all_ok = False
            lines.append(f"  {key:20s} {display:>12s}  [{marker}]")

        return SkillResult(
            success=all_ok,
            output="\n".join(lines),
            data=checks,
        )

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------
    async def _list_tenants(self, args: dict, context: SkillContext) -> SkillResult:
        """List all sanaa tenant sites by scanning tenant directories and nginx configs."""
        tenants = []
        if os.path.isdir(TENANT_BASE_DIR):
            for domain in sorted(os.listdir(TENANT_BASE_DIR)):
                target = f"{TENANT_BASE_DIR}/{domain}"
                if not os.path.isdir(target):
                    continue
                if not re.match(r"^[a-z0-9\-]+\.sanaa\.(ug|co)$", domain):
                    continue
                if not os.path.isdir(f"{target}/mbalala"):
                    continue

                env_values = _read_env(f"{target}/mbalala/.env")
                db_name = env_values.get("DB_DATABASE", _extract_app_name(domain))
                db_tables = str(await self._table_count(db_name))
                conf_name = f"{domain}.conf"

                tenants.append({
                    "domain": domain,
                    "app_name": _extract_app_name(domain),
                    "enabled": os.path.islink(f"{NGINX_ENABLED}/{conf_name}"),
                    "configured": os.path.isfile(f"{NGINX_AVAILABLE}/{conf_name}"),
                    "directory": True,
                    "db_tables": db_tables,
                    "path": target,
                })

        lines = [f"Sanaa Finance Tenants ({len(tenants)}):", ""]
        for t in tenants:
            if t["enabled"]:
                status = "ACTIVE"
            elif t["configured"]:
                status = "DISABLED"
            else:
                status = "INCOMPLETE"
            lines.append(f"  {t['domain']:30s} [{status:8s}] DB: {t['db_tables']:>3s} tables")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={"tenants": tenants, "count": len(tenants)},
        )

    # ------------------------------------------------------------------
    # disable
    # ------------------------------------------------------------------
    async def _disable_tenant(self, args: dict, context: SkillContext) -> SkillResult:
        domain = _normalize_domain(args.get("domain", ""))
        err = _validate_domain(domain)
        if err:
            return SkillResult(success=False, error=err)

        enabled_link = f"{NGINX_ENABLED}/{domain}.conf"
        if not os.path.islink(enabled_link):
            return SkillResult(success=False, error=f"{domain} is already disabled (no symlink)")

        os.unlink(enabled_link)
        rc, _, err = await _run([NGINX_BIN, "-t"])
        if rc != 0:
            return SkillResult(success=False, error=f"nginx test failed after disable: {err}")

        await _run([SYSTEMCTL_BIN, "reload", "nginx"])

        return SkillResult(
            success=True,
            output=f"Tenant {domain} disabled. Nginx symlink removed and reloaded.",
            data={"domain": domain, "action": "disabled"},
        )

    # ------------------------------------------------------------------
    # enable
    # ------------------------------------------------------------------
    async def _enable_tenant(self, args: dict, context: SkillContext) -> SkillResult:
        domain = _normalize_domain(args.get("domain", ""))
        err = _validate_domain(domain)
        if err:
            return SkillResult(success=False, error=err)

        nginx_conf = f"{NGINX_AVAILABLE}/{domain}.conf"
        enabled_link = f"{NGINX_ENABLED}/{domain}.conf"

        if not os.path.isfile(nginx_conf):
            return SkillResult(success=False, error=f"No nginx config found: {nginx_conf}")

        if os.path.islink(enabled_link):
            return SkillResult(success=False, error=f"{domain} is already enabled")

        await _run(["ln", "-sfn", nginx_conf, enabled_link])
        rc, _, err = await _run([NGINX_BIN, "-t"])
        if rc != 0:
            os.unlink(enabled_link)
            return SkillResult(success=False, error=f"nginx test failed, reverted: {err}")

        await _run([SYSTEMCTL_BIN, "reload", "nginx"])

        return SkillResult(
            success=True,
            output=f"Tenant {domain} re-enabled. Nginx symlink restored and reloaded.",
            data={"domain": domain, "action": "enabled"},
        )
