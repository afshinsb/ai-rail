from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Any

VERSION = "0.1.0a9"
PROJECT_DESCRIPTION = "A local-first workflow rail and portable project brain for AI-assisted development."
AUTHOR_NAME = "Afshin Saberi"
PROJECT_REPOSITORY = "https://github.com/afshinsb/ai-rail"
AUTHOR_WEBSITE = "https://theafshin.com"
PROJECT_LICENSE = "Apache-2.0"
VALID_MODELS = {"codex", "patch", "ai-direct"}
UNCONFIGURED_REPOSITORY_VALUES = {None, "", "CHANGE_ME"}
UNCONFIGURED_CONFIG_VALUES = {None, "", "CHANGE_ME"}
COMMAND_ALIASES = {
    "r": ["resume"],
    "n": ["next", "--copy"],
    "v": ["verify", "--copy"],
    "s": ["ship"],
    "snap": ["snapshot"],
    "h": ["handoff", "--for", "generic", "--copy"],
    "hc": ["handoff", "--for", "codex", "--copy"],
    "hg": ["handoff", "--for", "chatgpt", "--copy"],
    "hl": ["handoff", "--for", "claude", "--copy"],
    "x": ["export"],
    "xd": ["export", "--dry-run"],
    "xf": ["export", "--force"],
    "rc": ["release-check"],
}
PRESERVED_TEMPLATE_DIRS = {
    Path(".rail/state"),
    Path(".rail/reports"),
    Path(".rail/prompts"),
}
TEMPLATE_CONFIG = Path(".rail/config.json")


def root() -> Path:
    return Path.cwd()


def rail_dir() -> Path:
    return root() / ".rail"


def state() -> Path:
    return rail_dir() / "state"


def local_py() -> Path:
    return rail_dir() / "rail.py"


def active_path() -> Path:
    return state() / "active.json"


def history_path() -> Path:
    return state() / "history.jsonl"


def checks_path() -> Path:
    return state() / "last-checks.md"


def review_path() -> Path:
    return state() / "last-review.md"


def brain_dir() -> Path:
    return rail_dir() / "brain"


def handoff_state_path(target: str) -> Path:
    safe = re.sub(r"[^a-z0-9_-]+", "-", target.lower()).strip("-") or "generic"
    return state() / f"last-handoff-{safe}.md"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=root(), text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout)


def is_unconfigured_repository(value: Any) -> bool:
    return value in UNCONFIGURED_REPOSITORY_VALUES


def is_unconfigured_config_value(value: Any) -> bool:
    return value is None or value == "" or value == "CHANGE_ME"


def checks_for_stack(stack: str) -> list[str]:
    if stack == "python":
        return ["python -m pytest"]
    if stack == "static":
        return []
    return ["npm run check"]


def is_unconfigured_checks(value: Any) -> bool:
    if is_unconfigured_config_value(value):
        return True
    if value == []:
        return True
    return isinstance(value, list) and value in [checks_for_stack("node"), checks_for_stack("python"), checks_for_stack("static")]


def configured_repository(config: dict[str, Any]) -> str:
    repository = config.get("repository")
    if is_unconfigured_repository(repository):
        return detect_repo_from_tools() or "not configured"
    return str(repository)


def append_flag(args: list[str], enabled: bool, flag: str) -> None:
    if enabled:
        args.append(flag)


