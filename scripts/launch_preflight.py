from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.backup_service import database_integrity, latest_backup, sqlite_database_path, verify_restore


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    message: str


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _http_json(url: str, *, method: str = "GET") -> tuple[int, dict, dict[str, str]]:
    request = Request(url, method=method)
    with urlopen(request, timeout=6) as response:
        body = json.loads(response.read().decode("utf-8"))
        return response.status, body, {key.lower(): value for key, value in response.headers.items()}


def _check_certificate(public_base: str) -> Check:
    host = urlparse(public_base).hostname
    if not host:
        return Check("HTTPS certificate", "warning", "public base was not provided")
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=5) as connection:
            with context.wrap_socket(connection, server_hostname=host) as secure:
                expiry = datetime.strptime(secure.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z")
        days = (expiry - datetime.utcnow()).days
        if days < 7:
            return Check("HTTPS certificate", "failed", f"certificate expires in {days} days")
        if days < 21:
            return Check("HTTPS certificate", "warning", f"certificate expires in {days} days")
        return Check("HTTPS certificate", "passed", f"certificate expires in {days} days")
    except (OSError, KeyError, ValueError) as exc:
        return Check("HTTPS certificate", "failed", f"certificate check failed: {type(exc).__name__}")


def _env_value(env: dict[str, str], key: str, default: str = "") -> str:
    return env.get(key, os.getenv(key, default)).strip()


def _display_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _redis_public_listener(port: int) -> bool | None:
    ss = shutil.which("ss")
    if not ss:
        return None
    try:
        result = subprocess.run([ss, "-lnt"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    listeners = [line for line in result.stdout.splitlines() if f":{port}" in line]
    public_markers = (f"0.0.0.0:{port}", f"[::]:{port}", f"*:{port}")
    return any(any(marker in line for marker in public_markers) for line in listeners)


def run_checks(
    *,
    env_path: Path,
    local_base: str,
    public_base: str,
    backup_dir: Path,
    frontend_env_path: Path | None = None,
    project_root: Path = ROOT,
) -> list[Check]:
    env = _read_env(env_path)
    public_env = {**env, **(_read_env(frontend_env_path) if frontend_env_path else {})}
    checks: list[Check] = []
    environment = _env_value(env, "APP_ENV", "development").lower()
    checks.append(Check("production environment", "passed" if environment in {"production", "prod"} else "failed", f"APP_ENV is {environment or 'missing'}"))

    weak = {"", "change-me", "dev-only-secret"}
    secret_names = ["ANONYMOUS_COOKIE_SECRET", "DOWNLOAD_SIGNING_SECRET", "IP_HASH_SECRET"]
    weak_count = sum(_env_value(env, name) in weak for name in secret_names)
    checks.append(Check("production secrets", "failed" if weak_count else "passed", f"weak or missing secrets: {weak_count}" if weak_count else "all required secrets are configured"))

    if env_path.exists() and os.name != "nt":
        mode = env_path.stat().st_mode & 0o777
        checks.append(Check("environment file permissions", "failed" if mode & 0o077 else "passed", f"mode is {oct(mode)}"))
    else:
        checks.append(Check("environment file permissions", "warning", "environment file is missing or permissions are not available on this platform"))

    hosts = _env_value(env, "ALLOWED_HOSTS")
    origins = _env_value(env, "ALLOWED_ORIGINS")
    polluted = any(marker in hosts + origins for marker in "[]()")
    host_ok = bool(hosts and origins and not polluted and "localhost" not in origins.lower())
    checks.append(Check("host and origin allowlist", "passed" if host_ok else "failed", "production host/origin allowlist is configured" if host_ok else "allowlist is missing, local-only, or contains markup"))

    redis_url = _env_value(env, "REDIS_URL")
    parsed_redis = urlparse(redis_url)
    redis_local = parsed_redis.hostname in {"127.0.0.1", "localhost", "::1"}
    redis_public = _redis_public_listener(parsed_redis.port or 6379) if redis_local else None
    redis_ready = False
    if redis_local:
        try:
            import redis
            redis_ready = bool(redis.Redis.from_url(redis_url, socket_timeout=2).ping())
        except Exception:
            redis_ready = False
    redis_ok = redis_local and redis_ready and redis_public is not True
    if redis_public is True:
        redis_message = "Redis has a public listener"
    elif redis_ok:
        redis_message = "Redis is reachable through the local address and no public listener was detected"
    else:
        redis_message = "Redis is unavailable or not restricted to a local address"
    checks.append(Check("Redis", "passed" if redis_ok else "failed", redis_message))

    database_url = _env_value(env, "DATABASE_URL", f"sqlite:///{project_root / 'backend' / 'data' / 'resume_coach.db'}")
    try:
        database_path = sqlite_database_path(database_url, base_dir=project_root)
        valid, integrity = database_integrity(database_path)
        checks.append(Check("database integrity", "passed" if valid else "failed", f"integrity_check: {integrity}"))
    except ValueError:
        checks.append(Check("database integrity", "warning", "non-SQLite database requires a provider-specific check"))

    directory_failures = [
        _display_path(path, project_root) for path in [
            project_root / "backend" / "logs",
            project_root / "backend" / "outputs",
            project_root / "backend" / "reports",
            backup_dir,
        ] if not path.exists() or not os.access(path, os.W_OK)
    ]
    checks.append(Check("runtime directories", "failed" if directory_failures else "passed", f"not writable: {', '.join(directory_failures)}" if directory_failures else "runtime directories are writable"))

    backup = latest_backup(backup_dir)
    if not backup:
        checks.append(Check("recent verified backup", "failed", "no production backup found"))
    else:
        age_hours = (datetime.now().timestamp() - backup.stat().st_mtime) / 3600
        try:
            verified = bool(verify_restore(backup)["ok"])
        except Exception:
            verified = False
        status = "failed" if not verified or age_hours > 168 else "warning" if age_hours > 48 else "passed"
        checks.append(Check("recent verified backup", status, f"latest backup is {age_hours:.1f} hours old and verification={'ok' if verified else 'failed'}"))

    disk = shutil.disk_usage(project_root)
    free_mb = disk.free // 1024 // 1024
    disk_status = "failed" if free_mb < 500 else "warning" if free_mb < 1024 else "passed"
    checks.append(Check("disk capacity", disk_status, f"free disk: {free_mb} MB"))

    dist = project_root / "frontend" / "dist"
    frontend_ready = (dist / "index.html").exists() and any((dist / "assets").glob("*.js"))
    checks.append(Check("frontend build", "passed" if frontend_ready else "failed", "frontend/dist is ready" if frontend_ready else "frontend/dist is missing or incomplete"))

    try:
        live_status, live, _ = _http_json(f"{local_base.rstrip('/')}/api/health/live")
        ready_status, ready, _ = _http_json(f"{local_base.rstrip('/')}/api/health/ready")
        health_ok = live_status == 200 and ready_status == 200 and bool(live.get("ok")) and bool(ready.get("ok"))
        checks.append(Check("backend health", "passed" if health_ok else "failed", f"live={live_status}, ready={ready_status}"))
        openapi_status, openapi, _ = _http_json(f"{local_base.rstrip('/')}/openapi.json")
        docx_route = "/api/resume/docx" in openapi.get("paths", {})
        checks.append(Check("DOCX route", "passed" if openapi_status == 200 and docx_route else "failed", "DOCX generation route is registered" if docx_route else "DOCX route is missing"))
    except Exception as exc:
        checks.append(Check("backend health", "failed", f"local health request failed: {type(exc).__name__}"))
        checks.append(Check("DOCX route", "failed", "OpenAPI route check was unavailable"))

    icp_number = _env_value(public_env, "VITE_ICP_NUMBER")
    checks.append(Check("ICP footer configuration", "passed" if icp_number else "warning", "ICP number is configured" if icp_number else "ICP number is not configured"))
    privacy_contact = _env_value(public_env, "VITE_PRIVACY_CONTACT_EMAIL")
    checks.append(Check("privacy contact", "passed" if privacy_contact else "warning", "privacy contact is configured" if privacy_contact else "privacy contact email is not configured"))

    dry_run = _env_value(env, "RATE_LIMIT_DRY_RUN", "true").lower() in {"1", "true", "yes", "on"}
    checks.append(Check("rate limit enforcement", "warning" if dry_run else "passed", "rate limiting is still in observation mode" if dry_run else "rate limiting is enforced"))

    nginx = shutil.which("nginx")
    if nginx:
        result = subprocess.run([nginx, "-T"], capture_output=True, text=True, timeout=10)
        conflict = "conflicting server name" in (result.stdout + result.stderr).lower()
        status = "failed" if result.returncode != 0 or conflict else "passed"
        checks.append(Check("Nginx configuration", status, "configuration has duplicate server names or syntax errors" if status == "failed" else "configuration syntax is valid without duplicate server-name warnings"))
    else:
        checks.append(Check("Nginx configuration", "warning", "nginx command is unavailable on this host"))

    if public_base:
        checks.append(_check_certificate(public_base))
        try:
            homepage = Request(public_base.rstrip("/") + "/", method="GET")
            with urlopen(homepage, timeout=6) as response:
                homepage_ok = response.status == 200 and bool(response.read(512))
            identity_status, _, headers = _http_json(public_base.rstrip("/") + "/api/identity", method="POST")
            cookie = headers.get("set-cookie", "").lower()
            identity_ok = identity_status == 200 and all(flag in cookie for flag in ["httponly", "secure", "samesite=lax"])
            checks.append(Check("public homepage", "passed" if homepage_ok else "failed", "public homepage is reachable" if homepage_ok else "public homepage check failed"))
            checks.append(Check("public anonymous identity", "passed" if identity_ok else "failed", "signed secure cookie is issued" if identity_ok else "identity cookie flags are incomplete"))
        except Exception as exc:
            checks.append(Check("public homepage", "failed", f"public request failed: {type(exc).__name__}"))
            checks.append(Check("public anonymous identity", "failed", "public identity endpoint was unavailable"))
    else:
        checks.append(Check("public deployment", "warning", "--public-base was not provided"))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Resume Coach before public-beta launch.")
    parser.add_argument("--env", type=Path, default=Path("/etc/resume-coach/resume-coach.env") if os.name != "nt" else ROOT / ".env")
    parser.add_argument("--local-base", default="http://127.0.0.1:8001")
    parser.add_argument("--public-base", default="")
    parser.add_argument("--backups", type=Path, default=ROOT / "backend" / "backups")
    parser.add_argument("--frontend-env", type=Path, default=ROOT / "frontend" / ".env.production")
    args = parser.parse_args()
    checks = run_checks(
        env_path=args.env,
        local_base=args.local_base,
        public_base=args.public_base,
        backup_dir=args.backups,
        frontend_env_path=args.frontend_env,
    )
    icons = {"passed": "PASS", "warning": "WARN", "failed": "FAIL"}
    for check in checks:
        print(f"[{icons[check.status]}] {check.name}: {check.message}")
    print()
    print(f"passed={sum(item.status == 'passed' for item in checks)} warning={sum(item.status == 'warning' for item in checks)} failed={sum(item.status == 'failed' for item in checks)}")
    if any(item.status == "failed" for item in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
