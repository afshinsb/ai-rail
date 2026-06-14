from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any, Callable

RunFunc = Callable[[list[str], int], subprocess.CompletedProcess[str]]


def gh_available() -> bool:
    return shutil.which("gh") is not None


def detect_repo_from_gh(run_func: RunFunc) -> str | None:
    if not gh_available():
        return None
    try:
        result = run_func(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], 10)
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def detect_default_branch_from_gh(run_func: RunFunc) -> str | None:
    if not gh_available():
        return None
    try:
        result = run_func(["gh", "repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"], 10)
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def parse_github_remote_url(url: str) -> str | None:
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return match.group(1) if match else None


def fetch_github_issues(repo: str, state_value: str, run_func: RunFunc, limit: int = 100) -> list[dict[str, Any]]:
    gh = shutil.which("gh") or "gh"
    result = run_func(
        [
            gh, "issue", "list",
            "--repo", repo,
            "--state", state_value,
            "--limit", str(limit),
            "--json", "number,title,body,updatedAt,state",
        ],
        45,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "GitHub issue list failed.")
    return json.loads(result.stdout or "[]")
