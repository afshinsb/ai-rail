#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


VERSION = "0.1.0a16"

RAIL_DIR = Path(__file__).resolve().parent
ROOT = RAIL_DIR.parent
CONFIG_PATH = RAIL_DIR / "config.json"
AGENTS_PATH = RAIL_DIR / "AGENTS.md"
PROJECT_PATH = RAIL_DIR / "PROJECT.md"
STATE_DIR = RAIL_DIR / "state"
ACTIVE_PATH = STATE_DIR / "active.json"
LAST_REVIEW_PATH = STATE_DIR / "last-review.md"
LAST_CHECKS_PATH = STATE_DIR / "last-checks.md"
LAST_CODEX_PROMPT_PATH = STATE_DIR / "last-codex-prompt.md"
LAST_REVIEW_PROMPT_PATH = STATE_DIR / "last-chatgpt-review-prompt.md"
REMOTE_MEMORY_START = "<!-- AI RAIL PROJECT MEMORY START -->"
REMOTE_MEMORY_END = "<!-- AI RAIL PROJECT MEMORY END -->"
LOCAL_ROADMAP_START = "<!-- AI RAIL MANAGED ROADMAP START -->"
LOCAL_ROADMAP_END = "<!-- AI RAIL MANAGED ROADMAP END -->"
RAIL_ROADMAP_START = "<!-- AI RAIL ROADMAP START -->"
RAIL_ROADMAP_END = "<!-- AI RAIL ROADMAP END -->"
ROADMAP_LABEL = "ai-rail-roadmap"


ISSUE_TEMPLATE = """## Goal

## Current problem

## Scope
-

## Out of scope
-

## Implementation notes
-

## Acceptance checks
-

## Codex rules
- Keep scope small.
- Touch only necessary files.
- Do not commit.
- Do not run broad/full test suites unless the issue explicitly asks for them.
- Run only focused checks related to the issue, or the exact checks requested by the user or AI Rail.
- Do not close the issue.
- Do not create unrelated roadmaps or task folders.
- Stop and explain if this requires broader architectural changes.
"""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def unique_backup_path(path: Path) -> Path:
    i = 2
    first = path.with_name(f"{path.name}.rail.bak.1")
    if not first.exists():
        return first
    while True:
        candidate = path.with_name(f"{path.name}.rail.bak.{i}")
        if not candidate.exists():
            return candidate
        i += 1


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_config() -> dict[str, Any]:
    return load_json(CONFIG_PATH, {})


def run(cmd: list[str], timeout: int = 60, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"Command failed: {' '.join(cmd)}")
    return result


def gh_available() -> bool:
    return shutil.which("gh") is not None


def git_available() -> bool:
    return shutil.which("git") is not None


def git_ref_exists(ref: str) -> bool:
    if not ref or not git_available():
        return False
    result = run(["git", "rev-parse", "--verify", "--quiet", ref], timeout=15)
    return result.returncode == 0


def rail_runtime_tracked_on_branch(branch: str) -> bool:
    if not branch or not git_available():
        return False
    result = run(["git", "cat-file", "-e", f"{branch}:.rail/rail.py"], timeout=15)
    return result.returncode == 0


def current_branch() -> str:
    if not git_available():
        return "unknown"
    result = run(["git", "branch", "--show-current"], timeout=15)
    return result.stdout.strip() or "unknown"


def git_status_short() -> str:
    if not git_available():
        return "git unavailable"
    return run(["git", "status", "--short"], timeout=30).stdout.strip()


def git_state_path(name: str) -> Path | None:
    if not git_available():
        return None
    result = run(["git", "rev-parse", "--git-path", name], timeout=15)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = ROOT / path
    return path


def git_path_exists(name: str) -> bool:
    path = git_state_path(name)
    return bool(path and path.exists())


def unmerged_files() -> list[str]:
    if not git_available():
        return []
    result = run(["git", "diff", "--name-only", "--diff-filter=U"], timeout=30)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def git_safety_preflight() -> dict[str, Any]:
    merge_active = git_path_exists("MERGE_HEAD")
    rebase_active = git_path_exists("rebase-merge") or git_path_exists("rebase-apply")
    cherry_pick_active = git_path_exists("CHERRY_PICK_HEAD")
    revert_active = git_path_exists("REVERT_HEAD")
    conflicts = unmerged_files()
    return {
        "current_branch": current_branch(),
        "default_branch": default_branch(),
        "unmerged_files": conflicts,
        "has_unresolved_conflicts": bool(conflicts),
        "merge_active": merge_active,
        "rebase_active": rebase_active,
        "cherry_pick_active": cherry_pick_active,
        "revert_active": revert_active,
        "has_active_git_operation": merge_active or rebase_active or cherry_pick_active or revert_active,
    }


def print_git_state_blocked(action: str, state: dict[str, Any]) -> None:
    print(f"Error: rail {action} is blocked because Git has unresolved state.")
    if state.get("unmerged_files"):
        print("Unresolved files:")
        for item in state["unmerged_files"]:
            print(f"- {item}")
    active = []
    if state.get("merge_active"):
        active.append("merge")
    if state.get("rebase_active"):
        active.append("rebase")
    if state.get("cherry_pick_active"):
        active.append("cherry-pick")
    if state.get("revert_active"):
        active.append("revert")
    if active:
        print("Active Git operation: " + ", ".join(active))
    print("Run: git status --short")
    print("Resolve conflicts and commit the merge, or abort it before continuing.")
    print("If this is a merge you do not want to finish, run: git merge --abort")


def git_state_blocks_new_work(state: dict[str, Any]) -> bool:
    return bool(state.get("has_unresolved_conflicts") or state.get("has_active_git_operation"))


def print_default_branch_rail_tracking_warning(default_branch_name: str, current: str) -> None:
    print("\n.rail tracking warning:")
    print(".rail/ is not tracked on the default branch.")
    print("Ship/sync may remove local Rail runtime files.")
    print("This matters because checkout/sync back to the default branch can remove the repo-local Rail runtime files.")
    if current != default_branch_name:
        print(f"You are currently on `{current}`, not the default branch `{default_branch_name}`.")
    print("\nIf this branch is the desired project state:")
    print("git add -A")
    print('git commit -m "chore: initialize ai rail workflow"')
    print(f"git push -u origin {current}")
    print("\nIf Rail should be initialized on the default branch:")
    print(f"git switch {default_branch_name}")
    print("git pull")
    print("rail init --clean-default")


def is_dirty() -> bool:
    status = git_status_short()
    return bool(status and status != "git unavailable")


def dirty_count() -> int:
    status = git_status_short()
    if not status or status == "git unavailable":
        return 0
    return len(status.splitlines())


DANGEROUS_COMMIT_PATTERNS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
]

GENERATED_COMMIT_DIRS = {
    ".rail/brain",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".turbo",
    ".pytest_cache",
    "__pycache__",
}

LEGACY_WORKFLOW_MARKERS = [
    ".orchestra",
    "orchestrator.py",
    "tasks",
    "AGENTS.md",
    "ROADMAP.md",
    "WORKFLOW.md",
]


