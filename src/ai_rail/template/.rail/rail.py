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
from pathlib import Path
from typing import Any


VERSION = "0.1.0a7"

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
- Do not run broad checks.
- Do not close the issue.
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


def current_branch() -> str:
    if not git_available():
        return "unknown"
    result = run(["git", "branch", "--show-current"], timeout=15)
    return result.stdout.strip() or "unknown"


def git_status_short() -> str:
    if not git_available():
        return "git unavailable"
    return run(["git", "status", "--short"], timeout=30).stdout.strip()


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
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".turbo",
    ".pytest_cache",
    "__pycache__",
}


def git_status_entries() -> list[tuple[str, str]]:
    """Return porcelain status/path pairs using NUL separators for robust paths."""
    if not git_available():
        return []
    result = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], timeout=30)
    if result.returncode != 0:
        return []

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


def is_dangerous_commit_path(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/").strip("/")
    name = Path(normalized).name
    parts = set(Path(normalized).parts)

    if normalized.startswith(".rail/state/"):
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
    - latest / lastest: most recently updated open issue
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
            issues = sorted(issues, key=lambda item: int(item["number"]))
        if not issues:
            raise RuntimeError("No open GitHub issues found for `next`.")
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


def build_codex_prompt(active: dict[str, Any]) -> str:
    cfg = load_config()
    issue = active.get("issue", {})
    context_files = cfg.get("context_files") or [".rail/AGENTS.md", ".rail/PROJECT.md"]

    return f"""Read only:
{chr(10).join(f"- {item}" for item in context_files)}
- GitHub issue #{issue.get("number")}: {issue.get("title")}

Work only on the active issue.

Issue body:
```markdown
{issue.get("body", "").strip()}
```

Rules:
- Keep scope small.
- Touch only files needed for this issue.
- Do not inspect unrelated app areas.
- Do not run broad/full checks unless explicitly asked.
- Do not commit.
- Do not close the issue.
- Do not run AI Rail `done`.
- Stop and explain if the task requires broader architectural changes.

When done, summarize:
- files changed
- behavior changed
- focused checks run, if any
- remaining risks

The human will run final checks manually.
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
- Are the changed files reasonable?
- Are checks enough?
- Is it safe to commit?
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

    status = git_status_short()
    count = dirty_count()
    print(f"\nDirty files: {count}")
    if status:
        print(status)

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
    existing_active = active_issue()
    if existing_active and not args.force:
        old = existing_active.get("issue", {})
        print(f"Error: issue #{old.get('number')} is already active: {old.get('title')}")
        print(f"Starting {args.issue_ref} would replace it.")
        print("Run `rail done` first, or use `rail start ... --force` if you really want to replace it.")
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
    commands = args.run_commands or cfg.get("checks") or []
    if not commands:
        output = f"# AI Rail Checks\n\nStarted: {utc_now()}\n\nNo checks configured.\n\nExit code: 0\n\nFinished: {utc_now()}\n"
        write_text(LAST_CHECKS_PATH, output)
        print(output)
        return 0

    outputs = [f"# AI Rail Checks\n\nStarted: {utc_now()}\n"]
    exit_code = 0
    for command in commands:
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
        if result.returncode != 0 and exit_code == 0:
            exit_code = result.returncode or 1
        outputs.append(f"Exit code: {result.returncode}\n")
        outputs.append("### stdout\n")
        outputs.append(f"```text\n{result.stdout[-8000:]}\n```\n")
        outputs.append("### stderr\n")
        outputs.append(f"```text\n{result.stderr[-8000:]}\n```\n")

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
    checkout = run(["git", "checkout", branch], timeout=60)
    if checkout.returncode != 0:
        print(checkout.stderr.strip() or checkout.stdout.strip())
        return checkout.returncode or 1

    pull = run(["git", "pull"], timeout=120)
    if pull.returncode != 0:
        print(pull.stderr.strip() or pull.stdout.strip())
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
    if body:
        tmp_path = STATE_DIR / "issue-create-body.md"
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
    print(f"# or manually: git checkout {db} && git pull")
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

    start = sub.add_parser("start", help="Start a GitHub issue by number, latest, lastest, or next.")
    start.add_argument("issue_ref", help="Issue number, latest, lastest, or next.")
    start.add_argument("--no-branch", action="store_true", help="Do not create/switch issue branch.")
    start.add_argument("--reset-branch", action="store_true", help="Reset existing issue branch to current HEAD.")
    start.add_argument("--force", action="store_true", help="Replace active issue if one already exists.")

    prompt = sub.add_parser("prompt", help="Print a prompt.")
    prompt.add_argument("kind", choices=["codex", "review"])
    prompt.add_argument("--copy", action="store_true", help="Also copy prompt to clipboard when possible.")

    review = sub.add_parser("review", help="Capture git review info.")
    review.add_argument("--max-chars", type=int, default=30000)
    review.add_argument("--full-diff", action="store_true", help="Include full git diff in last-review.md.")

    checks = sub.add_parser("checks", help="Run configured or supplied checks.")
    checks.add_argument("run_commands", nargs="*", help="Optional commands to run instead of configured checks.")
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

    sync = sub.add_parser("sync", help="Checkout default branch and pull.")
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
