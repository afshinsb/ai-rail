from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable


def checks_result(checks_path: Path) -> str:
    if not checks_path.exists():
        return "missing"
    text = checks_path.read_text(encoding="utf-8", errors="replace")
    codes = [int(x) for x in re.findall(r"Exit code:\s*(\d+)", text)]
    if not codes:
        return "unknown"
    return "passed" if all(c == 0 for c in codes) else "failed"


def check_block_reason(
    *,
    checks_path: Path,
    changed_files_func: Callable[[], list[str]],
    artifact_is_fresh_func: Callable[[Path, list[str]], bool],
) -> str | None:
    state_value = checks_result(checks_path)
    if state_value != "passed":
        return state_value
    if not artifact_is_fresh_func(checks_path, changed_files_func()):
        return "stale"
    return None


def verify_fingerprint(
    check_commands: list[str],
    *,
    active_issue_number: Any,
    branch: str,
    changed_files: list[str],
    untracked_files: list[str],
    git_diff: str,
    untracked_text: str,
) -> str:
    payload = {
        "active_issue": active_issue_number,
        "branch": branch,
        "changed_files": changed_files,
        "untracked_files": untracked_files,
        "git_diff": git_diff,
        "untracked_text": untracked_text,
        "check_commands": check_commands,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8", errors="replace")
    return hashlib.sha256(encoded).hexdigest()


def configured_check_commands(config: dict[str, Any], override: list[str] | None = None) -> list[str]:
    if override:
        return override
    checks = config.get("checks") or []
    return [str(command) for command in checks]


def write_verify_snapshot(
    path: Path,
    *,
    check_commands: list[str],
    check_result: str,
    active_issue_number: Any,
    branch: str,
    changed_files: list[str],
    untracked_files: list[str],
    fingerprint: str,
    created_at: str,
) -> None:
    snapshot = {
        "version": 1,
        "created_at": created_at,
        "active_issue": active_issue_number,
        "branch": branch,
        "changed_files": changed_files,
        "untracked_files": untracked_files,
        "check_commands": check_commands,
        "check_result": check_result,
        "fingerprint": fingerprint,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")


def validate_verify_snapshot(
    snapshot: Any,
    *,
    check_commands: list[str],
    active_issue_number: Any,
    branch: str,
    fingerprint: str,
) -> tuple[bool, str]:
    if not isinstance(snapshot, dict) or snapshot.get("check_result") != "passed":
        return False, "Error: no passing verify snapshot found. Run: rail v"
    if snapshot.get("active_issue") != active_issue_number:
        return False, "Error: active issue changed after last review. Run: rail v"
    if snapshot.get("branch") != branch:
        return False, "Error: branch changed after last review. Run: rail v"
    if snapshot.get("check_commands") != check_commands:
        return False, "Error: check config changed after last review. Run: rail v"
    if snapshot.get("fingerprint") != fingerprint:
        return False, "Error: files changed after last review. Run: rail v"
    return True, "[rail] Verified snapshot is fresh."


def refresh_review_and_check_artifacts(review_path: Path, checks_path: Path) -> None:
    now = dt.datetime.now().timestamp()
    for path in (review_path, checks_path):
        if path.exists():
            os.utime(path, (now, now))
