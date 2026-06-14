from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

RunFunc = Callable[[list[str], int], subprocess.CompletedProcess[str]]


def current_branch(run_func: RunFunc) -> str:
    result = run_func(["git", "branch", "--show-current"], 15)
    return result.stdout.strip() or "unknown"


def changed_files(run_func: RunFunc) -> list[str]:
    result = run_func(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], 30)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git status failed."
        raise RuntimeError(f"Could not inspect changed files: {message}")
    files: list[str] = []
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
            files.append(path)
        if "R" in status or "C" in status:
            i += 1
            if i < len(parts) and parts[i]:
                files.append(parts[i])
        i += 1
    return sorted(set(files))


def untracked_files(run_func: RunFunc) -> list[str]:
    result = run_func(["git", "ls-files", "--others", "--exclude-standard"], 30)
    if result.returncode != 0:
        return []
    return sorted(line for line in result.stdout.splitlines() if line.strip())


def is_probably_text_file(path: Path, max_bytes: int = 20000) -> bool:
    try:
        if path.stat().st_size > max_bytes:
            return False
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\x00" not in sample


def reviewed_untracked_text_contents(root_path: Path, untracked: list[str], max_file_chars: int = 12000, max_total_chars: int = 50000) -> str:
    sections: list[str] = []
    total = 0
    for rel in untracked:
        path = root_path / rel
        if not path.is_file():
            continue
        if not is_probably_text_file(path):
            block = f"### {rel}\n\n[skipped: binary or larger than 20KB]\n"
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            if len(text) > max_file_chars:
                text = text[:max_file_chars] + "\n[truncated]\n"
            block = f"### {rel}\n\n```text\n{text}\n```\n"
        if total + len(block) > max_total_chars:
            sections.append("[untracked file content truncated]\n")
            break
        sections.append(block)
        total += len(block)
    return "\n".join(sections).strip()


def git_diff_for_fingerprint(run_func: RunFunc) -> str:
    result = run_func(["git", "diff", "--", "."], 30)
    return result.stdout if result.returncode == 0 else result.stderr


def git_ref_exists(ref: str, run_func: RunFunc) -> bool:
    if not ref or not shutil.which("git"):
        return False
    result = run_func(["git", "rev-parse", "--verify", "--quiet", ref], 5)
    return result.returncode == 0


def git_has_upstream(run_func: RunFunc) -> bool:
    if not shutil.which("git"):
        return False
    result = run_func(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], 15)
    return result.returncode == 0 and bool(result.stdout.strip())


def branch_exists_locally(branch: str, run_func: RunFunc) -> bool:
    if not branch or not shutil.which("git"):
        return False
    result = run_func(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], 5)
    return result.returncode == 0


def branch_exists_remotely(branch: str, run_func: RunFunc) -> bool:
    if not branch or not shutil.which("git"):
        return False
    show_ref = run_func(["git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}"], 5)
    if show_ref.returncode == 0:
        return True
    result = run_func(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], 10)
    return result.returncode == 0


def rail_runtime_tracked_on_branch(branch: str, run_func: RunFunc) -> bool:
    if not branch or not shutil.which("git"):
        return False
    result = run_func(["git", "cat-file", "-e", f"{branch}:.rail/rail.py"], 10)
    return result.returncode == 0


def latest_change_mtime(root_path: Path, paths: list[str]) -> float | None:
    mtimes: list[float] = []
    for rel in paths:
        path = root_path / rel
        if path.exists():
            try:
                mtimes.append(path.stat().st_mtime)
            except OSError:
                continue
    return max(mtimes) if mtimes else None


def artifact_is_fresh(path: Path, root_path: Path, paths: list[str]) -> bool:
    if not path.exists():
        return False
    latest = latest_change_mtime(root_path, paths)
    if latest is None:
        return True
    return path.stat().st_mtime + 1 >= latest


def git_status_porcelain(run_func: RunFunc) -> str:
    result = run_func(["git", "status", "--short"], 30)
    if result.returncode != 0:
        return "git status unavailable"
    return result.stdout.strip() or "clean"


def git_state_path(root_path: Path, name: str, run_func: RunFunc) -> Path | None:
    if not shutil.which("git"):
        return None
    result = run_func(["git", "rev-parse", "--git-path", name], 15)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = root_path / path
    return path


def git_path_exists(root_path: Path, name: str, run_func: RunFunc) -> bool:
    path = git_state_path(root_path, name, run_func)
    return bool(path and path.exists())


def unmerged_files(run_func: RunFunc) -> list[str]:
    if not shutil.which("git"):
        return []
    result = run_func(["git", "diff", "--name-only", "--diff-filter=U"], 30)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def git_safety_preflight(root_path: Path, default_branch: str, run_func: RunFunc) -> dict[str, Any]:
    merge_active = git_path_exists(root_path, "MERGE_HEAD", run_func)
    rebase_active = git_path_exists(root_path, "rebase-merge", run_func) or git_path_exists(root_path, "rebase-apply", run_func)
    cherry_pick_active = git_path_exists(root_path, "CHERRY_PICK_HEAD", run_func)
    revert_active = git_path_exists(root_path, "REVERT_HEAD", run_func)
    conflicts = unmerged_files(run_func)
    return {
        "current_branch": current_branch(run_func),
        "default_branch": default_branch,
        "unmerged_files": conflicts,
        "has_unresolved_conflicts": bool(conflicts),
        "merge_active": merge_active,
        "rebase_active": rebase_active,
        "cherry_pick_active": cherry_pick_active,
        "revert_active": revert_active,
        "has_active_git_operation": merge_active or rebase_active or cherry_pick_active or revert_active,
    }


def git_state_blocks_new_work(state: dict[str, Any]) -> bool:
    return bool(state.get("has_unresolved_conflicts") or state.get("has_active_git_operation"))