def git_status_entries() -> list[tuple[str, str]]:
    """Return porcelain status/path pairs using NUL separators for robust paths."""
    if not git_available():
        raise RuntimeError("git is required to inspect changed files.")
    result = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], timeout=30)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git status failed."
        raise RuntimeError(f"Could not inspect changed files: {message}")

    entries: list[tuple[str, str]] = []
    parts = result.stdout.split("\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        if not entry:
            i += 1
            continue
        status = entry[:2]
        path = entry[3:] if len(entry) > 3 else ""
        if path:
            entries.append((status, path))
        if "R" in status or "C" in status:
            i += 1
            if i < len(parts) and parts[i]:
                entries.append((status, parts[i]))
        i += 1
    return entries


def changed_paths() -> list[str]:
    """Return changed paths from git status, including untracked files."""
    return sorted(set(path for _status, path in git_status_entries() if path))


def untracked_paths() -> list[str]:
    return sorted(set(path for status, path in git_status_entries() if status == "??" and path))


def normalize_git_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def path_matches_marker(path: str, marker: str) -> bool:
    normalized = normalize_git_path(path)
    marker = marker.strip("/")
    return normalized == marker or normalized.startswith(marker + "/")


def is_rail_path(path: str) -> bool:
    return path_matches_marker(path, ".rail")


def is_legacy_workflow_path(path: str) -> bool:
    return any(path_matches_marker(path, marker) for marker in LEGACY_WORKFLOW_MARKERS)


def detected_legacy_workflow_artifacts(paths: list[str] | None = None) -> list[str]:
    candidates = paths or []
    found: set[str] = set()
    for marker in LEGACY_WORKFLOW_MARKERS:
        if (ROOT / marker).exists() or any(path_matches_marker(path, marker) for path in candidates):
            found.add(marker)
    return sorted(found)


def grouped_dirty_status(limit: int = 20) -> dict[str, list[str]]:
    groups = {
        "Rail files": [],
        "App/source files": [],
        "Deleted legacy workflow files": [],
        "Untracked legacy workflow files": [],
        "Other untracked files": [],
    }
    if not git_available():
        return groups
    for status, path in git_status_entries():
        if not path:
            continue
        item = f"{status} {path}"
        if is_rail_path(path):
            groups["Rail files"].append(item)
        elif status == "??" and is_legacy_workflow_path(path):
            groups["Untracked legacy workflow files"].append(item)
        elif "D" in status and is_legacy_workflow_path(path):
            groups["Deleted legacy workflow files"].append(item)
        elif status == "??":
            groups["Other untracked files"].append(item)
        else:
            groups["App/source files"].append(item)
    return {name: sorted(items) for name, items in groups.items()}


def print_grouped_dirty_status(limit: int = 20) -> None:
    if not git_available():
        print("Dirty files: git unavailable")
        return
    groups = grouped_dirty_status(limit=limit)
    total = sum(len(items) for items in groups.values())
    print(f"\nDirty files: {total}")
    if total == 0:
        return
    for name, items in groups.items():
        if not items:
            continue
        print(f"\n{name}: {len(items)}")
        for item in items[:limit]:
            print(f"  {item}")
        hidden = len(items) - limit
        if hidden > 0:
            print(f"  ... {hidden} more hidden")
    legacy = detected_legacy_workflow_artifacts([item[3:] for items in groups.values() for item in items])
    if legacy:
        print("\nLegacy workflow artifacts detected. If you are migrating to AI Rail, commit the deletion and `.rail/` addition together as a deliberate workflow migration.")


def is_dangerous_commit_path(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/").strip("/")
    name = Path(normalized).name
    parts = set(Path(normalized).parts)

    if normalized.startswith(".rail/state/"):
        return True
    if normalized.startswith(".rail/brain/"):
        return True

    if parts & GENERATED_COMMIT_DIRS:
        return True

    for pattern in DANGEROUS_COMMIT_PATTERNS:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def dangerous_changed_paths() -> list[str]:
    return [path for path in changed_paths() if is_dangerous_commit_path(path)]


def latest_change_mtime(paths: list[str]) -> float | None:
    mtimes: list[float] = []
    for rel in paths:
        path = ROOT / rel
        if path.exists():
            try:
                mtimes.append(path.stat().st_mtime)
            except OSError:
                continue
    return max(mtimes) if mtimes else None


def artifact_is_fresh(path: Path, paths: list[str]) -> bool:
    if not path.exists():
        return False
    latest = latest_change_mtime(paths)
    if latest is None:
        return True
    return path.stat().st_mtime + 1 >= latest


def is_probably_text_file(path: Path, max_bytes: int = 20000) -> bool:
    try:
        if path.stat().st_size > max_bytes:
            return False
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\x00" not in sample


def untracked_text_contents(max_file_chars: int = 12000, max_total_chars: int = 50000) -> str:
    """Include small untracked text files in review packs so new files are auditable."""
    if not git_available():
        return "git unavailable"

    sections: list[str] = []
    total = 0
    for rel in untracked_paths():
        path = ROOT / rel
        if not path.is_file():
            continue
        if not is_probably_text_file(path):
            sections.append(f"### {rel}\n\n[skipped: binary or larger than 20KB]\n")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_file_chars:
            text = text[:max_file_chars] + "\n[truncated]\n"
        block = f"### {rel}\n\n```text\n{text}\n```\n"
        if total + len(block) > max_total_chars:
            sections.append("[untracked file content truncated]\n")
            break
        sections.append(block)
        total += len(block)

    return "\n".join(sections).strip() or "No untracked text file contents."


def git_has_upstream() -> bool:
    if not git_available():
        return False
    result = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], timeout=15)
    return result.returncode == 0 and bool(result.stdout.strip())


def safety_preflight_before_commit(args: argparse.Namespace) -> int:
    """Refuse unsafe commits unless the user explicitly forces them."""
    paths = changed_paths()

    dangerous = dangerous_changed_paths()
    if dangerous and not args.force:
        print("Error: refusing to commit dangerous/generated paths:")
        for item in dangerous:
            print(f"- {item}")
        print("\nRestore/remove them, add them to .gitignore, or use `rail commit ... --force` only if intentional.")
        return 1

    if args.force:
        print("[rail] Warning: --force skips commit safety checks.")
        if dangerous:
            print("[rail] Warning: dangerous paths are present in the working tree:")
            for item in dangerous:
                print(f"[rail]   - {item}")
            print("[rail] Warning: --force does not protect against committing these. Review before proceeding.")
        return 0

    if not LAST_REVIEW_PATH.exists():
        print("Error: no fresh review pack found. Run: rail review  # or rail verify")
        return 1
    if not artifact_is_fresh(LAST_REVIEW_PATH, paths):
        print("Error: review pack is older than current file changes. Run: rail review  # or rail verify")
        return 1

    check_state = checks_result()
    if check_state != "passed":
        if args.allow_missing_checks and check_state in {"missing", "unknown"}:
            print(f"[rail] Warning: checks are {check_state}; continuing because --allow-missing-checks was used.")
        else:
            print(f"Error: last checks are {check_state.upper()}. Refusing to commit.")
            print("Run: rail checks  # or rail verify")
            print("Use --allow-missing-checks only when the project truly has no checks.")
            return 1
    elif not artifact_is_fresh(LAST_CHECKS_PATH, paths):
        if args.allow_stale:
            print("[rail] Warning: checks are older than current file changes; continuing because --allow-stale was used.")
        else:
            print("Error: checks are older than current file changes. Run: rail checks  # or rail verify")
            return 1

    return 0


def slugify(text: str, max_len: int = 54) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "task"


def detect_repo() -> str | None:
    cfg = load_config()
    repo = cfg.get("repository")
    if repo and repo != "CHANGE_ME":
        return repo

    if gh_available():
        result = run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

    if git_available():
        result = run(["git", "remote", "get-url", "origin"], timeout=15)
        url = result.stdout.strip()
        if url:
            match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
            if match:
                return match.group(1)
    return None


def detect_repo_from_git_remote() -> str | None:
    if not git_available():
        return None
    result = run(["git", "remote", "get-url", "origin"], timeout=15)
    url = result.stdout.strip()
    if not url:
        return None
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if match:
        return match.group(1)
    return url


def planning_identity() -> tuple[str, str]:
    cfg = load_config()
    project_name = str(cfg.get("project_name") or ROOT.name)
    repository = cfg.get("repository")
    if repository in {None, "", "CHANGE_ME"}:
        repository = detect_repo_from_git_remote() or "not configured"
    return project_name, str(repository)


def unconfigured_repository_prompt_warning(repository: str) -> str:
    if repository != "not configured":
        return ""
    return """

STOP: Repository is not configured.
- Do not create or update GitHub issues yet.
- First configure `.rail/config.json` repository or run `rail init --refresh-config`."""


def fetch_github_issues(repo: str, state_value: str, limit: int = 100) -> list[dict[str, Any]]:
    gh = shutil.which("gh") or "gh"
    result = run([
        gh, "issue", "list",
        "--repo", repo,
        "--state", state_value,
        "--limit", str(limit),
        "--json", "number,title,body,updatedAt,state,labels",
    ], timeout=45)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "GitHub issue list failed.")
    return json.loads(result.stdout or "[]")


def expected_roadmap_title(project_name: str) -> str:
    return f"Roadmap: {project_name} functional MVP"


def issue_label_names(issue: dict[str, Any]) -> set[str]:
    labels = issue.get("labels") or []
    names: set[str] = set()
    for label in labels:
        if isinstance(label, str):
            names.add(label)
        elif isinstance(label, dict) and label.get("name"):
            names.add(str(label["name"]))
    return names


def is_roadmap_mirror_issue(issue: dict[str, Any]) -> bool:
    title = str(issue.get("title", "")).strip().lower()
    return title.startswith("roadmap:") or ROADMAP_LABEL in issue_label_names(issue)


def implementation_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in issues if not is_roadmap_mirror_issue(item)]