def expand_alias(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    expansion = COMMAND_ALIASES.get(argv[0])
    if not expansion:
        return argv
    return [*expansion, *argv[1:]]


def render_version() -> str:
    return f"""AI Rail {VERSION}

Created by {AUTHOR_NAME}
{PROJECT_REPOSITORY}
"""


def render_about() -> str:
    return f"""AI Rail

{PROJECT_DESCRIPTION}

Version: {VERSION}
Author: {AUTHOR_NAME}
Repository: {PROJECT_REPOSITORY}
Website: {AUTHOR_WEBSITE}
License: {PROJECT_LICENSE}
"""


def detect_repo_from_tools() -> str | None:
    """Best-effort repository detection without trusting config.json placeholders.

    Prefer the local git remote because it is fast and non-interactive. Fall
    back to `gh repo view` only after git remote detection fails; this avoids
    slow auth/network waits during `rail init` in local demo/test repos.
    """
    if shutil.which("git"):
        inside = run(["git", "rev-parse", "--is-inside-work-tree"], timeout=5)
        result = run(["git", "remote", "get-url", "origin"], timeout=5)
        url = result.stdout.strip()
        if url:
            match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
            if match:
                return match.group(1)
        if inside.returncode == 0 and inside.stdout.strip() == "true":
            return None
    if shutil.which("gh"):
        result = run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


def rewrite_core_output(text: str) -> str:
    """Rewrite legacy local-core hints from alias style to public CLI style.

    This intentionally catches inline hints such as:
    - "rail issue-list  # then: o start next"
    - "fix the failure, then run: o review && o checks"

    It avoids normal words because the `o` must be a standalone command token.
    """
    if not text:
        return text
    return re.sub(r"(?<![a-zA-Z])o\s+(?=[a-z])", "rail ", text)


def delegate(args: list[str]) -> int:
    if not local_py().exists():
        print("No .rail/rail.py found. Run: rail init", file=sys.stderr)
        return 1
    result = subprocess.run(
        [sys.executable, str(local_py()), *args],
        cwd=root(),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=300,
    )
    if result.stdout:
        print(rewrite_core_output(result.stdout), end="")
    if result.stderr:
        print(rewrite_core_output(result.stderr), end="", file=sys.stderr)
    return result.returncode


def is_relative_to_path(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def backup_file(path: Path) -> Path:
    backup = path.with_name(path.name + ".rail.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
        return backup
    i = 2
    while True:
        candidate = path.with_name(f"{path.name}.rail.bak.{i}")
        if not candidate.exists():
            shutil.copy2(path, candidate)
            return candidate
        i += 1


def install_template(src: Path, dst: Path, force: bool = False) -> dict[str, Any]:
    preserved_existing_dirs = {rel for rel in PRESERVED_TEMPLATE_DIRS if (dst / rel).exists()}
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "preserved_dirs": sorted(str(path).replace("\\", "/") for path in preserved_existing_dirs),
        "config": "created",
        "config_backup": None,
        "config_updates": [],
    }

    for p in src.rglob("*"):
        rel = p.relative_to(src)
        target = dst / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if any(is_relative_to_path(rel, preserved) for preserved in preserved_existing_dirs):
            summary["skipped"] += 1
            continue
        if rel == TEMPLATE_CONFIG and target.exists():
            try:
                read_json(target, {})
            except json.JSONDecodeError:
                backup = backup_file(target)
                shutil.copy2(p, target)
                summary["updated"] += 1
                summary["config"] = "replaced"
                summary["config_backup"] = str(backup.relative_to(dst)).replace("\\", "/")
            else:
                summary["skipped"] += 1
                summary["config"] = "preserved"
            continue
        if target.exists() and not force:
            summary["skipped"] += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        shutil.copy2(p, target)
        summary["updated" if existed else "created"] += 1
    return summary


def print_install_summary(summary: dict[str, Any]) -> None:
    print(f"- Created files: {summary['created']}")
    print(f"- Updated files: {summary['updated']}")
    print(f"- Skipped files: {summary['skipped']}")
    config = summary["config"]
    if config == "preserved":
        print("- Preserved .rail/config.json")
    elif config == "replaced":
        print(f"- Backed up invalid .rail/config.json to {summary['config_backup']} and installed a fresh config")
    else:
        print("- Created .rail/config.json")
    if summary["config_updates"]:
        print("- Updated placeholder config values: " + ", ".join(summary["config_updates"]))
    for preserved in summary["preserved_dirs"]:
        print(f"- Preserved {preserved}/")


def cmd_init(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail init")
    parser.add_argument("--stack", choices=["node", "python", "static"], default="node")
    parser.add_argument("--project-name")
    parser.add_argument("--force", action="store_true")
    ns = parser.parse_args(argv)
    explicit_stack = any(arg == "--stack" or arg.startswith("--stack=") for arg in argv)

    cfg_path = rail_dir() / "config.json"
    had_config = cfg_path.exists()
    template_path = resources.files("ai_rail") / "template"
    summary = install_template(Path(str(template_path)), root(), force=ns.force)

    cfg = read_json(cfg_path, {})
    should_apply_init_defaults = not had_config or summary["config"] == "replaced"
    config_updates: list[str] = []
    if ns.project_name and should_apply_init_defaults:
        cfg["project_name"] = ns.project_name
    elif ns.project_name and is_unconfigured_config_value(cfg.get("project_name")):
        cfg["project_name"] = ns.project_name
        config_updates.append("project_name")

    if should_apply_init_defaults:
        # Stack presets are authoritative during first init; template defaults should not leak.
        cfg["checks"] = checks_for_stack(ns.stack)
    elif explicit_stack and is_unconfigured_checks(cfg.get("checks")):
        new_checks = checks_for_stack(ns.stack)
        if cfg.get("checks") != new_checks:
            cfg["checks"] = new_checks
            config_updates.append("checks")

    if "stack" in cfg and explicit_stack and is_unconfigured_config_value(cfg.get("stack")):
        cfg["stack"] = ns.stack
        config_updates.append("stack")

    if is_unconfigured_config_value(cfg.get("default_branch")):
        cfg["default_branch"] = "main"
        config_updates.append("default_branch")

    detected_repo = detect_repo_from_tools()
    if detected_repo and is_unconfigured_repository(cfg.get("repository")):
        cfg["repository"] = detected_repo
        print(f"Detected GitHub repo: {detected_repo}")
        if not should_apply_init_defaults:
            config_updates.append("repository")
    elif should_apply_init_defaults and is_unconfigured_repository(cfg.get("repository")):
        print("Repository not detected yet. Set .rail/config.json repository when ready.")

    summary["config_updates"] = config_updates
    if should_apply_init_defaults or config_updates:
        write_json(cfg_path, cfg)

    # Make the compatibility script executable when supported.
    try:
        local_py().chmod(local_py().stat().st_mode | 0o111)
    except Exception:
        pass

    print(f"Initialized AI Rail v{VERSION} in {rail_dir()}")
    print_install_summary(summary)
    print("\nNext:")
    print("rail doctor")
    print("rail status")
    return 0


def cmd_upgrade(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail upgrade")
    parser.parse_args(argv)

    if not rail_dir().exists():
        print("No .rail folder found. Run: rail init", file=sys.stderr)
        return 1

    template_path = resources.files("ai_rail") / "template"
    summary = install_template(Path(str(template_path)), root(), force=True)

    try:
        local_py().chmod(local_py().stat().st_mode | 0o111)
    except Exception:
        pass

    print(f"Upgraded AI Rail local runtime/template files to v{VERSION}.")
    print_install_summary(summary)
    return 0


def active() -> dict[str, Any] | None:
    return read_json(active_path(), None)


def active_model() -> str | None:
    item = active()
    if not item:
        return None
    model = item.get("interaction_model") or item.get("mode") or "codex"
    # Legacy local runtime stores mode="issue". That is workflow state, not
    # an interaction model, so treat it as the default Codex loop.
    return "codex" if model == "issue" else model


def set_active_model(model: str) -> None:
    item = active()
    if not item:
        return
    item["interaction_model"] = model
    item.setdefault("rail_started_at", utc_now())
    write_json(active_path(), item)


def checks_result() -> str:
    if not checks_path().exists():
        return "missing"
    text = checks_path().read_text(encoding="utf-8", errors="replace")
    codes = [int(x) for x in re.findall(r"Exit code:\s*(\d+)", text)]
    if not codes:
        return "unknown"
    return "passed" if all(c == 0 for c in codes) else "failed"


def current_branch() -> str:
    r = run(["git", "branch", "--show-current"], timeout=15)
    return r.stdout.strip() or "unknown"


def changed_files() -> list[str]:
    r = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], timeout=30)
    if r.returncode != 0:
        return []
    files: list[str] = []
    parts = r.stdout.split("\0")
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


def latest_commit() -> str | None:
    r = run(["git", "rev-parse", "--short", "HEAD"], timeout=15)
    return r.stdout.strip() or None


def history_append(entry: dict[str, Any]) -> None:
    state().mkdir(parents=True, exist_ok=True)
    with history_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def read_history_entries() -> list[dict[str, Any]]:
    """Read history.jsonl defensively.

    A CLI should not crash if a user manually edits the file or a previous
    process leaves a partial/corrupt line. Invalid lines are skipped.
    """
    if not history_path().exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in history_path().read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    return entries


def cmd_start(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail start")
    parser.add_argument("issue_ref")
    parser.add_argument("--model", choices=sorted(VALID_MODELS), default="codex")
    parser.add_argument("--no-branch", action="store_true")
    parser.add_argument("--reset-branch", action="store_true")
    parser.add_argument("--force", action="store_true")
    ns = parser.parse_args(argv)

    delegate_args = ["start", ns.issue_ref]
    append_flag(delegate_args, ns.no_branch or ns.model == "ai-direct", "--no-branch")
    append_flag(delegate_args, ns.reset_branch, "--reset-branch")
    append_flag(delegate_args, ns.force, "--force")

    rc = delegate(delegate_args)
    if rc == 0:
        set_active_model(ns.model)
        print(f"[rail] interaction_model={ns.model}")
        if ns.model == "codex":
            print("Next: rail prompt codex --copy")
        elif ns.model == "patch":
            print("Next: rail patch PATCH_FILE --check-only")
        else:
            print("Next: use AI-direct GitHub workflow, then fetch/pull locally")
    return rc



def cmd_next(argv: list[str]) -> int:
    """Start the next task and optionally produce the first AI prompt.

    This is a short daily wrapper over the existing start/prompt commands.
    It intentionally does not change the underlying workflow engine.
    """
    parser = argparse.ArgumentParser(prog="rail next")
    parser.add_argument("issue_ref", nargs="?", default="next", help="Issue number, next, or latest. Also accepts lastest as a typo alias. Default: next.")
    parser.add_argument("--model", choices=sorted(VALID_MODELS), default="codex")
    parser.add_argument("--copy", action="store_true", help="Copy generated Codex prompt to clipboard when possible.")
    parser.add_argument("--no-prompt", action="store_true", help="Only start the issue; do not generate a prompt.")
    parser.add_argument("--no-branch", action="store_true")
    parser.add_argument("--reset-branch", action="store_true")
    parser.add_argument("--force", action="store_true")
    ns = parser.parse_args(argv)

    start_args = [ns.issue_ref, "--model", ns.model]
    append_flag(start_args, ns.no_branch, "--no-branch")
    append_flag(start_args, ns.reset_branch, "--reset-branch")
    append_flag(start_args, ns.force, "--force")

    rc = cmd_start(start_args)
    if rc != 0 or ns.no_prompt:
        return rc

    if ns.model == "codex":
        prompt_args = ["codex"]
        append_flag(prompt_args, ns.copy, "--copy")
        return cmd_prompt(prompt_args)

    if ns.model == "patch":
        print("\n[rail] Patch model selected.")
        print("Next: ask ChatGPT for a small .patch file, then run `rail patch PATCH_FILE`.")
        return 0

    print("\n[rail] AI-direct model selected.")
    print("Next: use the external AI/GitHub workflow, then fetch or pull locally.")
    return 0


def cmd_verify(argv: list[str]) -> int:
    """Capture review info, run checks, and generate the review prompt.

    This is a short daily wrapper over review/checks/prompt review. It still
    returns the checks exit code so failures are visible to shells/CI, but it
    generates the review prompt even when checks fail.
    """
    parser = argparse.ArgumentParser(prog="rail verify")
    parser.add_argument("--copy", action="store_true", help="Copy generated review prompt to clipboard when possible.")
    parser.add_argument("--no-checks", action="store_true", help="Capture review and prompt only; skip checks.")
    parser.add_argument("--full-diff", action="store_true", help="Include full git diff in last-review.md.")
    parser.add_argument("--max-chars", type=int, default=30000)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("run_commands", nargs="*", help="Optional check commands to run instead of configured checks.")
    ns = parser.parse_args(argv)

    review_args = ["--max-chars", str(ns.max_chars)]
    append_flag(review_args, ns.full_diff, "--full-diff")
    review_rc = delegate(["review", *review_args])

    checks_rc = 0
    if not ns.no_checks:
        checks_args = ["--timeout", str(ns.timeout), *ns.run_commands]
        checks_rc = delegate(["checks", *checks_args])

    prompt_args = ["review"]
    append_flag(prompt_args, ns.copy, "--copy")
    prompt_rc = cmd_prompt(prompt_args)

    return checks_rc or review_rc or prompt_rc


def cmd_ship(argv: list[str]) -> int:
    """Commit, push, close the active issue, clear state, and optionally sync.

    This is a short daily wrapper over the existing commit/issue-close/done/sync
    sequence. Safety checks are enforced by the underlying commit command.
    """
    parser = argparse.ArgumentParser(prog="rail ship")
    parser.add_argument("message", help="Commit message.")
    parser.add_argument("--no-push", action="store_true", help="Commit but do not push.")
    parser.add_argument("--amend", action="store_true", help="Amend previous commit.")
    parser.add_argument("--force", action="store_true", help="Pass --force to commit/done where applicable.")
    parser.add_argument("--allow-missing-checks", action="store_true", help="Allow ship when checks are missing/unknown.")
    parser.add_argument("--allow-stale", action="store_true", help="Allow ship when checks are older than changed files.")
    parser.add_argument("--no-close", action="store_true", help="Do not close the active GitHub issue.")
    parser.add_argument("--no-done", action="store_true", help="Do not clear the active AI Rail state.")
    parser.add_argument("--no-sync", action="store_true", help="Do not switch back to the default branch and pull.")
    parser.add_argument("--keep-active", action="store_true", help="Keep active issue when running done.")
    ns = parser.parse_args(argv)

    commit_args = ["commit", ns.message]
    append_flag(commit_args, ns.no_push, "--no-push")
    append_flag(commit_args, ns.amend, "--amend")
    append_flag(commit_args, ns.force, "--force")
    append_flag(commit_args, ns.allow_missing_checks, "--allow-missing-checks")
    append_flag(commit_args, ns.allow_stale, "--allow-stale")

    rc = delegate(commit_args)
    if rc != 0:
        print("[rail] Ship stopped during commit; no later ship steps ran.")
        return rc

    if not ns.no_close:
        rc = delegate(["issue-close", "--commit"])
        if rc != 0:
            print("[rail] Ship stopped after commit succeeded; issue close failed. Active state was kept.")
            print("[rail] Recovery: close the GitHub issue manually or fix `gh auth login`, then run:")
            print("[rail]   rail done")
            print("[rail]   rail sync")
            return rc

    if not ns.no_done:
        done_args: list[str] = []
        append_flag(done_args, ns.keep_active, "--keep-active")
        append_flag(done_args, ns.force, "--force")
        rc = cmd_done(done_args)
        if rc != 0:
            print("[rail] Ship stopped after commit and issue-close succeeded; done failed.")
            return rc

    if not ns.no_sync:
        rc = delegate(["sync"])
        if rc != 0:
            print("[rail] Ship stopped after commit, issue-close, and done succeeded; sync failed.")
            return rc

    print("\n[rail] Ship complete.")
    return 0

def cmd_prompt(argv: list[str]) -> int:
    if argv and argv[0] == "codex":
        model = active_model()
        forced = "--force" in argv
        if model and model != "codex" and not forced:
            print(f"Error: active issue is in Model `{model}`. Codex prompt is only for Model `codex`.")
            print("Use `rail prompt codex --force` only if intentional.")
            return 1
        if model and model != "codex" and forced:
            print(f"[rail] Warning: running Codex prompt despite active model being `{model}`.")
        argv = [x for x in argv if x != "--force"]
    return delegate(["prompt", *argv])


def cmd_patch(argv: list[str]) -> int:
    model = active_model()
    forced = "--force" in argv
    if model and model != "patch" and not forced:
        print(f"Error: active issue is in Model `{model}`. Patch command is for Model `patch`.")
        print("Start with `rail start ISSUE --model patch`, or rerun with `--force` if intentional.")
        return 1
    if model and model != "patch" and forced:
        print(f"[rail] Warning: running patch despite active model being `{model}`.")
    argv = [x for x in argv if x != "--force"]
    return delegate(["patch", *argv])


def cmd_status(argv: list[str]) -> int:
    rc = delegate(["status", *argv])
    print("\n[rail] Public CLI layer")
    print(f"[rail] interaction_model: {active_model() or 'none'}")
    print(f"[rail] history entries: {history_count()}")
    return rc


def history_count() -> int:
    return len(read_history_entries())


def completed_history_entry(item: dict[str, Any]) -> dict[str, Any]:
    issue = item.get("issue", {})
    return {
        "completed_at": utc_now(),
        "issue": issue.get("number"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "interaction_model": item.get("interaction_model", "codex"),
        "branch": item.get("branch") or current_branch(),
        "commit": latest_commit(),
        "checks_result": checks_result(),
        "files_changed": changed_files(),
    }


def cmd_done(argv: list[str]) -> int:
    item = active()
    rc = delegate(["done", *argv])
    if rc == 0 and item:
        entry = completed_history_entry(item)
        history_append(entry)
        print(f"[rail] history appended for issue #{entry.get('issue')}")
    return rc


def cmd_log(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail log")
    parser.add_argument("--last", type=int, default=10)
    parser.add_argument("--verbose", action="store_true")
    ns = parser.parse_args(argv)
    entries = read_history_entries()
    if not entries:
        print("No AI Rail history yet.")
        return 0
    for item in entries[-ns.last:]:
        print(f"#{item.get('issue')} | {item.get('interaction_model')} | {item.get('checks_result')} | {item.get('commit') or '-'} | {item.get('title')}")
        if ns.verbose:
            print(json.dumps(item, indent=2))
    return 0


def cmd_report(argv: list[str]) -> int:
    entries = read_history_entries()
    if not entries:
        print("No AI Rail history yet.")
        return 0
    print("# AI Rail Report")
    print(f"Completed issues: {len(entries)}")
    by_model: dict[str, int] = {}
    by_checks: dict[str, int] = {}
    for item in entries:
        by_model[item.get("interaction_model", "unknown")] = by_model.get(item.get("interaction_model", "unknown"), 0) + 1
        by_checks[item.get("checks_result", "unknown")] = by_checks.get(item.get("checks_result", "unknown"), 0) + 1
    print("\nBy model:")
    for k, v in sorted(by_model.items()):
        print(f"- {k}: {v}")
    print("\nBy checks result:")
    for k, v in sorted(by_checks.items()):
        print(f"- {k}: {v}")
    return 0




def safe_read_text(path: Path, default: str = "", max_chars: int | None = None) -> str:
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + f"\n\n[truncated at {max_chars} chars]\n"
    return text


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
            subprocess.run(command, input=text, text=True, encoding="utf-8", check=True, timeout=10)
            return True
        except Exception:
            continue
    return False


def git_status_porcelain() -> str:
    result = run(["git", "status", "--short"], timeout=30)
    if result.returncode != 0:
        return "git status unavailable"
    return result.stdout.strip() or "clean"


def cfg() -> dict[str, Any]:
    return read_json(rail_dir() / "config.json", {})


def active_issue_summary() -> dict[str, Any]:
    item = active() or {}
    issue = item.get("issue") or {}
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "body": issue.get("body") or "",
        "interaction_model": item.get("interaction_model") or active_model() or "none",
        "branch": item.get("branch") or current_branch(),
        "started_at": item.get("started_at") or item.get("rail_started_at") or item.get("created_at"),
    }


def recent_history_lines(max_history: int = 5) -> list[str]:
    entries = read_history_entries()[-max_history:]
    if not entries:
        return ["No completed AI Rail history yet."]
    lines: list[str] = []
    for item in entries:
        issue = item.get("issue") or "?"
        title = item.get("title") or "Untitled"
        model = item.get("interaction_model") or "unknown"
        checks = item.get("checks_result") or "unknown"
        commit = item.get("commit") or "-"
        completed = item.get("completed_at") or "unknown time"
        lines.append(f"- #{issue} | {model} | checks: {checks} | commit: {commit} | {completed} | {title}")
    return lines


def render_project_brain(max_history: int = 5) -> dict[str, str]:
    config = cfg()
    active_issue = active_issue_summary()
    checks = checks_result()
    status = git_status_porcelain()
    files = changed_files()

    project_name = config.get("project_name") or root().name
    repository = configured_repository(config)
    check_commands = config.get("checks") or []

    project = f"""# Project

- Name: {project_name}
- Repository: {repository}
- Root: {root()}
- AI Rail version: {VERSION}

## Purpose

This repo uses AI Rail as a local-first project brain and workflow rail for AI-assisted development.

## Configured checks
{chr(10).join(f"- `{cmd}`" for cmd in check_commands) if check_commands else "- No checks configured."}
"""

    if active_issue.get("number"):
        current = f"""# Current Task

- Issue: #{active_issue.get('number')} — {active_issue.get('title')}
- URL: {active_issue.get('url') or '-'}
- Active model: {active_issue.get('interaction_model')}
- Branch: {active_issue.get('branch')}
- Started: {active_issue.get('started_at') or '-'}

## Issue body

{active_issue.get('body') or '_No issue body captured._'}
"""
    else:
        current = "# Current Task\n\nNo active AI Rail issue. Use `rail next` or `rail start ISSUE`.\n"

    status_doc = f"""# Status

- Generated: {utc_now()}
- Branch: {current_branch()}
- Checks result: {checks}
- Git status: {status}

## Changed files
{chr(10).join(f"- {path}" for path in files) if files else "- None"}
"""

    history = "# Recent History\n\n" + "\n".join(recent_history_lines(max_history)) + "\n"

    handoff = f"""# Handoff Summary

Generated by `rail snapshot` at {utc_now()}.

## Where we are

- Project: {project_name}
- Branch: {current_branch()}
- Active issue: {('#' + str(active_issue.get('number')) + ' — ' + str(active_issue.get('title'))) if active_issue.get('number') else 'none'}
- Active model: {active_issue.get('interaction_model')}
- Checks: {checks}
- Dirty files: {len(files)}

## Next safe action

{next_safe_action(checks, bool(active_issue.get('number')), files)}
"""

    return {
        "PROJECT.md": project,
        "CURRENT_TASK.md": current,
        "STATUS.md": status_doc,
        "RECENT_HISTORY.md": history,
        "HANDOFF.md": handoff,
    }


def next_safe_action(checks: str, has_active: bool, files: list[str]) -> str:
    if not has_active:
        return "Start the next task with `rail next`."
    if files and checks != "passed":
        return "Run `rail verify` before shipping."
    if files and checks == "passed":
        return "Ask an AI reviewer to inspect the handoff/review, then run `rail ship \"type(scope): message\"` when approved."
    return "Continue the active task or run `rail verify` if implementation is complete."


def cmd_snapshot(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail snapshot")
    parser.add_argument("--max-history", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    ns = parser.parse_args(argv)

    if not rail_dir().exists():
        print("No .rail folder found. Run: rail init", file=sys.stderr)
        return 1

    docs = render_project_brain(max_history=ns.max_history)
    brain_dir().mkdir(parents=True, exist_ok=True)
    for name, content in docs.items():
        (brain_dir() / name).write_text(content, encoding="utf-8")

    if not ns.quiet:
        print("Updated AI Rail project brain:")
        for name in docs:
            print(f"- .rail/brain/{name}")
    return 0


def target_instructions(target: str) -> str:
    common = """Use this handoff as the source of truth for the current state. Do not assume missing context. Keep scope small, work only on the active issue or requested task, and ask for clarification only when the handoff is insufficient to continue safely."""
    by_target = {
        "generic": "Continue from this project state. Summarize your understanding first, then work only on the requested next step.",
        "chatgpt": "You are the reviewer/planner. Identify drift, check changed files against issue scope, check focused checks, decide whether ship is safe, and give exact next commands. Do not claim you ran commands unless evidence is included.",
        "codex": "You are the coding agent. Implement only the active issue. Read AGENTS.md and the AI Rail brain first. Do not commit, push, close issues, create roadmaps, or run broad/full tests unless explicitly asked.",
        "claude": "You are the coding agent/reviewer. Use the project brain and active task as authoritative context. Keep edits narrow, avoid broad refactors, and report changed files, focused checks, and risks.",
        "cursor": "Use the project brain as repo rules/context. Keep edits scoped to the active issue, avoid broad refactors, and do not run broad/full tests unless explicitly asked.",
        "aider": "Use this as the task brief. Edit only files relevant to the active issue, keep diffs small, run only focused requested checks, and leave commit/review/ship to AI Rail.",
    }
    return common + "\n\n" + by_target.get(target, by_target["generic"])


def render_handoff(target: str, max_history: int = 5, include_review: bool = False, include_checks: bool = False, max_section_chars: int = 12000) -> str:
    docs = render_project_brain(max_history=max_history)
    active_issue = active_issue_summary()
    files = changed_files()
    parts = [
        f"# AI Rail Handoff — {target}\n",
        f"Generated: {utc_now()}\n",
        "## Instruction for the next AI session\n\n" + target_instructions(target) + "\n",
        "## Quick state\n",
        f"- Branch: {current_branch()}",
        f"- Active issue: {('#' + str(active_issue.get('number')) + ' — ' + str(active_issue.get('title'))) if active_issue.get('number') else 'none'}",
        f"- Active model: {active_issue.get('interaction_model')}",
        f"- Checks result: {checks_result()}",
        f"- Changed files: {len(files)}",
        "",
        "## Project brain\n",
    ]
    for name in ["PROJECT.md", "CURRENT_TASK.md", "STATUS.md", "RECENT_HISTORY.md", "HANDOFF.md"]:
        parts.append(f"### .rail/brain/{name}\n")
        parts.append(docs[name].strip() + "\n")

    contract_files = ["AI_CONTRACT.md", "AGENTS.md", "CODEX.md", "CLAUDE.md", "CHATGPT.md"]
    existing_contracts = [(name, rail_dir() / name) for name in contract_files if (rail_dir() / name).exists()]
    if existing_contracts:
        parts.append("## AI contract files\n")
        for name, path in existing_contracts:
            parts.append(f"### .rail/{name}\n")
            parts.append(safe_read_text(path, max_chars=max_section_chars).strip() + "\n")

    if include_review:
        parts.append("## Last review pack\n")
        parts.append(safe_read_text(review_path(), "No last review pack found.", max_chars=max_section_chars).strip() + "\n")

    if include_checks:
        parts.append("## Last checks output\n")
        parts.append(safe_read_text(checks_path(), "No last checks output found.", max_chars=max_section_chars).strip() + "\n")

    parts.append("## Required response format\n")
    parts.append("- Confirm the active task you understand.\n- List any missing context or risk.\n- Then provide the smallest safe next action.\n")
    return "\n".join(parts).rstrip() + "\n"


def cmd_handoff(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail handoff")
    parser.add_argument("--for", dest="target", choices=["generic", "chatgpt", "codex", "claude", "cursor", "aider"], default="generic")
    parser.add_argument("--copy", action="store_true", help="Copy handoff to clipboard when possible.")
    parser.add_argument("--output", help="Write handoff to a specific path instead of the default state file.")
    parser.add_argument("--max-history", type=int, default=5)
    parser.add_argument("--no-snapshot", action="store_true", help="Do not refresh .rail/brain before generating handoff.")
    parser.add_argument("--include-review", action="store_true", help="Include .rail/state/last-review.md content.")
    parser.add_argument("--include-checks", action="store_true", help="Include .rail/state/last-checks.md content.")
    parser.add_argument("--max-section-chars", type=int, default=12000)
    ns = parser.parse_args(argv)

    if not rail_dir().exists():
        print("No .rail folder found. Run: rail init", file=sys.stderr)
        return 1

    if not ns.no_snapshot:
        rc = cmd_snapshot(["--quiet", "--max-history", str(ns.max_history)])
        if rc != 0:
            return rc

    text = render_handoff(
        target=ns.target,
        max_history=ns.max_history,
        include_review=ns.include_review,
        include_checks=ns.include_checks,
        max_section_chars=ns.max_section_chars,
    )
    output = Path(ns.output) if ns.output else handoff_state_path(ns.target)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")

    print(text)
    print(f"[rail] handoff written: {output}")
    if ns.copy:
        if copy_to_clipboard(text):
            print("[rail] handoff copied to clipboard")
        else:
            print("[rail] copy requested, but no supported clipboard command was found")
    return 0


EXPORT_TARGETS = {"agents", "claude", "cursor", "aider", "copilot"}
EXPORT_BEGIN = "<!-- AI_RAIL_EXPORT_BEGIN -->"
EXPORT_END = "<!-- AI_RAIL_EXPORT_END -->"


def export_path_for_target(target: str) -> Path:
    paths = {
        "agents": root() / "AGENTS.md",
        "claude": root() / "CLAUDE.md",
        "cursor": root() / ".cursor" / "rules" / "ai-rail.mdc",
        "aider": root() / "AIDER.md",
        "copilot": root() / ".github" / "copilot-instructions.md",
    }
    return paths[target]


def export_label_for_target(target: str) -> str:
    labels = {
        "agents": "AGENTS.md / Codex-compatible agents",
        "claude": "Claude Code",
        "cursor": "Cursor rules",
        "aider": "Aider",
        "copilot": "GitHub Copilot instructions",
    }
    return labels[target]


def render_export_context(max_history: int = 5) -> str:
    config = cfg()
    active_issue = active_issue_summary()
    files = changed_files()
    project_name = config.get("project_name") or root().name
    repository = configured_repository(config)
    issue_line = (
        f"#{active_issue.get('number')} — {active_issue.get('title')}"
        if active_issue.get("number")
        else "none"
    )
    changed = "\n".join(f"- {path}" for path in files) if files else "- None"
    history = "\n".join(recent_history_lines(max_history))
    issue_body = active_issue.get("body") or "_No active issue body captured._"
    return f"""## AI Rail project state

- Project: {project_name}
- Repository: {repository}
- Branch: {current_branch()}
- Active issue: {issue_line}
- Active model: {active_issue.get('interaction_model')}
- Checks result: {checks_result()}
- Generated: {utc_now()}

### Current task body

{issue_body}

### Changed files
{changed}

### Recent AI Rail history
{history}

### Canonical project brain files

Read these files when available. They are generated by `rail snapshot` and are the most portable source of truth for the current repo state:

- `.rail/brain/PROJECT.md`
- `.rail/brain/CURRENT_TASK.md`
- `.rail/brain/STATUS.md`
- `.rail/brain/RECENT_HISTORY.md`
- `.rail/brain/HANDOFF.md`

### AI Rail workflow rules

- Keep work scoped to the active issue unless the human explicitly changes scope.
- Prefer small diffs over broad rewrites.
- Do not commit, push, close issues, or mark tasks done unless the human explicitly asks.
- Preserve existing architecture and conventions.
- Report changed files and checks clearly.
- If context is missing, state exactly what is missing instead of guessing.
""".rstrip()


def render_tool_export(target: str, max_history: int = 5) -> str:
    context = render_export_context(max_history=max_history)
    target_specific = {
        "agents": """# AGENTS.md

This repository uses AI Rail. Treat this file as repo-level guidance for Codex-compatible AI coding agents.

## Agent role

You are a scoped coding agent. Implement only the active task, keep edits narrow, and leave final review/ship actions to AI Rail and the human operator.

Do not commit, close issues, create unrelated roadmaps, rewrite architecture, or run broad/full tests unless explicitly requested. Run only focused checks related to the task.""",
        "claude": """# CLAUDE.md

This repository uses AI Rail. Treat this file as Claude Code project memory and operating rules.

## Claude role

You may implement or review the active task. Before editing, summarize the active issue and the smallest safe plan. Avoid broad refactors unless explicitly requested.

Do not commit, close issues, create unrelated roadmaps, or run broad/full tests unless explicitly requested. Run only focused checks related to the task.""",
        "aider": """# AIDER.md

This repository uses AI Rail. Treat this file as the active task brief for Aider.

## Aider role

Edit only files relevant to the active issue. Keep commits and shipping outside Aider unless the human explicitly asks for them.

Do not create unrelated roadmaps, rewrite architecture, or run broad/full tests unless explicitly requested. Run only focused checks related to the task.""",
        "copilot": """# GitHub Copilot instructions

This repository uses AI Rail. Use the generated AI Rail project state below as repository guidance.

## Copilot role

Keep suggestions aligned with the active issue, existing architecture, and local checks. Avoid unrelated rewrites.

Do not suggest broad/full test runs unless the issue explicitly asks for them. Prefer focused checks related to the task.""",
    }
    if target == "cursor":
        header = """---
description: AI Rail portable project brain and workflow rules
alwaysApply: true
---

# AI Rail Cursor rules

This repository uses AI Rail. Treat this rule as always-on project context for Cursor.

## Cursor role

Keep edits scoped to the active issue. Use the project brain as authoritative context and avoid broad refactors unless explicitly requested.

Do not commit, close issues, create unrelated roadmaps, or run broad/full tests unless explicitly requested. Run only focused checks related to the task."""
    else:
        header = target_specific[target]
    return f"""{EXPORT_BEGIN}
Generated by `rail export --target {target}` at {utc_now()}.
Do not edit inside this managed block manually. Update it with `rail export`.

{header}

{context}
{EXPORT_END}
"""


def write_managed_export(path: Path, content: str, *, force: bool = False, dry_run: bool = False) -> tuple[bool, str]:
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="replace")
        has_begin = EXPORT_BEGIN in existing
        has_end = EXPORT_END in existing
        if has_begin and has_end:
            before = existing.split(EXPORT_BEGIN, 1)[0]
            after = existing.split(EXPORT_END, 1)[1]
            new_text = before + content + after
            action = "updated"
        elif not force:
            return False, f"refused existing unmarked file: {path} (use --force to replace with backup)"
        else:
            backup = path.with_name(path.name + ".rail.bak")
            if not dry_run:
                backup.write_text(existing, encoding="utf-8")
            new_text = content
            action = f"replaced with backup {backup}"
    else:
        new_text = content
        action = "created"

    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")
    return True, f"{action}: {path}"


def cmd_export(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail export")
    parser.add_argument("--target", action="append", choices=["all", *sorted(EXPORT_TARGETS)], help="Export target. Repeatable. Default: all.")
    parser.add_argument("--force", action="store_true", help="Replace existing unmarked files after writing a .rail.bak backup.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written without changing files.")
    parser.add_argument("--no-snapshot", action="store_true", help="Do not refresh .rail/brain before exporting.")
    parser.add_argument("--max-history", type=int, default=5)
    ns = parser.parse_args(argv)

    if not rail_dir().exists():
        print("No .rail folder found. Run: rail init", file=sys.stderr)
        return 1

    if not ns.no_snapshot and not ns.dry_run:
        rc = cmd_snapshot(["--quiet", "--max-history", str(ns.max_history)])
        if rc != 0:
            return rc

    requested = ns.target or ["all"]
    targets = sorted(EXPORT_TARGETS) if "all" in requested else sorted(set(requested))

    failures: list[str] = []
    print("AI Rail tool exports:" + (" (dry run)" if ns.dry_run else ""))
    for target in targets:
        path = export_path_for_target(target)
        content = render_tool_export(target, max_history=ns.max_history)
        ok, message = write_managed_export(path, content, force=ns.force, dry_run=ns.dry_run)
        label = export_label_for_target(target)
        prefix = "OK" if ok else "SKIP"
        print(f"- {prefix} {label}: {message}")
        if not ok:
            failures.append(message)

    if failures:
        print("\nSome exports were skipped to avoid overwriting human files.")
        print("Use `rail export --force` only when you intentionally want AI Rail to replace them with backups.")
        return 1
    return 0


def cmd_ci_init(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail ci-init")
    parser.add_argument("--force", action="store_true")
    ns = parser.parse_args(argv)
    cfg = read_json(rail_dir() / "config.json", {})
    checks = cfg.get("checks") or []
    if not checks:
        print("No checks configured in .rail/config.json.")
        return 1
    workflow = root() / ".github" / "workflows" / "rail.yml"
    if workflow.exists() and not ns.force:
        print(f"{workflow} already exists. Use --force to overwrite.")
        return 1
    workflow.parent.mkdir(parents=True, exist_ok=True)

    joined = "\n".join(checks).lower()
    uses_python = any(token in joined for token in ["python", "pytest", "pip", "ruff", "mypy"])
    uses_node = any(token in joined for token in ["npm", "node", "pnpm", "yarn", "npx"])

    setup_steps: list[str] = ["      - uses: actions/checkout@v4\n"]

    if uses_python:
        setup_steps.append("""      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
""")
        setup_steps.append("""      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          if [ -f pyproject.toml ]; then pip install -e .; fi
""")

    if uses_node:
        setup_steps.append("""      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
""")
        setup_steps.append("""      - name: Install Node dependencies
        run: |
          if [ -f package-lock.json ]; then npm ci; elif [ -f package.json ]; then npm install; fi
""")

    check_steps = "".join(f"      - name: {cmd}\n        run: {cmd}\n" for cmd in checks)
    content = """name: AI Rail Checks

on:
  push:
  pull_request:

jobs:
  rail:
    runs-on: ubuntu-latest
    steps:
""" + "".join(setup_steps) + check_steps

    workflow.write_text(content, encoding="utf-8")
    print(f"Created {workflow}")
    return 0



def render_demo_script() -> str:
    return f"""# AI Rail 3-minute demo

AI Rail is a local-first workflow rail and portable project brain for solo developers using AI coding assistants.

## 1. Install AI Rail

```bash
pipx install ai-rail
rail --version
```

Expected:

```text
AI Rail {VERSION}
```

## 2. Try the bundled TODO demo

```bash
cd examples/demo-todo
rail init --stack node --project-name \"AI Rail Demo TODO\"
rail doctor
npm run check
```

## 3. Create a sample GitHub issue

```bash
gh issue create --title \"Add todo body validation\" --body-file issues/001-add-body-validation.md
```

## 4. Start the scoped AI loop

```bash
rail next --copy
```

Paste the copied prompt into Codex, Claude Code, Cursor, Aider, or another AI coding tool. The agent should implement only the active issue and should not commit.

## 5. Generate portable context for another AI session

```bash
rail snapshot
rail handoff --for chatgpt --include-review --include-checks --copy
```

Paste the handoff into a new AI chat. The new model should understand the project, current issue, branch, checks, changed files, and next safe action without you re-explaining everything.

## 6. Verify and ship

```bash
rail verify --copy
rail ship \"fix(api): add todo body validation\"
```

`rail ship` refuses unsafe commits by default when review/check state is missing or stale, or when dangerous/generated files are changed.

## 7. Export the project brain to AI tool files

```bash
rail export --dry-run
rail export
```

Generated files include:

```text
AGENTS.md
CLAUDE.md
AIDER.md
.cursor/rules/ai-rail.mdc
.github/copilot-instructions.md
```

## The point

You can move between ChatGPT, Codex, Claude, Cursor, Aider, and patch mode without re-explaining the project every time.
"""


def cmd_demo(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail demo")
    parser.add_argument("--copy", action="store_true", help="Copy the demo script to clipboard when possible.")
    parser.add_argument("--output", help="Write the demo script to a file.")
    ns = parser.parse_args(argv)

    text = render_demo_script()
    if ns.output:
        output = Path(ns.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(f"[rail] demo script written: {output}")
    else:
        print(text)

    if ns.copy:
        if copy_to_clipboard(text):
            print("[rail] demo script copied to clipboard")
        else:
            print("[rail] copy requested, but no supported clipboard command was found")
    return 0


def cmd_about(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail about")
    parser.parse_args(argv)
    print(render_about())
    return 0


def cmd_release_check(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail release-check")
    parser.add_argument("--json", action="store_true", help="Print machine-readable result.")
    ns = parser.parse_args(argv)

    required = [
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "pyproject.toml",
        "docs/QUICKSTART.md",
        "docs/COMMANDS.md",
        "docs/RELEASE.md",
        "examples/demo-todo/README.md",
        "examples/demo-todo/DEMO_SCRIPT.md",
    ]
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    for rel in required:
        add(f"required file: {rel}", (root() / rel).exists())

    pyproject = safe_read_text(root() / "pyproject.toml")
    add("pyproject version matches CLI", f'version = "{VERSION}"' in pyproject)
    add("pyproject exposes rail script", 'rail = "ai_rail.cli:main"' in pyproject)

    template_runtime = safe_read_text(root() / "src" / "ai_rail" / "template" / ".rail" / "rail.py")
    add("template runtime version matches CLI", f'VERSION = "{VERSION}"' in template_runtime)

    cli_source = safe_read_text(root() / "src" / "ai_rail" / "cli.py")
    try:
        compile(cli_source, "src/ai_rail/cli.py", "exec")
        add("cli.py compiles", True)
    except SyntaxError as exc:
        add("cli.py compiles", False, str(exc))

    missing_docs = [name for name in ["QUICKSTART.md", "COMMANDS.md", "RELEASE.md"] if not (root() / "docs" / name).exists()]
    add("public docs present", not missing_docs, ", ".join(missing_docs))

    ok = all(item["ok"] for item in checks)
    payload = {"ok": ok, "version": VERSION, "checks": checks}

    if ns.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"AI Rail release check for {VERSION}")
        for item in checks:
            mark = "OK" if item["ok"] else "FAIL"
            suffix = f" — {item['detail']}" if item.get("detail") else ""
            print(f"- {mark}: {item['name']}{suffix}")
        print("\nResult: " + ("ready for alpha packaging" if ok else "not ready"))
    return 0 if ok else 1

def cmd_doctor(argv: list[str]) -> int:
    if not local_py().exists():
        print("No .rail/rail.py found. Run: rail init", file=sys.stderr)
        return 1
    rc = delegate(["doctor", *argv])
    missing = []
    for name in ["CHATGPT.md", "CLAUDE.md", "CODEX.md", "THREE_MODELS.md", "AI_CONTRACT.md"]:
        if not (rail_dir() / name).exists():
            missing.append(f".rail/{name}")
    if missing:
        print("\n[rail] Missing AI contract files:")
        for item in missing:
            print(f"- {item}")
        return 1
    print("\n[rail] AI contract files: OK")
    return rc


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(f"AI Rail {VERSION}")
        print("Daily: init, resume, next, handoff, verify, ship, snapshot, export")
        print("Aliases: r, n, v, s, snap, h, hc, hg, hl, x, xd, xf, rc")
        print("Advanced: doctor, status, start, prompt, patch, review, checks, commit, issue-close, done, sync, log, report, ci-init, upgrade, about, demo, release-check")
        return 0
    if argv[0] in {"--version", "version"}:
        print(render_version(), end="")
        return 0

    argv = expand_alias(argv)
    cmd, rest = argv[0], argv[1:]
    if cmd == "init":
        return cmd_init(rest)
    if cmd == "upgrade":
        return cmd_upgrade(rest)
    if cmd == "doctor":
        return cmd_doctor(rest)
    if cmd in {"status", "active", "resume"}:
        return cmd_status(rest)
    if cmd == "next":
        return cmd_next(rest)
    if cmd == "verify":
        return cmd_verify(rest)
    if cmd == "ship":
        return cmd_ship(rest)
    if cmd == "snapshot":
        return cmd_snapshot(rest)
    if cmd == "handoff":
        return cmd_handoff(rest)
    if cmd == "export":
        return cmd_export(rest)
    if cmd == "demo":
        return cmd_demo(rest)
    if cmd == "about":
        return cmd_about(rest)
    if cmd == "release-check":
        return cmd_release_check(rest)
    if cmd == "start":
        return cmd_start(rest)
    if cmd == "prompt":
        return cmd_prompt(rest)
    if cmd == "patch":
        return cmd_patch(rest)
    if cmd == "done":
        return cmd_done(rest)
    if cmd == "log":
        return cmd_log(rest)
    if cmd == "report":
        return cmd_report(rest)
    if cmd == "ci-init":
        return cmd_ci_init(rest)

    # All unchanged advanced commands delegate to the local core.
    return delegate([cmd, *rest])


if __name__ == "__main__":
    raise SystemExit(main())
