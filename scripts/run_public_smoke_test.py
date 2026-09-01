from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.observability_common import BEIJING, load_jsonl, parse_time, safe_short_commit, write_json
from backend.app.services.resume_visible_output_service import (
    find_internal_field_leaks,
    visible_output_text,
)


FORBIDDEN_TEXT = (
    "综合经历", "其他经历", "原文截断", "需补充原文",
    "技术动作", "围绕该段经历完成相关任务",
)


class SmokeFailure(RuntimeError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})


class HttpClient:
    def __init__(self, base: str, *, origin: str | None = None):
        self.base = base.rstrip("/")
        self.origin = (origin or self.base).rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))

    def request(self, path: str, *, method: str = "GET", payload: dict | None = None, origin: bool = False) -> tuple[int, bytes, dict[str, str]]:
        headers = {"X-Request-ID": f"req_{uuid.uuid4().hex}"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if origin:
            headers["Origin"] = self.origin
        request = Request(self.base + path, data=body, method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=120) as response:
                return response.status, response.read(), {key.lower(): value for key, value in response.headers.items()}
        except HTTPError as exc:
            return exc.code, exc.read(), {key.lower(): value for key, value in exc.headers.items()}
        except URLError as exc:
            raise SmokeFailure(f"network_error:{type(exc.reason).__name__}") from exc

    def json(self, path: str, *, method: str = "GET", payload: dict | None = None, origin: bool = False) -> tuple[int, dict, dict[str, str]]:
        status, body, headers = self.request(path, method=method, payload=payload, origin=origin)
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SmokeFailure(f"invalid_json:{path}") from exc
        return status, parsed, headers


def validate_generation(generation: dict) -> dict[str, Any]:
    payload = generation.get("result") if isinstance(generation, dict) else None
    sections = payload.get("resume_sections") if isinstance(payload, dict) else None
    projects = sections.get("projects") if isinstance(sections, dict) else None
    if not isinstance(projects, list) or not projects:
        raise SmokeFailure("empty_projects")
    empty_projects = sum(
        not str(project.get("intro") or "").strip()
        and not str(project.get("role") or "").strip()
        and not any(str(item).strip() for item in project.get("details", []) or [])
        for project in projects if isinstance(project, dict)
    )
    text = visible_output_text(payload)
    forbidden = [marker for marker in FORBIDDEN_TEXT if marker in text]
    leaks = find_internal_field_leaks(payload)
    if empty_projects:
        raise SmokeFailure("empty_project_body")
    if forbidden:
        raise SmokeFailure("forbidden_output_marker")
    if leaks:
        raise SmokeFailure(
            "internal_field_leak",
            details={
                "leaked_markers": sorted({leak.marker for leak in leaks}),
                "affected_field_paths": sorted({leak.field_path for leak in leaks}),
                "internal_field_leak_count": len(leaks),
            },
        )
    return {
        "project_count": len(projects),
        "empty_project_count": empty_projects,
        "forbidden_marker_count": len(forbidden),
        "internal_field_leak_count": len(leaks),
    }


def run_shallow(client: HttpClient, *, expected_version: str = "", expected_commit: str = "") -> dict:
    checks: list[dict[str, Any]] = []
    status, homepage, headers = client.request("/")
    html = homepage.decode("utf-8", errors="ignore")
    checks.append({"name": "homepage", "passed": status == 200 and bool(html)})
    for route in ["/#/privacy", "/#/terms", "/#/ai"]:
        route_status, body, _ = client.request(route)
        checks.append({"name": f"legal:{route}", "passed": route_status == 200 and bool(body)})
    live_status, live, _ = client.json("/api/health/live")
    ready_status, ready, _ = client.json("/api/health/ready")
    checks.append({"name": "health_live", "passed": live_status == 200 and bool(live.get("ok"))})
    checks.append({"name": "health_ready", "passed": ready_status == 200 and bool(ready.get("ok"))})
    identity_status, _, identity_headers = client.json("/api/identity", method="POST")
    cookie = identity_headers.get("set-cookie", "").lower()
    checks.append({"name": "anonymous_cookie", "passed": identity_status == 200 and all(item in cookie for item in ["httponly", "samesite=lax"])})
    security_headers = {key.lower(): value for key, value in headers.items()}
    checks.append({"name": "security_headers", "passed": "x-content-type-options" in security_headers and ("content-security-policy" in security_headers or "x-frame-options" in security_headers)})
    html_version = re.search(r'name="resume-coach-version" content="([^"]+)"', html)
    html_commit = re.search(r'name="resume-coach-commit" content="([^"]+)"', html)
    version = str(live.get("version") or "")
    commit = safe_short_commit(live.get("commit"))
    version_match = bool(html_version and html_version.group(1) == version)
    commit_match = bool(html_commit and safe_short_commit(html_commit.group(1)) == commit)
    if expected_version:
        version_match = version_match and version == expected_version
    if expected_commit:
        commit_match = commit_match and commit == safe_short_commit(expected_commit)
    checks.append({"name": "release_version", "passed": version_match})
    checks.append({"name": "release_commit", "passed": commit_match})
    return {
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "release": {"version": version, "commit": commit, "build_time": live.get("build_time")},
    }


SMOKE_CASES = [
    {
        "target_role": "后端开发",
        "raw_input": "独立开发课程资料问答项目，使用 Python、FastAPI 和 SQLite，实现文档解析、检索问答与引用展示，并通过测试集检查回答质量。",
    },
    {
        "target_role": "前端开发",
        "raw_input": "独立开发校园活动管理项目，使用 TypeScript、React 完成活动列表、报名表单和状态展示，并根据同学试用反馈调整交互流程。",
    },
]


def _generation_quality_summary(
    logs_dir: Path,
    attempt_id: str,
    result_id: int,
    started_at: datetime,
) -> dict[str, Any]:
    matching = []
    for row in load_jsonl(logs_dir, "generation_stability"):
        if str(row.get("attempt_id") or "") != attempt_id:
            continue
        if int(row.get("generation_result_id") or 0) != result_id:
            continue
        created_at = parse_time(row.get("created_at"))
        if created_at is not None and created_at >= started_at:
            matching.append(row)
    if not matching:
        raise SmokeFailure("generation_quality_summary_missing")
    latest = max(matching, key=lambda row: parse_time(row.get("created_at")) or started_at)
    return {
        "unresolved_critical_issue_count": int(latest.get("unresolved_critical_issue_count") or 0),
        "high_value_fact_coverage": float(latest.get("high_value_fact_coverage") or 0),
        "projects_missing_source_id": int(latest.get("projects_missing_source_id") or 0),
    }


def run_full(
    client: HttpClient,
    *,
    case_index: int = 0,
    poll_seconds: int = 180,
    logs_dir: Path = ROOT / "backend" / "logs",
) -> dict:
    started_at = datetime.now(BEIJING)
    attempt_id = f"smoke_{uuid.uuid4().hex}"
    identity = {"anonymous_user_id": "smoke_client", "session_id": f"smoke_session_{uuid.uuid4().hex[:12]}"}
    case = SMOKE_CASES[case_index % len(SMOKE_CASES)]
    result_id = None
    file_id = None
    request_id = ""
    cleanup_attempted = False
    cleanup_passed = False
    failure: Exception | None = None
    output: dict[str, Any] = {}
    try:
        status, _, _ = client.json("/api/identity", method="POST")
        if status != 200:
            raise SmokeFailure("identity_failed")
        event_status, _, _ = client.json("/api/events", method="POST", payload={
            **identity,
            "event_name": "public_smoke_test",
            "payload": {"attempt_id": attempt_id, "mode": "full"},
        })
        if event_status != 200:
            raise SmokeFailure("smoke_marker_failed")
        payload = {
            **identity, **case, "attempt_id": attempt_id, "mode": "full_resume",
            "packaging_level": "大胆", "experience_type": "项目经历",
        }
        status, task, submit_headers = client.json("/api/generation-attempts", method="POST", payload=payload)
        request_id = submit_headers.get("x-request-id", "")
        if status != 202:
            raise SmokeFailure(f"generation_submit_status_{status}")
        deadline = time.time() + poll_seconds
        while time.time() < deadline and task.get("status") not in {"succeeded", "failed", "expired"}:
            time.sleep(1.2)
            status, task, _ = client.json(f"/api/generation-attempts/{attempt_id}")
            if status != 200:
                raise SmokeFailure(f"generation_poll_status_{status}")
        if task.get("status") != "succeeded" or not isinstance(task.get("generation"), dict):
            raise SmokeFailure(f"generation_{task.get('status', 'timeout')}")
        generation = task["generation"]
        result_id = int(generation["generation_result_id"])
        output.update(validate_generation(generation))
        quality = _generation_quality_summary(logs_dir, attempt_id, result_id, started_at)
        output.update(quality)
        if quality["unresolved_critical_issue_count"]:
            raise SmokeFailure("unresolved_quality_critical")
        if quality["projects_missing_source_id"]:
            raise SmokeFailure("missing_source_experience_id")
        status, docx, _ = client.json("/api/resume/docx", method="POST", payload={
            **identity, "generation_result_id": result_id, "version_type": "recommended",
        })
        if status != 200:
            raise SmokeFailure(f"docx_create_status_{status}")
        file_id = int(docx["file_id"])
        download_status, body, _ = client.request(str(docx["download_url"]))
        if download_status != 200 or not body.startswith(b"PK") or len(body) < 1000:
            raise SmokeFailure("docx_download_invalid")
        output["docx_bytes"] = len(body)
    except Exception as exc:
        failure = exc
    finally:
        cleanup_attempted = True
        try:
            status, deleted, _ = client.json("/api/privacy/my-data", method="DELETE", origin=True)
            cleanup_passed = status == 200 and bool(deleted.get("ok"))
        except Exception:
            cleanup_passed = False
    context = {
        "attempt_id": attempt_id,
        "request_id": request_id,
        "generation_result_id": result_id,
        "file_id": file_id,
        "cleanup_attempted": cleanup_attempted,
        "cleanup_passed": cleanup_passed,
    }
    if not cleanup_passed:
        details = dict(getattr(failure, "details", {}) or {})
        if failure is not None:
            details["original_error_code"] = str(failure)[:80]
        raise SmokeFailure("cleanup_failed", details={**details, **context}) from failure
    if failure:
        if isinstance(failure, SmokeFailure):
            raise SmokeFailure(failure.code, details={**failure.details, **context}) from failure
        raise SmokeFailure(
            "unexpected_full_smoke_error",
            details={"original_error_type": type(failure).__name__, **context},
        ) from failure
    return {
        "passed": True,
        **context,
        **output,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run public Resume Coach smoke checks.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--mode", choices=["shallow", "full"], default="shallow")
    parser.add_argument("--out", type=Path, default=ROOT / "backend" / "reports")
    parser.add_argument("--case", type=int, default=int(datetime.now(BEIJING).strftime("%j")))
    parser.add_argument("--expected-version", default="")
    parser.add_argument("--expected-commit", default="")
    parser.add_argument("--origin", default="", help="Allowed browser origin for deletion checks; defaults to --base.")
    args = parser.parse_args()
    report = {
        "created_at": datetime.now(BEIJING).isoformat(),
        "mode": args.mode,
        "base_host": re.sub(r"^https?://", "", args.base).split("/", 1)[0],
        "passed": False,
    }
    try:
        client = HttpClient(args.base, origin=args.origin or args.base)
        result = (
            run_shallow(client, expected_version=args.expected_version, expected_commit=args.expected_commit)
            if args.mode == "shallow"
            else run_full(client, case_index=args.case)
        )
        report.update(result)
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error_code"] = str(exc)[:80]
        if isinstance(exc, SmokeFailure):
            report.update(exc.details)
    path = write_json(args.out / f"public-smoke-{args.mode}-latest.json", report)
    print(path)
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