def roadmap_issue_from_open_issues(open_issues: list[dict[str, Any]], expected_project_name: str | None = None) -> tuple[dict[str, Any] | None, bool]:
    roadmap = [item for item in open_issues if is_roadmap_mirror_issue(item)]
    if not roadmap:
        return None, False
    if expected_project_name:
        expected_title = expected_roadmap_title(expected_project_name)
        exact = [item for item in roadmap if str(item.get("title", "")).strip() == expected_title]
        if len(exact) == 1:
            return exact[0], False
        if len(exact) > 1:
            raise RuntimeError(f"multiple open roadmap issues match `{expected_title}`. Close or rename old roadmap issues and rerun `rail import`.")
        if len(roadmap) > 1:
            raise RuntimeError(f"multiple open roadmap issues found and none matches `{expected_title}`. Close or rename old roadmap issues and rerun `rail import`.")
    roadmap = sorted(roadmap, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return roadmap[0], len(roadmap) > 1


def extract_remote_memory(body: str) -> str | None:
    if REMOTE_MEMORY_START not in body or REMOTE_MEMORY_END not in body:
        return None
    return body.split(REMOTE_MEMORY_START, 1)[1].split(REMOTE_MEMORY_END, 1)[0].strip()


def extract_strict_roadmap_blocks(text: str) -> list[str]:
    pattern = re.escape(RAIL_ROADMAP_START) + r".*?" + re.escape(RAIL_ROADMAP_END)
    return re.findall(pattern, text, flags=re.DOTALL)


def render_managed_roadmap_from_issue(roadmap: dict[str, Any], open_issues: list[dict[str, Any]], closed_issues: list[dict[str, Any]]) -> str:
    body = str(roadmap.get("body") or "").strip() or "_No roadmap body captured._"
    open_impl = implementation_issues(open_issues)
    open_lines = "\n".join(f"- [ ] #{item.get('number')} {item.get('title')}" for item in open_impl) or "- None"
    closed_lines = "\n".join(f"- [x] #{item.get('number')} {item.get('title')}" for item in closed_issues) or "- None"
    next_issue = open_impl[0] if open_impl else None
    next_line = f"#{next_issue.get('number')} {next_issue.get('title')}" if next_issue else "None"
    return f"""## Roadmap

Imported from GitHub roadmap issue #{roadmap.get('number')}: {roadmap.get('title')}

## Roadmap issue body

{body}

## Active execution queue

{open_lines}

## Completed work

{closed_lines}

## Next recommended issue

{next_line}
"""


def project_memory_template(managed: str) -> str:
    return f"""# Project Memory

This file is the local AI Rail project memory and roadmap brain.

GitHub Issues are the active task execution queue.
The GitHub roadmap issue is the remote roadmap mirror.
AI/planning agents create and update the roadmap.
AI Rail imports roadmap memory and tracks completed issue state.

{LOCAL_ROADMAP_START}

{managed.strip()}

{LOCAL_ROADMAP_END}

## Roadmap maintenance rules

- Keep the full roadmap here.
- Keep only the active execution slice as GitHub implementation issues.
- Do not create `.rail/ROADMAP.md`.
- Do not use GitHub Issues for the entire 100-task roadmap.
- Use `rail import` after `rail plan --copy` or `rail phase --copy`.
- Use `rail s` to ship/close one issue and mark it completed locally.
"""


def is_placeholder_project_memory(text: str) -> bool:
    if "CHANGE_ME" not in text:
        return False
    required = ["Product notes", "Stack", "Non-negotiables", "Roadmap maintenance rules"]
    if not all(item in text for item in required):
        return False
    stripped = re.sub(r"<!-- AI RAIL MANAGED ROADMAP START -->.*?<!-- AI RAIL MANAGED ROADMAP END -->", "", text, flags=re.DOTALL)
    defaults = [
        "# Project Memory",
        "This file is the local AI Rail project memory and roadmap brain.",
        "GitHub Issues are the active task execution queue.",
        "The GitHub roadmap issue is the remote roadmap mirror.",
        "AI/planning agents create and update the roadmap.",
        "AI Rail imports roadmap memory and tracks completed issue state.",
        "## Product notes",
        "CHANGE_ME: What does this project do?",
        "## Stack",
        "CHANGE_ME: Main technologies, framework, runtime, database, deployment target.",
        "## Non-negotiables",
        "CHANGE_ME: Constraints, architecture rules, safety rules, and things AI must not break.",
        "## Roadmap maintenance rules",
        "- Keep the full roadmap here.",
        "- Keep only the active execution slice as GitHub implementation issues.",
        "- Do not create `.rail/ROADMAP.md`.",
        "- Do not use GitHub Issues for the entire 100-task roadmap.",
        "- Use `rail import` after `rail plan --copy` or `rail phase --copy`.",
        "- Use `rail s` to ship/close one issue and mark it completed locally.",
    ]
    remainder = stripped
    for item in defaults:
        remainder = remainder.replace(item, "")
    return not remainder.strip()


def backup_project_memory_before_replacement() -> None:
    if not PROJECT_PATH.exists() or not PROJECT_PATH.is_file():
        return
    backup = unique_backup_path(PROJECT_PATH)
    shutil.copy2(PROJECT_PATH, backup)
    print(f"[rail] Backed up .rail/PROJECT.md to .rail/{backup.name}")


def update_local_project_memory(managed: str) -> None:
    new_block = f"{LOCAL_ROADMAP_START}\n\n{managed.strip()}\n\n{LOCAL_ROADMAP_END}"
    if not PROJECT_PATH.exists():
        write_text(PROJECT_PATH, project_memory_template(managed))
        return
    existing = read_text(PROJECT_PATH)
    if is_placeholder_project_memory(existing) or ("CHANGE_ME:" in existing and "## Roadmap maintenance rules" in existing and RAIL_ROADMAP_START in existing):
        backup_project_memory_before_replacement()
        write_text(PROJECT_PATH, project_memory_template(managed))
        return
    if LOCAL_ROADMAP_START in existing and LOCAL_ROADMAP_END in existing:
        before = existing.split(LOCAL_ROADMAP_START, 1)[0].rstrip()
        after = existing.split(LOCAL_ROADMAP_END, 1)[1].lstrip()
        write_text(PROJECT_PATH, f"{before}\n\n{new_block}\n\n{after}")
        return
    write_text(PROJECT_PATH, existing.rstrip() + "\n\n" + new_block + "\n")


def default_branch() -> str:
    cfg = load_config()
    if cfg.get("default_branch"):
        return str(cfg["default_branch"])
    if gh_available():
        repo = detect_repo()
        repo_args = ["--repo", repo] if repo else []
        result = run(["gh", "repo", "view", *repo_args, "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"], timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return "main"


def gh_repo_args() -> list[str]:
    repo = detect_repo()
    return ["--repo", repo] if repo else []


def fetch_issue(issue_ref: str) -> dict[str, Any]:
    """Fetch a GitHub issue.

    issue_ref may be:
    - number
    - latest: most recently updated open issue; lastest is accepted as a backward-compatible typo alias
    - next: open issue labeled status:next, otherwise lowest-numbered open issue
    """
    if not gh_available():
        raise RuntimeError("GitHub CLI `gh` is not installed or not available in PATH.")

    repo_args = gh_repo_args()
    ref = issue_ref.lower()

    if ref in {"latest", "lastest"}:
        result = run(
            [
                "gh", "issue", "list",
                *repo_args,
                "--state", "open",
                "--limit", "1",
                "--sort", "updated",
                "--json", "number,title,body,url,state,labels,updatedAt",
            ],
            timeout=45,
            check=True,
        )
        issues = json.loads(result.stdout or "[]")
        issues = implementation_issues(issues)
        if not issues:
            raise RuntimeError("No open GitHub issues found for `latest`.")
        issue = issues[0]
    elif ref == "next":
        result = run(
            [
                "gh", "issue", "list",
                *repo_args,
                "--state", "open",
                "--label", "status:next",
                "--limit", "1",
                "--json", "number,title,body,url,state,labels,updatedAt",
            ],
            timeout=45,
        )
        issues = json.loads(result.stdout or "[]") if result.returncode == 0 else []
        issues = implementation_issues(issues)
        if not issues:
            result = run(
                [
                    "gh", "issue", "list",
                    *repo_args,
                    "--state", "open",
                    "--limit", "100",
                    "--json", "number,title,body,url,state,labels,updatedAt",
                ],
                timeout=45,
                check=True,
            )
            issues = json.loads(result.stdout or "[]")
            issues = implementation_issues(issues)
            issues = sorted(issues, key=lambda item: int(item["number"]))
        if not issues:
            raise RuntimeError("No open implementation issues found.")
        issue = issues[0]
    else:
        issue_number = int(issue_ref)
        result = run(
            [
                "gh", "issue", "view", str(issue_number),
                *repo_args,
                "--json", "number,title,body,url,state,labels,updatedAt",
            ],
            timeout=45,
            check=True,
        )
        issue = json.loads(result.stdout or "{}")

    issue["body"] = issue.get("body") or ""
    return issue


def create_branch_for_issue(issue: dict[str, Any], reset_existing: bool = False) -> str:
    if not git_available():
        raise RuntimeError("git is not installed or not available in PATH.")

    branch = f"issue-{issue['number']}-{slugify(issue.get('title', 'task'))}"
    existing = run(["git", "rev-parse", "--verify", branch], timeout=15)

    if existing.returncode == 0:
        if reset_existing:
            run(["git", "checkout", "-B", branch], timeout=30, check=True)
        else:
            run(["git", "checkout", branch], timeout=30, check=True)
        return branch

    run(["git", "checkout", "-b", branch], timeout=30, check=True)
    return branch


def warn_placeholders() -> list[str]:
    warnings: list[str] = []
    cfg = load_config()

    if cfg.get("project_name") in {None, "", "CHANGE_ME"}:
        warnings.append("config.json: project_name is still CHANGE_ME.")

    if cfg.get("repository") in {None, "", "CHANGE_ME"}:
        warnings.append("config.json: repository is not set. gh/git remote detection will be used.")

    for path in (PROJECT_PATH, AGENTS_PATH):
        text = read_text(path)
        if "CHANGE_ME" in text:
            warnings.append(f"{path.relative_to(ROOT)} contains CHANGE_ME placeholders.")

    return warnings


def active_issue() -> dict[str, Any] | None:
    if not ACTIVE_PATH.exists():
        return None
    return load_json(ACTIVE_PATH, None)


def require_active() -> dict[str, Any]:
    active = active_issue()
    if not active:
        raise RuntimeError("No active issue. Run: rail start ISSUE_NUMBER")
    return active


def file_age_minutes(path: Path) -> int | None:
    if not path.exists():
        return None
    age = dt.datetime.now().timestamp() - path.stat().st_mtime
    return int(age // 60)


def checks_result() -> str:
    if not LAST_CHECKS_PATH.exists():
        return "missing"

    text = read_text(LAST_CHECKS_PATH)
    codes = [int(match) for match in re.findall(r"Exit code:\s*(\d+)", text)]

    if not codes:
        return "unknown"

    return "passed" if all(code == 0 for code in codes) else "failed"


def step_position() -> str:
    active = active_issue()
    if not active:
        return "no active issue"

    has_review = LAST_REVIEW_PATH.exists()
    has_checks = LAST_CHECKS_PATH.exists()
    has_prompt = LAST_CODEX_PROMPT_PATH.exists()
    dirty = is_dirty()
    check_state = checks_result()

    if not has_prompt:
        return "started; generate Codex prompt next"
    if dirty and not has_review:
        return "files changed; run review next"
    if has_review and not has_checks:
        return "review captured; run checks next"
    if has_review and has_checks and check_state == "failed":
        return "checks failed; fix before commit"
    if has_review and has_checks and check_state == "passed":
        return "checks passed; ask ChatGPT to audit or commit"
    if has_review and has_checks:
        return "review/checks captured; verify before commit"
    return "prompt generated; run Codex or apply patch"


def extract_issue_section(body: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(body)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", body[match.end():], flags=re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(body)
    return body[match.end():end].strip()


def issue_section_items(body: str, heading: str) -> list[str]:
    section = extract_issue_section(body, heading)
    items: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^[-*]\s+", "", stripped)
        stripped = re.sub(r"^\d+\.\s+", "", stripped)
        if stripped and stripped not in {"-", "None", "N/A"}:
            items.append(stripped)
    return items


def build_codex_prompt(active: dict[str, Any]) -> str:
    issue = active.get("issue", {})
    issue_number = issue.get("number")
    title = issue.get("title")
    body = str(issue.get("body", "")).strip()
    expected_files = issue_section_items(body, "Files likely touched")
    checks = issue_section_items(body, "Acceptance checks")

    read_first = [
        ".rail/CODEX.md",
    ]
    lowered_body = body.lower()
    if "project-level context" in lowered_body or ".rail/project.md" in lowered_body:
        read_first.append(".rail/PROJECT.md")

    expected_text = "\n".join(f"- {item.strip('`')}" for item in expected_files) if expected_files else "- Not specified by the issue."

    return f"""Use this AI Rail task prompt. Do not invent a separate task.

Task:
GitHub issue #{issue_number} - {title}

The full issue body is included below. Do not fetch the GitHub issue unless local issue context is missing or contradictory.

Read first:
{chr(10).join(f"- {item}" for item in read_first)}

Then inspect only the minimum project files needed to implement this issue.

Expected files:
{expected_text}

Inspect only the minimum files needed for this issue.
Edit only files directly required by this issue.
If the fix appears to require broad unrelated changes, stop and explain before editing.

Hard scope:
- Implement only this issue.
- No unrelated refactor.
- No architecture changes unless the issue explicitly asks.
- No commits.
- No issue close.
- No rail done.

Checks:
- Do not run tests/checks by default.
- Do not run full suites like npm test, npm run build, or broad integration tests.
- Only run a tiny focused check if there is truly no safe way to finish the task without it.
- If you skip checks, say exactly: "Checks not run; human will run rail v."

Return:
- files changed
- behavior changed
- checks run, or "Checks not run; human will run rail v."
- remaining risks

Issue body:
```markdown
{body}
```
"""


def truncated_git_diff(max_lines: int = 220) -> str:
    if not git_available():
        return "git unavailable"
    result = run(["git", "diff", "--", "."], timeout=30)
    diff = result.stdout.strip()
    if not diff:
        return "No diff."
    lines = diff.splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + f"\n\n[diff truncated at {max_lines} lines]"
    return diff


def build_review_prompt(active: dict[str, Any]) -> str:
    issue = active.get("issue", {})
    review = read_text(LAST_REVIEW_PATH, "No local review captured yet.")
    checks = read_text(LAST_CHECKS_PATH, "No checks captured yet.")
    diff = truncated_git_diff(220)

    return f"""Audit this task against the GitHub issue.

Issue #{issue.get("number")}: {issue.get("title")}
URL: {issue.get("url")}

Issue body:
```markdown
{issue.get("body", "").strip()}
```

Local review:
```text
{review.strip()}
```

Actual diff, truncated:
```diff
{diff}
```

Checks:
```text
{checks.strip()}
```

Tell me:
- Did the implementation drift from the issue?
- Are the changed files within scope?
- Were only focused or explicitly requested checks run?
- Is it safe to run `rail ship`?
- What exact next terminal commands should I run?
- What commit message should I use?
"""


def copy_to_clipboard(text: str) -> bool:
    """Best-effort clipboard copy. Returns True if copied."""
    commands: list[list[str]] = []

    if os.name == "nt" and shutil.which("clip"):
        commands.append(["clip"])
    if shutil.which("pbcopy"):
        commands.append(["pbcopy"])
    if shutil.which("xclip"):
        commands.append(["xclip", "-selection", "clipboard"])
    if shutil.which("xsel"):
        commands.append(["xsel", "--clipboard", "--input"])
    if shutil.which("wl-copy"):
        commands.append(["wl-copy"])

    for command in commands:
        try:
            subprocess.run(command, input=text, text=True, encoding="utf-8", check=True)
            return True
        except Exception:
            continue
    return False


def cmd_init(args: argparse.Namespace) -> int:
    ensure_state_dir()
    for path, content in {
        RAIL_DIR / ".gitignore": "__pycache__/\n*.pyc\nstate/*\n!state/.gitignore\n",
        STATE_DIR / ".gitignore": "*\n!.gitignore\n",
    }.items():
        if not path.exists():
            write_text(path, content)
    print("AI Rail initialized.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"AI Rail doctor v{VERSION}")
    print(f"Root: {ROOT}")
    print(f"Git available: {git_available()}")
    print(f"GitHub CLI available: {gh_available()}")
    print(f"Detected repo: {detect_repo() or 'unknown'}")
    print(f"Default branch: {default_branch()}")
    print(f"Current branch: {current_branch()}")

    required = [CONFIG_PATH, AGENTS_PATH, PROJECT_PATH]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        print("\nMissing files:")
        for item in missing:
            print(f"- {item}")

    warnings = warn_placeholders()
    if warnings:
        print("\nWarnings:")
        for item in warnings:
            print(f"- {item}")

    active = active_issue()
    if active:
        issue = active.get("issue", {})
        print(f"\nActive issue: #{issue.get('number')} {issue.get('title')}")
    else:
        print("\nActive issue: none")

    db = default_branch()
    ref = db if git_ref_exists(db) else f"origin/{db}"
    if git_ref_exists(ref) and not rail_runtime_tracked_on_branch(ref):
        print_default_branch_rail_tracking_warning(db, current_branch())

    return 1 if missing else 0


def cmd_status(args: argparse.Namespace) -> int:
    active = active_issue()
    print(f"AI Rail status v{VERSION}")
    print(f"Repo: {detect_repo() or 'unknown'}")
    print(f"Branch: {current_branch()}")
    print(f"Default branch: {default_branch()}")
    print(f"Loop position: {step_position()}")

    if active:
        issue = active.get("issue", {})
        print(f"Active issue: #{issue.get('number')} — {issue.get('title')}")
        print(f"Issue URL: {issue.get('url')}")
        print(f"Started: {active.get('started_at')}")
    else:
        print("Active issue: none")

    print("")
    for label, path in [
        ("Codex prompt", LAST_CODEX_PROMPT_PATH),
        ("Review", LAST_REVIEW_PATH),
        ("Checks", LAST_CHECKS_PATH),
        ("Review prompt", LAST_REVIEW_PROMPT_PATH),
    ]:
        age = file_age_minutes(path)
        print(f"{label}: {'missing' if age is None else f'{age} min ago'}")

    check_state = checks_result()
    if check_state == "passed":
        print("Checks result: PASSED")
    elif check_state == "failed":
        print("Checks result: FAILED")
    else:
        print(f"Checks result: {check_state}")

    print_grouped_dirty_status()

    print("\nNext suggestion:")
    print(next_suggestion())
    return 0


def next_suggestion() -> str:
    pos = step_position()
    if pos == "no active issue":
        return "rail issue-list  # then: rail start next"
    if "generate Codex prompt" in pos:
        return "rail prompt codex"
    if "run review" in pos:
        return "rail review"
    if "run checks" in pos:
        return "rail checks"
    if "checks failed" in pos:
        return "fix the failure, then run: rail review && rail checks"
    if "checks passed" in pos:
        return "rail prompt review  # then audit/commit"
    return "rail status"


def cmd_repo(args: argparse.Namespace) -> int:
    repo = detect_repo()
    if not repo:
        print("Could not detect repository.")
        return 1
    print(repo)
    return 0


def cmd_active(args: argparse.Namespace) -> int:
    return cmd_status(args)


def cmd_resume(args: argparse.Namespace) -> int:
    return cmd_status(args)


def cmd_issue_template(args: argparse.Namespace) -> int:
    print(ISSUE_TEMPLATE.rstrip())
    return 0


def cmd_issue_list(args: argparse.Namespace) -> int:
    if not gh_available():
        print("GitHub CLI `gh` is required for issue-list.")
        return 1

    cmd = [
        "gh", "issue", "list",
        *gh_repo_args(),
        "--state", args.state,
        "--limit", str(args.limit),
    ]
    if args.label:
        for label in args.label:
            cmd += ["--label", label]
    if args.sort:
        cmd += ["--sort", args.sort]

    result = run(cmd, timeout=45)
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode or 1
    print(result.stdout.strip() or "No issues found.")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    state = git_safety_preflight()
    if state.get("has_unresolved_conflicts"):
        print_git_state_blocked("start", state)
        print("Do not start a new task while .rail/PROJECT.md or code is conflicted.")
        return 1

    existing_active = active_issue()
    if existing_active and not args.force:
        old = existing_active.get("issue", {})
        print(f"Error: issue #{old.get('number')} is already active: {old.get('title')}")
        print(f"Starting {args.issue_ref} would replace it.")
        print("Run `rail clear-active` first for a local reset, or use `rail start ... --force` if you really want to replace it.")
        return 1

    issue = fetch_issue(args.issue_ref)
    branch = current_branch()

    if not args.no_branch:
        branch = create_branch_for_issue(issue, reset_existing=args.reset_branch)

    active = {
        "started_at": utc_now(),
        "mode": "issue",
        "branch": branch,
        "issue": issue,
    }
    save_json(ACTIVE_PATH, active)

    # Clear stale loop state for new issue.
    for path in (LAST_REVIEW_PATH, LAST_CHECKS_PATH, LAST_CODEX_PROMPT_PATH, LAST_REVIEW_PROMPT_PATH):
        path.unlink(missing_ok=True)

    for warning in warn_placeholders():
        print(f"Warning: {warning}")

    print(f"Started issue #{issue['number']}: {issue.get('title')}")
    print(f"Branch: {branch}")
    print("\nNext:")
    print("rail prompt codex")
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    active = require_active()
    if args.kind == "codex":
        prompt = build_codex_prompt(active)
        write_text(LAST_CODEX_PROMPT_PATH, prompt)
    elif args.kind == "review":
        prompt = build_review_prompt(active)
        write_text(LAST_REVIEW_PROMPT_PATH, prompt)
    else:
        raise RuntimeError(f"Unknown prompt kind: {args.kind}")

    print(prompt)

    if args.copy:
        if copy_to_clipboard(prompt):
            print("\n[Copied prompt to clipboard]")
        else:
            print("\n[Clipboard copy requested, but no supported clipboard command was found]")
    return 0


def render_plan_prompt() -> str:
    project_name, repository = planning_identity()
    return f"""You are a GitHub-connected planning agent for this repository.

Project: {project_name}
Repository: {repository}{unconfigured_repository_prompt_warning(repository)}

Audit the repo enough to understand:
- project purpose
- tech stack
- current features
- missing backend/backbone/configuration
- fake UI or unimplemented controls
- risky/broken areas
- what should be done first

Create or update one GitHub roadmap issue as the remote roadmap mirror, titled:
Roadmap: {project_name} functional MVP

Roadmap mirror issue rules:
- Create/update exactly one roadmap mirror issue.
- Label it `ai-rail-roadmap`.
- Keep it open permanently as the remote `.rail/PROJECT.md` mirror.
- Never include the roadmap mirror issue itself as a task inside the strict roadmap block.
- Close only normal implementation task issues after work ships; do not close the roadmap mirror issue.

Put the full roadmap/project memory inside the roadmap issue body. Include this exact managed block:

{REMOTE_MEMORY_START}
...
{REMOTE_MEMORY_END}

The managed block should be complete enough to become the useful body of local `.rail/PROJECT.md` after `rail import`.
Do not include `CHANGE_ME`.
Do not duplicate default placeholder sections.
If updating an existing roadmap issue, replace the old managed block instead of appending another one.
If old roadmap content exists outside the managed block, update it only if needed; do not create duplicate roadmap sections.

Inside the managed block, include exactly one strict Rail-readable roadmap block:

<!-- AI RAIL ROADMAP START -->

## Phase P1 - Foundation / truth alignment
Status: active

### Goal
Plain text phase goal.

### Completion criteria
- Plain text criterion.

### Tasks
- [ ] P1-T01 | #123 | Existing active issue title
- [ ] P1-T02 | TBD | Future task title

<!-- AI RAIL ROADMAP END -->

Strict roadmap rules:
- Every task line must use exactly one of these forms:
  - [ ] TASK_ID | ISSUE | TITLE
  - [x] TASK_ID | ISSUE | TITLE
- `TASK_ID` must look like `P1-T01`, `P2-T03`, and be unique.
- `ISSUE` must be `#N` for GitHub issues that exist or `TBD` for future tasks not yet created.
- Legacy issue-first task lines are still accepted by Rail, but new roadmap text should use task-id-first.
- Phase `Status:` must be one of `planned`, `active`, `complete`, or `blocked`.
- Use checkboxes for every task.
- Do not use numbered lists for task status inside the strict block.
- Do not duplicate task status elsewhere as a second source of truth.
- Do not append duplicate roadmap blocks; replace/update the existing block.

AI RAIL PROJECT MEMORY contains human-readable project context:
- product summary
- stack
- non-negotiables
- current state
- target state
- blockers/postponed items
- completed work summary
- next recommended issue/task
- workflow notes

AI RAIL ROADMAP contains only Rail-readable phase/task state:
- phase headings
- Status
- Goal
- Completion criteria
- Tasks
- strict task lines

Do not put product summary, stack, non-negotiables, current state, target state, blockers, completed-work prose, workflow notes, or next-step prose inside AI RAIL ROADMAP.
Do not duplicate task status outside AI RAIL ROADMAP.

AI Rail treats `.rail/PROJECT.md` as the local project memory and roadmap brain, but you should update the GitHub roadmap issue first. Do not edit `.rail/PROJECT.md` remotely unless the user explicitly asks.

Structure the roadmap into phases. Example phase styles:
- Phase 1 - Foundation / cleanup / truth alignment
- Phase 2 - Core functionality
- Phase 3 - UI/backbone connection
- Phase 4 - safety/polish/release readiness

Do not force those exact phase names; choose phases that fit this repo.

Create all issues for the first active execution slice/current phase as implementation-ready GitHub Issues:
- usually 3-10 right-sized implementation issues
- do not stop after creating one issue unless the phase truly has one task or GitHub/API failure blocks more
- do not create GitHub issues for the entire long-term roadmap
- assign `#N` issue refs in the strict roadmap block for issues you create
- keep future tasks as `Pn-Txx | TBD | title`
- small enough for one focused coding-agent pass
- big enough to be meaningful
- not tiny/noisy micro-tasks
- not huge phase-sized tasks
- ordered safest/foundation-first
- each issue should produce a clear diff
- avoid vague issues like "improve UI" or "refactor app"
- prefer backbone/config/foundation fixes before polish
- if GitHub blocks long issue bodies, create shorter issue bodies but still create issue shells and insert `#N` refs
- if not all active-slice issues are created, list which tasks remain `TBD` and why

Each implementation issue must include this body template:

## Goal

## Current problem

## Scope

## Out of scope

## Files likely touched

## Acceptance checks

## AI/Codex rules

- Keep scope small.
- Touch only necessary files.
- Do not commit.
- Do not close the issue.
- Do not run broad/full test suites unless explicitly asked.
- Run only focused checks related to this issue.
- Stop and explain if this requires broader architecture changes.

Task-writing rules:
- One issue should fit one focused coding-agent session.
- Each issue should usually touch a small set of related files.
- Each issue should have enough detail that `rail n` can pass it to a coding agent without re-explaining the project.
- Do not create tiny noisy micro-tasks.
- Do not create huge phase-sized tasks.
- Do not bundle unrelated UI, backend, docs, and config changes into one issue.
- If a phase is large, split it into several scoped issues.
- If the coding agent would need to make architecture decisions, create a planning/audit issue first instead of a coding issue.

Do not:
- implement code
- make commits
- open PRs
- create GitHub issues for the entire future roadmap
- create vague or huge issues

After I create/update the roadmap issue and active execution issues, run `rail import` locally.
AI Rail will import the roadmap issue into local `.rail/PROJECT.md`.
Do not edit `.rail/PROJECT.md` remotely unless the user explicitly asks.

After import, the human will run:

rail n
# paste generated prompt into coding agent

rail v
# paste review prompt into AI reviewer

rail s "type(scope): message"

Implementation happens through the one-issue-at-a-time AI Rail loop."""


def render_phase_prompt() -> str:
    project_name, repository = planning_identity()
    return f"""You are a GitHub-connected phase-audit agent for this repository.

Project: {project_name}
Repository: {repository}{unconfigured_repository_prompt_warning(repository)}

Inspect the repo and GitHub Issues. Find the roadmap issue, usually titled like:
Roadmap: {project_name} functional MVP

Roadmap mirror issue rules:
- Create/update exactly one roadmap mirror issue.
- Label it `ai-rail-roadmap`.
- Keep it open permanently as the remote `.rail/PROJECT.md` mirror.
- Never include the roadmap mirror issue itself as a task inside the strict roadmap block.
- Close only normal implementation task issues after work ships; do not close the roadmap mirror issue.

Update the GitHub roadmap issue. Update the managed project-memory block inside the roadmap issue:

{REMOTE_MEMORY_START}
...
{REMOTE_MEMORY_END}

Replace/update the existing managed block. Do not append duplicate managed blocks.
Do not leave stale phase/task sections.
Do not include `CHANGE_ME`.
Inside it, preserve and update exactly one strict `<!-- AI RAIL ROADMAP START -->` / `<!-- AI RAIL ROADMAP END -->` block.
Every task line in that block must stay exactly one of these forms:
- [ ] TASK_ID | ISSUE | TITLE
- [x] TASK_ID | ISSUE | TITLE
Use `#N` for existing GitHub issues and `TBD` for future tasks not yet created.
Legacy issue-first task lines are still accepted by Rail, but new roadmap text should use task-id-first.
Use phase statuses only from: planned, active, complete, blocked.
Do not use numbered lists for task status.
Do not invent alternate task structures.

AI RAIL PROJECT MEMORY contains human-readable project context: product summary, stack, non-negotiables, current state, target state, blockers/postponed items, completed work summary, next recommended issue/task, and workflow notes.
AI RAIL ROADMAP contains only Rail-readable phase/task state: phase headings, Status, Goal, Completion criteria, Tasks, and strict task lines.
Do not put product summary, stack, non-negotiables, current state, target state, blockers, completed-work prose, workflow notes, or next-step prose inside AI RAIL ROADMAP.
Do not duplicate task status outside AI RAIL ROADMAP.

AI Rail will import that roadmap issue into local `.rail/PROJECT.md`; do not edit `.rail/PROJECT.md` remotely unless explicitly asked.

Identify:
- current phase
- completed/closed issues in that phase
- open issues in that phase
- shipped work since the last phase audit

Audit whether the phase is really complete. Check for:
- whether completed issues really satisfy the phase completion criteria
- scope drift
- incomplete tasks
- broken assumptions
- missing tests/checks
- docs mismatch
- fake UI still not backed
- risky shortcuts
- roadmap mismatch

If the phase is complete:
- mark completed task lines as `[x]` in the strict roadmap block
- update phase `Status:` lines in the strict roadmap block
- update completed work, current phase, next recommended issue, and blockers/postponed work in the roadmap issue memory block
- mark or recommend the phase as complete in the GitHub roadmap issue
- recommend or create all issues for the next active execution slice/current phase
- usually create 3-10 right-sized implementation issues
- do not stop after creating one issue unless the slice truly has one task or GitHub/API failure blocks more
- keep new issues right-sized for coding agents

If the phase is not complete:
- list remaining blockers
- create or update only scoped blocker issues
- replace `TBD` with issue numbers when you create all issues for the next active execution slice/current phase
- add future tasks only as `- [ ] Pn-Txx | TBD | title`
- do not start the next phase yet
- if GitHub blocks long issue bodies, create shorter issue bodies but still create issue shells and insert `#N` refs
- if not all active-slice issues are created, list which tasks remain `TBD` and why

Review upcoming phases and decide whether the roadmap is still correct. If it is off-track, update upcoming phases in the GitHub roadmap issue, then clearly tell the user what changed and why.

Right-sized issue rules:
- one focused coding session
- clear diff
- not a micro-task
- not a giant phase-sized task
- no unrelated bundles
- enough detail for `rail next --copy`

Do not:
- implement code
- commit
- open PRs
- close roadmap phases unless the audit supports it
- silently create unrelated tasks
- create issues for the entire future roadmap
- edit `.rail/PROJECT.md` remotely unless explicitly asked

Implementation still happens one issue at a time through:

rail n -> coding agent -> rail v -> reviewer -> rail s

After I update the roadmap issue and active execution issues, run `rail import` locally.
AI Rail will import the updated roadmap issue into local `.rail/PROJECT.md`.

Return:
- phase audit verdict
- completed issue list
- remaining blockers
- roadmap updates made or recommended
- next phase recommendation
- next issue to run with AI Rail"""


def cmd_plan(args: argparse.Namespace) -> int:
    prompt = render_plan_prompt()
    print(prompt)
    if args.copy:
        if copy_to_clipboard(prompt):
            print("\n[Copied planning prompt to clipboard]")
        else:
            print("\n[Clipboard copy requested, but no supported clipboard command was found]")
    return 0


def cmd_phase(args: argparse.Namespace) -> int:
    prompt = render_phase_prompt()
    print(prompt)
    if args.copy:
        if copy_to_clipboard(prompt):
            print("\n[Copied phase-audit prompt to clipboard]")
        else:
            print("\n[Clipboard copy requested, but no supported clipboard command was found]")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    state = git_safety_preflight()
    if git_state_blocks_new_work(state):
        print_git_state_blocked("import", state)
        print("Resolve or abort the merge before importing.")
        return 1

    if not RAIL_DIR.exists():
        print("No .rail folder found. Run: rail init", file=sys.stderr)
        return 1
    if not gh_available():
        print("GitHub CLI `gh` is required for rail import.", file=sys.stderr)
        return 1
    repo = detect_repo()
    if repo in {None, "", "CHANGE_ME"}:
        print("Could not detect GitHub repository. Set .rail/config.json repository or git remote origin.", file=sys.stderr)
        return 1
    try:
        open_issues = fetch_github_issues(str(repo), "open")
        project_name = str(load_config().get("project_name") or ROOT.name)
        roadmap, multiple = roadmap_issue_from_open_issues(open_issues, expected_project_name=project_name)
        if not roadmap:
            closed_issues = fetch_github_issues(str(repo), "closed")
            closed_roadmaps = sorted(
                [item for item in closed_issues if is_roadmap_mirror_issue(item)],
                key=lambda item: str(item.get("updatedAt") or ""),
                reverse=True,
            )
            closed_roadmap = closed_roadmaps[0] if closed_roadmaps else None
            if closed_roadmap:
                print(f"Found closed roadmap issue #{closed_roadmap.get('number')}. Reopen it with: gh issue reopen {closed_roadmap.get('number')}", file=sys.stderr)
                return 1
            print("No open roadmap issue found. Run `rail plan --copy` first.", file=sys.stderr)
            return 1
        closed_issues = fetch_github_issues(str(repo), "closed")
        remote_block = extract_remote_memory(str(roadmap.get("body") or ""))
        if remote_block is None:
            print("Import failed: roadmap issue has no managed AI Rail project memory block.", file=sys.stderr)
            print(f"Update the GitHub roadmap issue with exactly one strict {RAIL_ROADMAP_START} / {RAIL_ROADMAP_END} block, then run rail import again.", file=sys.stderr)
            return 1
        strict_blocks = extract_strict_roadmap_blocks(remote_block)
        if len(strict_blocks) != 1:
            count = "no" if not strict_blocks else f"{len(strict_blocks)}"
            print(f"Import failed: managed roadmap memory contains {count} strict AI RAIL ROADMAP blocks; expected exactly one.", file=sys.stderr)
            print(f"Update the GitHub roadmap issue with exactly one strict {RAIL_ROADMAP_START} / {RAIL_ROADMAP_END} block, then run rail import again.", file=sys.stderr)
            return 1
        managed = remote_block
        update_local_project_memory(managed)
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1

    open_impl = implementation_issues(open_issues)
    next_issue = open_impl[0] if open_impl else None
    if multiple:
        print("[rail] Warning: multiple open roadmap issues found; imported the newest one.")
    print("Imported roadmap into .rail/PROJECT.md.")
    print(f"- Roadmap issue: #{roadmap.get('number')} {roadmap.get('title')}")
    print(f"- Open issues: {len(open_impl)}")
    print(f"- Closed issues: {len(closed_issues)}")
    print(f"- Next open issue: #{next_issue.get('number')} {next_issue.get('title')}" if next_issue else "- Next open issue: none")
    return 0


def git_output(title: str, cmd: list[str], timeout: int = 30) -> str:
    if not git_available():
        return f"## {title}\n\ngit unavailable\n"
    result = run(cmd, timeout=timeout)
    content = result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
    return f"## {title}\n\nRun: `{' '.join(cmd)}`\n\n```text\n{content or 'No output.'}\n```\n"


def cmd_review(args: argparse.Namespace) -> int:
    active = active_issue()
    issue_line = "No active issue."
    if active:
        issue = active.get("issue", {})
        issue_line = f"Active issue: #{issue.get('number')} {issue.get('title')}"

    sections = [
        "# AI Rail Review",
        "",
        f"Generated: {utc_now()}",
        issue_line,
        f"Branch: {current_branch()}",
        "",
        git_output("Git Status", ["git", "status", "--short"]),
        git_output("Git Diff Stat", ["git", "diff", "--stat"]),
        git_output("Changed Files", ["git", "diff", "--name-only"]),
        git_output("Untracked Files", ["git", "ls-files", "--others", "--exclude-standard"]),
        "## Untracked Text File Contents\n\n" + untracked_text_contents(),
    ]
    if args.full_diff:
        sections.append(git_output("Git Diff", ["git", "diff", "--", "."], timeout=30))

    output = "\n".join(sections)
    if len(output) > args.max_chars:
        output = output[: args.max_chars] + "\n\n[review truncated]\n"
    write_text(LAST_REVIEW_PATH, output)
    print(output)
    return 0


def cmd_checks(args: argparse.Namespace) -> int:
    cfg = load_config()
    commands = args.run or args.run_commands or cfg.get("checks") or []
    if not commands:
        output = f"# AI Rail Checks\n\nStarted: {utc_now()}\n\nNo checks configured.\n\nExit code: 0\n\nTotal duration: 0.0s\n\nFinished: {utc_now()}\n"
        write_text(LAST_CHECKS_PATH, output)
        print(output)
        return 0

    outputs = [f"# AI Rail Checks\n\nStarted: {utc_now()}\n"]
    exit_code = 0
    total_started = time.monotonic()
    total = len(commands)
    for index, command in enumerate(commands, start=1):
        print(f"[rail] Running check {index}/{total}: {command}", flush=True)
        started = time.monotonic()
        outputs.append(f"## `{command}`\n")
        result = subprocess.run(
            command,
            cwd=ROOT,
            shell=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=args.timeout,
        )
        duration = time.monotonic() - started
        print(f"[rail] Check completed in {duration:.1f}s: {'passed' if result.returncode == 0 else 'failed'}", flush=True)
        if result.returncode != 0 and exit_code == 0:
            exit_code = result.returncode or 1
        outputs.append(f"Exit code: {result.returncode}\n")
        outputs.append(f"Duration: {duration:.1f}s\n")
        outputs.append("### stdout\n")
        outputs.append(f"```text\n{result.stdout[-8000:]}\n```\n")
        outputs.append("### stderr\n")
        outputs.append(f"```text\n{result.stderr[-8000:]}\n```\n")

    outputs.append(f"Total duration: {time.monotonic() - total_started:.1f}s\n")
    outputs.append(f"Finished: {utc_now()}\n")
    output = "\n".join(outputs)
    write_text(LAST_CHECKS_PATH, output)
    print(output)
    return exit_code


def cmd_patch(args: argparse.Namespace) -> int:
    patch_path = Path(args.patch_file).expanduser()
    if not patch_path.is_absolute():
        patch_path = ROOT / patch_path

    if not patch_path.exists():
        print(f"Patch file not found: {patch_path}")
        return 1

    check_cmd = ["git", "apply", "--check", str(patch_path)]
    apply_cmd = ["git", "apply", str(patch_path)]

    check = run(check_cmd, timeout=60)
    if check.returncode != 0:
        print("Patch does not apply cleanly.")
        print(check.stderr.strip() or check.stdout.strip())
        return check.returncode or 1

    if args.check_only:
        print("Patch applies cleanly. No files changed because --check-only was used.")
        return 0

    result = run(apply_cmd, timeout=60)
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode or 1

    print(f"Applied patch: {patch_path}")
    print("\nNext:")
    print("rail review")
    print("rail checks")
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    if not git_available():
        print("git is required for commit.")
        return 1

    if not args.message.strip():
        print("Commit message cannot be empty.")
        return 1

    if not is_dirty():
        print("No changes to commit.")
        return 0

    preflight = safety_preflight_before_commit(args)
    if preflight != 0:
        return preflight

    paths = changed_paths()
    if not paths:
        print("No changed paths to stage.")
        return 0

    add = run(["git", "add", "-A", "--", *paths], timeout=60)
    if add.returncode != 0:
        print(add.stderr.strip() or add.stdout.strip())
        return add.returncode or 1

    commit_cmd = ["git", "commit", "-m", args.message]
    if args.amend:
        commit_cmd.insert(2, "--amend")
    commit = run(commit_cmd, timeout=120)
    if commit.returncode != 0:
        print(commit.stderr.strip() or commit.stdout.strip())
        return commit.returncode or 1
    print(commit.stdout.strip())

    if not args.no_push:
        push_cmd = ["git", "push"] if git_has_upstream() else ["git", "push", "-u", "origin", "HEAD"]
        push = run(push_cmd, timeout=120)
        if push.returncode != 0:
            print(push.stderr.strip() or push.stdout.strip())
            return push.returncode or 1
        print(push.stdout.strip() or push.stderr.strip() or "Pushed.")

    if os.environ.get("AI_RAIL_SUPPRESS_COMMIT_NEXT") != "1":
        print("\nNext:")
        print("rail issue-close --commit")
        print("rail done")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    if not git_available():
        print("git is required for sync.")
        return 1

    if is_dirty() and not args.force:
        print(f"Error: {dirty_count()} dirty files. Refusing to switch branches.")
        print("Commit/stash/restore changes first, or use `rail sync --force` if you know what you are doing.")
        return 1

    branch = args.branch or default_branch()
    ref = branch if git_ref_exists(branch) else f"origin/{branch}"
    if git_ref_exists(ref) and not rail_runtime_tracked_on_branch(ref):
        print("Warning: sync paused because .rail/ is not tracked on the target branch.")
        print("Checkout/sync could remove AI Rail runtime files.")
        print("Recommended: commit .rail/ on the target branch, then rerun rail sync.")
        return 1

    checkout = run(["git", "checkout", branch], timeout=60)
    if checkout.returncode != 0:
        print(checkout.stderr.strip() or checkout.stdout.strip())
        return checkout.returncode or 1

    pull = run(["git", "pull", "--ff-only"], timeout=120)
    if pull.returncode != 0:
        print(pull.stderr.strip() or pull.stdout.strip())
        print("Sync paused because the target branch could not fast-forward cleanly.")
        return pull.returncode or 1

    print(checkout.stdout.strip() or checkout.stderr.strip())
    print(pull.stdout.strip() or pull.stderr.strip())
    print("\nNext:")
    print("rail issue-list")
    print("rail start next")
    return 0


def cmd_issue_create(args: argparse.Namespace) -> int:
    if not gh_available():
        print("GitHub CLI `gh` is required for issue-create.")
        return 1

    body = ""
    if args.body_file:
        body = read_text(Path(args.body_file))
    elif args.body:
        body = args.body

    cmd = ["gh", "issue", "create", "--title", args.title]
    tmp_path = STATE_DIR / "issue-create-body.md"
    if body:
        write_text(tmp_path, body)
        cmd += ["--body-file", str(tmp_path)]
    for label in args.label or []:
        cmd += ["--label", label]
    for assignee in args.assignee or []:
        cmd += ["--assignee", assignee]
    cmd += gh_repo_args()

    result = run(cmd, timeout=60)
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode or 1

    url = result.stdout.strip()
    if tmp_path.exists():
        tmp_path.unlink()
    print(url)
    match = re.search(r"/issues/(\d+)", url)
    if args.start and match:
        start_args = argparse.Namespace(issue_ref=match.group(1), no_branch=args.no_branch, reset_branch=False, force=True)
        return cmd_start(start_args)
    return 0


def cmd_issue_comment(args: argparse.Namespace) -> int:
    active = require_active()
    issue_number = str(active["issue"]["number"])
    body = read_text(Path(args.body_file)) if args.body_file else args.body
    if not body:
        print("No comment body provided.")
        return 1

    cmd = ["gh", "issue", "comment", issue_number, "--body", body, *gh_repo_args()]
    result = run(cmd, timeout=45)
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode or 1
    print(result.stdout.strip() or f"Commented on issue #{issue_number}.")
    return 0


def cmd_issue_close(args: argparse.Namespace) -> int:
    active = require_active()
    issue_number = str(active["issue"]["number"])

    comment = args.comment or "Completed."
    if args.commit and git_available():
        sha = run(["git", "rev-parse", "--short", "HEAD"], timeout=15).stdout.strip()
        if sha:
            comment = f"Completed and pushed in commit {sha}."

    cmd = ["gh", "issue", "close", issue_number, "--reason", "completed", "--comment", comment, *gh_repo_args()]
    result = run(cmd, timeout=45)
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode or 1
    print(result.stdout.strip() or f"Closed issue #{issue_number}.")
    return 0


def cmd_pr_create(args: argparse.Namespace) -> int:
    active = require_active()
    issue = active["issue"]
    title = args.title or f"{issue.get('title')}"

    close_line = f"Closes #{issue.get('number')}"
    body = args.body or f"{close_line}\n\nGenerated from active AI Rail issue."
    if args.close_issue_on_merge and close_line not in body:
        body = f"{close_line}\n\n{body}"

    cmd = ["gh", "pr", "create", "--title", title, "--body", body]
    if args.draft:
        cmd.append("--draft")
    if args.base:
        cmd += ["--base", args.base]
    cmd += gh_repo_args()

    result = run(cmd, timeout=60)
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode or 1
    print(result.stdout.strip())
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    active = active_issue()
    if not active:
        print("No active issue.")
        return 0

    if is_dirty() and not args.force:
        print(f"Warning: {dirty_count()} uncommitted file(s) still exist.")
        print("Did you forget to commit?")
        print("")
        print('  rail commit "type(scope): message"')
        print("")
        print("Run `rail done --force` to clear active state anyway.")
        return 1

    issue = active.get("issue", {})
    report = [
        "# AI Rail Done",
        "",
        f"Completed: {utc_now()}",
        f"Issue: #{issue.get('number')} {issue.get('title')}",
        f"URL: {issue.get('url')}",
        f"Branch: {current_branch()}",
        "",
        "## Last Review",
        "",
        read_text(LAST_REVIEW_PATH, "No review captured.").strip(),
        "",
        "## Last Checks",
        "",
        read_text(LAST_CHECKS_PATH, "No checks captured.").strip(),
        "",
    ]
    write_text(STATE_DIR / "done.md", "\n".join(report))
    print("\n".join(report[:8]))

    if not args.keep_active:
        ACTIVE_PATH.unlink(missing_ok=True)
        print("Cleared active issue.")
    else:
        print("Kept active issue because --keep-active was used.")

    db = default_branch()
    print("\nNext:")
    print("rail sync")
    print(f"# or manually: git checkout {db} && git pull --ff-only")
    print("rail start next   # or: rail start latest / rail start ISSUE_NUMBER")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"AI Rail v{VERSION}: GitHub Issue + AI workflow rail.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize local AI Rail state files.")
    sub.add_parser("doctor", help="Check setup and placeholder configuration.")
    sub.add_parser("status", help="Show active issue and workflow position.")
    sub.add_parser("resume", help="Alias for status.")
    sub.add_parser("repo", help="Print detected GitHub repository.")
    sub.add_parser("active", help="Alias for status.")
    sub.add_parser("issue-template", help="Print the standard issue body template.")

    issue_list = sub.add_parser("issue-list", help="List GitHub issues for this repo.")
    issue_list.add_argument("--state", default="open", choices=["open", "closed", "all"])
    issue_list.add_argument("--limit", type=int, default=20)
    issue_list.add_argument("--label", action="append")
    issue_list.add_argument("--sort", choices=["created", "updated", "comments"], default=None)

    start = sub.add_parser("start", help="Start a GitHub issue by number, latest, or next. Also accepts lastest as a backward-compatible typo alias.")
    start.add_argument("issue_ref", help="Issue number, latest, or next. Also accepts lastest as a backward-compatible typo alias.")
    start.add_argument("--no-branch", action="store_true", help="Do not create/switch issue branch.")
    start.add_argument("--reset-branch", action="store_true", help="Reset existing issue branch to current HEAD.")
    start.add_argument("--force", action="store_true", help="Replace active issue if one already exists.")

    prompt = sub.add_parser("prompt", help="Print a prompt.")
    prompt.add_argument("kind", choices=["codex", "review"])
    prompt.add_argument("--copy", action="store_true", help="Also copy prompt to clipboard when possible.")

    plan = sub.add_parser("plan", help="Print a GitHub-connected AI prompt for creating a phased issue roadmap.")
    plan.add_argument("--copy", action="store_true", help="Also copy prompt to clipboard when possible.")

    phase = sub.add_parser("phase", help="Print a GitHub-connected AI prompt for auditing/updating the current roadmap phase.")
    phase.add_argument("--copy", action="store_true", help="Also copy prompt to clipboard when possible.")

    sub.add_parser("import", help="Import the GitHub roadmap issue memory into .rail/PROJECT.md.")

    review = sub.add_parser("review", help="Capture git review info.")
    review.add_argument("--max-chars", type=int, default=30000)
    review.add_argument("--full-diff", action="store_true", help="Include full git diff in last-review.md.")

    checks = sub.add_parser("checks", help="Run configured or supplied checks.")
    checks.add_argument("run_commands", nargs="*", help="Optional commands to run instead of configured checks.")
    checks.add_argument("--run", action="append", help="Check command to run instead of configured checks. May be repeated.")
    checks.add_argument("--timeout", type=int, default=180)

    patch = sub.add_parser("patch", help="Apply a .patch file locally.")
    patch.add_argument("patch_file")
    patch.add_argument("--check-only", action="store_true", help="Only verify patch applicability.")

    commit = sub.add_parser("commit", help="Safely stage changed paths, commit, and push.")
    commit.add_argument("message", help="Commit message.")
    commit.add_argument("--no-push", action="store_true", help="Commit but do not push.")
    commit.add_argument("--amend", action="store_true", help="Amend previous commit.")
    commit.add_argument("--force", action="store_true", help="Bypass review/check/danger guards. Use with care.")
    commit.add_argument("--allow-missing-checks", action="store_true", help="Allow commit when checks are missing/unknown.")
    commit.add_argument("--allow-stale", action="store_true", help="Allow commit when checks are older than changed files.")

    sync = sub.add_parser("sync", help="Checkout default branch and pull --ff-only.")
    sync.add_argument("--branch", help="Branch to sync instead of default branch.")
    sync.add_argument("--force", action="store_true", help="Allow sync with dirty worktree.")

    issue_create = sub.add_parser("issue-create", help="Create a GitHub issue using gh.")
    issue_create.add_argument("--title", required=True)
    issue_create.add_argument("--body")
    issue_create.add_argument("--body-file")
    issue_create.add_argument("--label", action="append")
    issue_create.add_argument("--assignee", action="append")
    issue_create.add_argument("--start", action="store_true", help="Start the created issue immediately.")
    issue_create.add_argument("--no-branch", action="store_true")

    issue_comment = sub.add_parser("issue-comment", help="Comment on the active GitHub issue.")
    issue_comment.add_argument("--body")
    issue_comment.add_argument("--body-file")

    issue_close = sub.add_parser("issue-close", help="Close the active GitHub issue.")
    issue_close.add_argument("--comment")
    issue_close.add_argument("--commit", action="store_true", help="Mention current HEAD commit in close comment.")

    pr_create = sub.add_parser("pr-create", help="Create a PR for the active issue.")
    pr_create.add_argument("--title")
    pr_create.add_argument("--body")
    pr_create.add_argument("--base")
    pr_create.add_argument("--draft", action="store_true", default=True, help="Create draft PR; default behavior.")
    pr_create.add_argument("--ready", dest="draft", action="store_false", help="Create ready-for-review PR.")
    pr_create.add_argument("--close-issue-on-merge", action="store_true")

    done = sub.add_parser("done", help="Finish local AI Rail state.")
    done.add_argument("--keep-active", action="store_true")
    done.add_argument("--force", action="store_true", help="Clear active state even with dirty worktree.")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        commands = {
            "init": cmd_init,
            "doctor": cmd_doctor,
            "status": cmd_status,
            "resume": cmd_resume,
            "repo": cmd_repo,
            "active": cmd_active,
            "issue-template": cmd_issue_template,
            "issue-list": cmd_issue_list,
            "start": cmd_start,
            "prompt": cmd_prompt,
            "plan": cmd_plan,
            "phase": cmd_phase,
            "import": cmd_import,
            "review": cmd_review,
            "checks": cmd_checks,
            "patch": cmd_patch,
            "commit": cmd_commit,
            "sync": cmd_sync,
            "issue-create": cmd_issue_create,
            "issue-comment": cmd_issue_comment,
            "issue-close": cmd_issue_close,
            "pr-create": cmd_pr_create,
            "done": cmd_done,
        }
        return commands[args.command](args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
