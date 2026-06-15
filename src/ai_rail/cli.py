from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ai_rail.checks import (
    check_block_reason as checks_check_block_reason,
    checks_result as checks_result_impl,
    configured_check_commands as configured_check_commands_impl,
    refresh_review_and_check_artifacts as refresh_review_and_check_artifacts_impl,
    validate_verify_snapshot as validate_verify_snapshot_impl,
    verify_fingerprint as verify_fingerprint_impl,
    write_verify_snapshot as write_verify_snapshot_impl,
)
from ai_rail.brain import (
    EXPORT_BEGIN,
    EXPORT_END,
    EXPORT_TARGETS,
    BrainContext,
    cmd_export as brain_cmd_export,
    cmd_handoff as brain_cmd_handoff,
    cmd_snapshot as brain_cmd_snapshot,
    export_label_for_target as brain_export_label_for_target,
    export_path_for_target as brain_export_path_for_target,
    next_safe_action,
    render_export_context as brain_render_export_context,
    render_handoff as brain_render_handoff,
    render_project_brain as brain_render_project_brain,
    render_tool_export as brain_render_tool_export,
    target_instructions,
    write_managed_export as brain_write_managed_export,
)
from ai_rail.config import (
    apply_detected_init_config,
    can_update_stale_default_node_check,
    check_output_mentions_missing_npm_script,
    configured_repository,
    detect_checks,
    is_unconfigured_config_value,
    is_unconfigured_repository,
    missing_npm_check_recovery,
    npm_run_script,
    package_json_scripts,
    pyproject_data,
    suggested_node_check_replacement,
)
from ai_rail.git_ops import (
    artifact_is_fresh as git_artifact_is_fresh,
    branch_exists_locally as git_branch_exists_locally,
    branch_exists_remotely as git_branch_exists_remotely,
    changed_files as git_changed_files,
    current_branch as git_current_branch,
    git_diff_for_fingerprint as git_diff_for_fingerprint_impl,
    has_baseline_commit as git_has_baseline_commit,
    has_git_dir as git_has_git_dir,
    init_dirty_inspection as git_init_dirty_inspection,
    git_ref_exists as git_ref_exists_impl,
    git_safety_preflight as git_safety_preflight_impl,
    git_status_porcelain as git_status_porcelain_impl,
    git_state_blocks_new_work as git_state_blocks_new_work_impl,
    is_inside_work_tree as git_is_inside_work_tree,
    is_probably_text_file as git_is_probably_text_file,
    latest_change_mtime as git_latest_change_mtime,
    rail_runtime_tracked_on_branch as git_rail_runtime_tracked_on_branch,
    remote_url as git_remote_url,
    reviewed_untracked_text_contents as git_reviewed_untracked_text_contents,
    untracked_files as git_untracked_files,
)
from ai_rail.github_ops import (
    detect_default_branch_from_gh,
    detect_repo_from_gh,
    fetch_github_issues as fetch_github_issues_impl,
    gh_available,
    parse_github_remote_url,
)
from ai_rail.prompts import (
    render_phase_prompt as render_phase_prompt_text,
    render_plan_prompt as render_plan_prompt_text,
)
from ai_rail.roadmap import (
    LOCAL_ROADMAP_END,
    LOCAL_ROADMAP_START,
    RAIL_ROADMAP_END,
    RAIL_ROADMAP_START,
    RAIL_TASK_ID_PATTERN,
    REMOTE_MEMORY_END,
    REMOTE_MEMORY_START,
    active_phase_summary_from_text,
    ensure_strict_roadmap,
    extract_remote_memory,
    extract_strict_roadmap_blocks,
    implementation_issues,
    is_roadmap_mirror_issue,
    is_placeholder_project_memory,
    project_memory_template,
    roadmap_issue_from_open_issues,
    roadmap_task_id_mentions,
    validate_rail_roadmap,
)
from ai_rail.ship import ShipContext, run_ship
from ai_rail.support import (
    SupportContext,
    cmd_about as support_cmd_about,
    cmd_ci_init as support_cmd_ci_init,
    cmd_demo as support_cmd_demo,
    cmd_release_check as support_cmd_release_check,
    render_about as support_render_about,
    render_demo_script as support_render_demo_script,
    render_version as support_render_version,
)
from ai_rail.template_ops import (
    PRESERVED_TEMPLATE_DIRS,
    TEMPLATE_CONFIG,
    UPGRADE_PROTECTED_FILES,
    TemplateContext,
    backup_file as template_backup_file,
    cmd_init as template_cmd_init,
    cmd_upgrade as template_cmd_upgrade,
    install_template as template_install_template,
    is_relative_to_path,
    next_backup_path,
    print_install_summary,
)

VERSION = "0.1.0a17"
PROJECT_DESCRIPTION = "A local-first workflow rail and portable project brain for AI-assisted development."
AUTHOR_NAME = "Afshin Saberi"
PROJECT_REPOSITORY = "https://github.com/afshinsb/ai-rail"
AUTHOR_WEBSITE = "https://theafshin.com"
PROJECT_LICENSE = "Apache-2.0"
VALID_MODELS = {"codex", "patch", "ai-direct"}
COMMAND_ALIASES = {
    "r": ["resume"],
    "n": ["next", "--copy"],
    "p": ["plan", "--copy"],
    "ph": ["phase", "--copy"],
    "im": ["import"],
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
    "clear": ["clear-active"],
}
RAIL_ICONS = {
    "error": "\u274c",
    "warning": "\u26a0\ufe0f",
    "success": "\u2705",
    "info": "\u2139\ufe0f",
    "tip": "\U0001f4a1",
    "context": "\U0001f9ed",
}
RAIL_ICON_FALLBACKS = {
    "error": "Error:",
    "warning": "Warning:",
    "success": "OK:",
    "info": "Info:",
    "tip": "Tip:",
    "context": "Context:",
}


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


def verified_path() -> Path:
    return state() / "last-verify.json"


def review_path() -> Path:
    return state() / "last-review.md"


def agent_result_path() -> Path:
    return state() / "agent-result.md"


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


def stream_can_encode(text: str, stream: Any | None = None) -> bool:
    stream = sys.stdout if stream is None else stream
    encoding = getattr(stream, "encoding", None) or sys.getdefaultencoding() or "utf-8"
    try:
        text.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def rail_icon(kind: str) -> str:
    icon = RAIL_ICONS[kind]
    return icon if stream_can_encode(icon) else RAIL_ICON_FALLBACKS[kind]


def fallback_cli_text(text: str) -> str:
    for kind, icon in RAIL_ICONS.items():
        text = text.replace(icon, RAIL_ICON_FALLBACKS[kind])
    return text.replace("\u2192", "->")


def rail_print(text: str = "", *, file: Any | None = None) -> None:
    stream = sys.stdout if file is None else file
    try:
        print(text, file=stream)
    except UnicodeEncodeError:
        print(fallback_cli_text(text), file=stream)


def print_utf8_text(text: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print(text)


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


def support_context() -> SupportContext:
    return SupportContext(
        root=root,
        rail_dir=rail_dir,
        read_json=read_json,
        safe_read_text=safe_read_text,
        copy_to_clipboard=copy_to_clipboard,
        backup_file=backup_file,
        version=VERSION,
        project_description=PROJECT_DESCRIPTION,
        author_name=AUTHOR_NAME,
        project_repository=PROJECT_REPOSITORY,
        author_website=AUTHOR_WEBSITE,
        project_license=PROJECT_LICENSE,
    )


def render_version() -> str:
    return support_render_version(support_context())


def render_about() -> str:
    return support_render_about(support_context())


def detect_repo_from_tools() -> str | None:
    """Best-effort repository detection without trusting config.json placeholders.

    Prefer GitHub CLI when available, then fall back to the local git remote.
    """
    repo = detect_repo_from_gh(run)
    if repo:
        return repo
    if shutil.which("git"):
        inside = run(["git", "rev-parse", "--is-inside-work-tree"], timeout=5)
        result = run(["git", "remote", "get-url", "origin"], timeout=5)
        url = result.stdout.strip()
        if url:
            repo = parse_github_remote_url(url)
            if repo:
                return repo
        if inside.returncode == 0 and inside.stdout.strip() == "true":
            return None
    return None


def branch_exists_locally(branch: str) -> bool:
    return git_branch_exists_locally(branch, run)


def branch_exists_remotely(branch: str) -> bool:
    return git_branch_exists_remotely(branch, run)


def branch_exists(branch: Any) -> bool:
    if is_unconfigured_config_value(branch):
        return False
    value = str(branch)
    if shutil.which("git") and current_branch() == value:
        return True
    return branch_exists_locally(value) or branch_exists_remotely(value)


def detect_default_branch() -> str:
    branch = detect_default_branch_from_gh(run)
    if branch:
        return branch
    if shutil.which("git"):
        result = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], timeout=5)
        ref = result.stdout.strip()
        prefix = "refs/remotes/origin/"
        if result.returncode == 0 and ref.startswith(prefix):
            return ref.removeprefix(prefix)
        current = current_branch()
        if current in {"main", "master"}:
            return current
        if branch_exists_locally("master"):
            return "master"
        if branch_exists_locally("main"):
            return "main"
    return "main"


def configured_default_branch() -> str:
    value = cfg().get("default_branch")
    return str(value) if not is_unconfigured_config_value(value) else detect_default_branch()


def git_ref_exists(ref: str) -> bool:
    return git_ref_exists_impl(ref, run)


def rail_runtime_tracked_on_branch(branch: str) -> bool:
    return git_rail_runtime_tracked_on_branch(branch, run)


def detect_repo_from_git_remote() -> str | None:
    if not shutil.which("git"):
        return None
    url = git_remote_url("origin", run) or ""
    if not url:
        return None
    repo = parse_github_remote_url(url)
    if repo:
        return repo
    return url


def has_github_remote() -> bool:
    url = git_remote_url("origin", run)
    return bool(url and parse_github_remote_url(url))


def is_inside_work_tree() -> bool:
    return git_is_inside_work_tree(run)


def has_git_dir() -> bool:
    return git_has_git_dir(root())


def run_git_init_main() -> subprocess.CompletedProcess[str]:
    return run(["git", "init", "-b", "main"], timeout=30)


def has_baseline_commit() -> bool:
    return git_has_baseline_commit(run)


def planning_identity() -> tuple[str, str]:
    config = cfg()
    project_name = str(config.get("project_name") or root().name)
    repository = config.get("repository")
    if is_unconfigured_repository(repository):
        repository = detect_repo_from_git_remote() or "not configured"
    return project_name, str(repository)


def detected_repository_for_github() -> str | None:
    config = cfg()
    repository = config.get("repository")
    if not is_unconfigured_repository(repository):
        return str(repository)
    return detect_repo_from_git_remote()


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


def delegate(args: list[str], *, stream: bool = False, extra_env: dict[str, str] | None = None) -> int:
    if not local_py().exists():
        print("No .rail/rail.py found. Run: rail init", file=sys.stderr)
        return 1
    env = {**os.environ, **(extra_env or {})}
    if stream:
        proc = subprocess.Popen(
            [sys.executable, str(local_py()), *args],
            cwd=root(),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if proc.stdout is None:
            proc.kill()
            print("Failed to stream .rail/rail.py output.", file=sys.stderr)
            return 1
        for line in proc.stdout:
            print(rewrite_core_output(line), end="")
        return proc.wait(timeout=300)
    result = subprocess.run(
        [sys.executable, str(local_py()), *args],
        cwd=root(),
        env=env,
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


def template_context() -> TemplateContext:
    return TemplateContext(
        root=root,
        rail_dir=rail_dir,
        local_py=local_py,
        read_json=read_json,
        write_json=write_json,
        detect_repo_from_tools=detect_repo_from_tools,
        branch_exists=branch_exists,
        detect_default_branch=detect_default_branch,
        init_dirty_inspection=lambda default_branch: git_init_dirty_inspection(root(), default_branch, run),
        is_inside_work_tree=is_inside_work_tree,
        has_git_dir=has_git_dir,
        git_safety_preflight=git_safety_preflight,
        git_state_blocks_new_work=git_state_blocks_new_work,
        run_git_init=run_git_init_main,
        has_github_remote=has_github_remote,
        version=VERSION,
    )


def backup_file(path: Path) -> Path:
    return template_backup_file(path)


def install_template(
    src: Path,
    dst: Path,
    force: bool = False,
    preserve_existing_files: set[Path] | None = None,
) -> dict[str, Any]:
    return template_install_template(
        template_context(),
        src,
        dst,
        force=force,
        preserve_existing_files=preserve_existing_files,
    )


def cmd_init(argv: list[str]) -> int:
    return template_cmd_init(argv, template_context())


def cmd_upgrade(argv: list[str]) -> int:
    return template_cmd_upgrade(argv, template_context())


def detected_github_owner() -> str | None:
    if not gh_available():
        return None
    result = run(["gh", "api", "user", "--jq", ".login"], timeout=15)
    owner = result.stdout.strip()
    return owner if result.returncode == 0 and owner else None


def print_no_github_remote_guidance() -> None:
    rail_print(f"{rail_icon('warning')} No GitHub remote found.")
    rail_print(f"{rail_icon('context')} AI Rail can work locally, but GitHub issues/roadmap sync need a remote.")
    rail_print(f"{rail_icon('tip')} Recommended:")
    rail_print("gh repo create OWNER/PROJECT --private --source . --remote origin --push")
    rail_print("rail init --clean-default")
    rail_print(f"{rail_icon('tip')} Or let Rail create the GitHub repo:")
    rail_print("rail github-create --private")
    rail_print("rail github-create --public")


def cmd_github_create(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail github-create")
    visibility = parser.add_mutually_exclusive_group(required=True)
    visibility.add_argument("--private", action="store_true", help="Create a private GitHub repo.")
    visibility.add_argument("--public", action="store_true", help="Create a public GitHub repo.")
    parser.add_argument("--repo", help="Explicit OWNER/PROJECT repo name. Defaults to the gh user and folder name.")
    ns = parser.parse_args(argv)

    if not gh_available():
        rail_print(f"{rail_icon('error')} GitHub CLI `gh` is required for rail github-create.")
        rail_print(f"{rail_icon('tip')} Install and authenticate `gh`, then rerun this command.")
        return 1
    if not shutil.which("git"):
        rail_print(f"{rail_icon('error')} Git is required for rail github-create.")
        return 1
    if not is_inside_work_tree():
        rail_print(f"{rail_icon('error')} AI Rail needs a Git repository before creating a GitHub remote.")
        rail_print(f"{rail_icon('tip')} Run: git init -b main")
        return 1

    state = git_safety_preflight()
    if git_state_blocks_new_work(state):
        print_git_state_blocked("github-create", state)
        return 1

    existing_origin = git_remote_url("origin", run)
    if existing_origin:
        rail_print(f"{rail_icon('error')} origin already exists.")
        rail_print(f"{rail_icon('context')} Current origin: {existing_origin}")
        rail_print(f"{rail_icon('tip')} Remove or rename it yourself if you intentionally want a different GitHub remote.")
        return 1

    if not has_baseline_commit():
        rail_print(f"{rail_icon('error')} A baseline commit is required before creating a GitHub repo.")
        rail_print(f"{rail_icon('tip')} Recommended:")
        rail_print("git add -A")
        rail_print('git commit -m "chore: initialize ai rail workflow"')
        return 1

    repo = ns.repo
    if not repo:
        owner = detected_github_owner()
        if not owner:
            rail_print(f"{rail_icon('error')} Could not detect your GitHub owner from `gh`.")
            rail_print(f"{rail_icon('tip')} Rerun with: rail github-create --private --repo OWNER/PROJECT")
            return 1
        repo = f"{owner}/{root().name}"

    visibility_flag = "--public" if ns.public else "--private"
    branch = current_branch()
    create = run(["gh", "repo", "create", repo, visibility_flag, "--source", ".", "--remote", "origin", "--push"], timeout=120)
    if create.returncode != 0:
        rail_print(f"{rail_icon('error')} GitHub repo creation failed.")
        message = (create.stderr or create.stdout).strip()
        if message:
            rail_print(message)
        return create.returncode or 1

    repo_url = create.stdout.strip() or create.stderr.strip()
    if not repo_url:
        repo_url = git_remote_url("origin", run) or f"https://github.com/{repo}"
    rail_print(f"{rail_icon('success')} GitHub repo created and pushed from `{branch}`.")
    rail_print(f"{rail_icon('context')} Repo: {repo_url}")
    rail_print(f"{rail_icon('tip')} Next:")
    rail_print("rail init --clean-default")
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
    return checks_result_impl(checks_path())


def latest_change_mtime(paths: list[str]) -> float | None:
    return git_latest_change_mtime(root(), paths)


def artifact_is_fresh(path: Path, paths: list[str]) -> bool:
    return git_artifact_is_fresh(path, root(), paths)


def check_block_reason() -> str | None:
    return checks_check_block_reason(
        checks_path=checks_path(),
        changed_files_func=changed_files,
        artifact_is_fresh_func=artifact_is_fresh,
    )


def current_branch() -> str:
    return git_current_branch(run)


def changed_files() -> list[str]:
    return git_changed_files(run)


def untracked_files() -> list[str]:
    return git_untracked_files(run)


def is_probably_text_file(path: Path, max_bytes: int = 20000) -> bool:
    return git_is_probably_text_file(path, max_bytes)


def reviewed_untracked_text_contents(max_file_chars: int = 12000, max_total_chars: int = 50000) -> str:
    return git_reviewed_untracked_text_contents(root(), untracked_files(), max_file_chars, max_total_chars)


def clear_agent_result() -> None:
    agent_result_path().unlink(missing_ok=True)


def git_diff_for_fingerprint() -> str:
    return git_diff_for_fingerprint_impl(run)


def active_issue_number() -> Any:
    item = active()
    if not item:
        return None
    issue = item.get("issue", {})
    return issue.get("number")


def verify_fingerprint(check_commands: list[str]) -> str:
    return verify_fingerprint_impl(
        check_commands,
        active_issue_number=active_issue_number(),
        branch=current_branch(),
        changed_files=changed_files(),
        untracked_files=untracked_files(),
        git_diff=git_diff_for_fingerprint(),
        untracked_text=reviewed_untracked_text_contents(),
    )


def configured_check_commands(override: list[str] | None = None) -> list[str]:
    return configured_check_commands_impl(cfg(), override)


def write_verify_snapshot(check_commands: list[str], check_result: str) -> None:
    write_verify_snapshot_impl(
        verified_path(),
        check_commands=check_commands,
        check_result=check_result,
        active_issue_number=active_issue_number(),
        branch=current_branch(),
        changed_files=changed_files(),
        untracked_files=untracked_files(),
        fingerprint=verify_fingerprint(check_commands),
        created_at=utc_now(),
    )


def validate_verify_snapshot(*, check_commands: list[str]) -> tuple[bool, str]:
    snapshot = read_json(verified_path(), None)
    return validate_verify_snapshot_impl(
        snapshot,
        check_commands=check_commands,
        active_issue_number=active_issue_number(),
        branch=current_branch(),
        fingerprint=verify_fingerprint(check_commands),
    )


def refresh_review_and_check_artifacts() -> None:
    refresh_review_and_check_artifacts_impl(review_path(), checks_path())


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


def project_memory_has_placeholders() -> bool:
    path = rail_dir() / "PROJECT.md"
    return path.exists() and "CHANGE_ME" in safe_read_text(path)


def fetch_github_issues(repo: str, state_value: str, limit: int = 100) -> list[dict[str, Any]]:
    return fetch_github_issues_impl(repo, state_value, run, limit=limit)


def active_phase_summary() -> dict[str, Any] | None:
    path = rail_dir() / "PROJECT.md"
    if not path.exists() or not path.is_file():
        return None
    return active_phase_summary_from_text(path.read_text(encoding="utf-8", errors="replace"))


def print_no_open_issue_phase_guidance() -> bool:
    summary = active_phase_summary()
    if not summary or not summary.get("next_task"):
        rail_print(f"{rail_icon('error')} No open implementation issues found.")
        rail_print(f"{rail_icon('tip')} Recommended next action: rail phase --copy \u2192 rail import \u2192 rail n")
        return False
    next_task = summary["next_task"]
    rail_print(f"{rail_icon('error')} No open implementation issues found.")
    rail_print(f"{rail_icon('info')} Active phase: {summary['heading']}")
    rail_print(f"{rail_icon('info')} Progress: {summary['completed']}/{summary['total']} tasks complete")
    rail_print(f"{rail_icon('info')} Next roadmap task: {next_task['task_id']} - {next_task['title']}")
    rail_print(f"{rail_icon('tip')} Recommended next action: rail phase --copy \u2192 rail import \u2192 rail n")
    rail_print("")
    rail_print("Why: GitHub has no open implementation issues, but PROJECT.md still has unchecked TBD tasks.")
    return True


def print_ship_phase_progress() -> None:
    summary = active_phase_summary()
    if not summary:
        return
    rail_print(f"{rail_icon('info')} Active phase: {summary['heading']}")
    rail_print(f"{rail_icon('info')} Progress: {summary['completed']}/{summary['total']} tasks complete")
    next_task = summary.get("next_task")
    if next_task:
        rail_print(f"{rail_icon('info')} Next roadmap task: {next_task['task_id']} - {next_task['title']}")
    else:
        rail_print(f"{rail_icon('success')} Phase {summary['phase']} appears complete.")
        rail_print(f"{rail_icon('tip')} Recommended next action: rail phase --copy \u2192 rail import \u2192 rail n")


def backup_project_memory_before_replacement(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    backup = backup_file(path)
    backup_rel = str(backup.relative_to(root())).replace("\\", "/")
    print(f"[rail] Backed up .rail/PROJECT.md to {backup_rel}")


def update_local_project_memory(managed: str) -> None:
    path = rail_dir() / "PROJECT.md"
    managed, warnings = ensure_strict_roadmap(managed)
    for warning in warnings:
        print(f"[rail] Warning: {warning}")
    new_block = f"{LOCAL_ROADMAP_START}\n\n{managed.strip()}\n\n{LOCAL_ROADMAP_END}"
    if not path.exists():
        path.write_text(project_memory_template(managed), encoding="utf-8")
        return
    existing = path.read_text(encoding="utf-8", errors="replace")
    if is_placeholder_project_memory(existing) or ("CHANGE_ME:" in existing and "## Roadmap maintenance rules" in existing and RAIL_ROADMAP_START in existing):
        backup_project_memory_before_replacement(path)
        path.write_text(project_memory_template(managed), encoding="utf-8")
        return
    if LOCAL_ROADMAP_START in existing and LOCAL_ROADMAP_END in existing:
        before = existing.split(LOCAL_ROADMAP_START, 1)[0].rstrip()
        after = existing.split(LOCAL_ROADMAP_END, 1)[1].lstrip()
        path.write_text(f"{before}\n\n{new_block}\n\n{after}", encoding="utf-8")
        return
    path.write_text(existing.rstrip() + "\n\n" + new_block + "\n", encoding="utf-8")


def print_no_matching_roadmap_task(issue_number: Any) -> None:
    rail_print(f"{rail_icon('warning')} No matching roadmap task found for issue #{issue_number}.")
    rail_print(f"{rail_icon('info')} PROJECT.md was left unchanged.")


def mark_project_issue_completed(issue_number: Any, title: str | None = None, body: str | None = None) -> bool:
    path = rail_dir() / "PROJECT.md"
    if not path.exists() or issue_number in {None, ""}:
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    num = str(issue_number)
    blocks = extract_strict_roadmap_blocks(text)
    if len(blocks) != 1:
        print_no_matching_roadmap_task(num)
        return False
    block = blocks[0]
    block_start = text.find(block)
    task_pattern = re.compile(
        rf"(?m)^(?P<prefix>[ \t]*- \[)(?P<status>[ x])(?P<suffix>\] (?:(?P<issue_first>#\d+|TBD) \| (?P<task_id_legacy>{RAIL_TASK_ID_PATTERN})|(?P<task_id_first>{RAIL_TASK_ID_PATTERN}) \| (?P<issue_second>#\d+|TBD)) \| (?P<title>.+))$"
    )
    tasks: list[dict[str, Any]] = []
    for match in task_pattern.finditer(block):
        task_id = match.group("task_id_first") or match.group("task_id_legacy")
        issue = match.group("issue_second") or match.group("issue_first")
        tasks.append(
            {
                "match": match,
                "task_id": task_id,
                "issue": issue,
                "status": match.group("status"),
                "title": match.group("title"),
            }
        )

    candidates = [task for task in tasks if task["issue"] == f"#{num}"]
    if not candidates:
        mentioned_ids = roadmap_task_id_mentions(title, body)
        candidates = [task for task in tasks if task["task_id"] in mentioned_ids]
    if len(candidates) != 1:
        print_no_matching_roadmap_task(num)
        return False
    task = candidates[0]
    if task["status"] == "x":
        return False

    status_start = block_start + task["match"].start("status")
    updated = text[:status_start] + "x" + text[status_start + 1:]
    path.write_text(updated, encoding="utf-8")
    return True


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
    parser.add_argument("issue_ref", nargs="?", default="next", help="Issue number, next, or latest. Also accepts lastest as a backward-compatible typo alias. Default: next.")
    parser.add_argument("--model", choices=sorted(VALID_MODELS), default="codex")
    parser.add_argument("--copy", action="store_true", help="Copy generated Codex prompt to clipboard when possible.")
    parser.add_argument("--no-prompt", action="store_true", help="Only start the issue; do not generate a prompt.")
    parser.add_argument("--no-branch", action="store_true")
    parser.add_argument("--reset-branch", action="store_true")
    parser.add_argument("--force", action="store_true")
    ns = parser.parse_args(argv)

    git_state = git_safety_preflight()
    if git_state.get("has_unresolved_conflicts"):
        print_git_state_blocked("next", git_state)
        print("Do not start a new task while .rail/PROJECT.md or code is conflicted.")
        return 1

    if project_memory_has_placeholders():
        print("[rail] Project memory has placeholders. Run `rail import` after planning.")

    active_issue = active()
    if active_issue and not ns.force:
        issue = active_issue.get("issue", {})
        number = issue.get("number")
        print(f"[rail] Issue #{number} is already active. Reusing active issue prompt.")
        clear_agent_result()
        if ns.no_prompt:
            return 0
        model = active_model() or ns.model
        if model == "codex":
            prompt_args = ["codex"]
            append_flag(prompt_args, ns.copy, "--copy")
            return cmd_prompt(prompt_args)
        if model == "patch":
            print("\n[rail] Patch model selected.")
            print("Next: ask ChatGPT for a small .patch file, then run `rail patch PATCH_FILE`.")
            return 0
        print("\n[rail] AI-direct model selected.")
        print("Next: use the external AI/GitHub workflow, then fetch or pull locally.")
        return 0

    start_args = [ns.issue_ref, "--model", ns.model]
    append_flag(start_args, ns.no_branch, "--no-branch")
    append_flag(start_args, ns.reset_branch, "--reset-branch")
    append_flag(start_args, ns.force, "--force")

    rc = cmd_start(start_args)
    if rc != 0:
        if ns.issue_ref == "next":
            print_no_open_issue_phase_guidance()
        return rc
    clear_agent_result()
    if ns.no_prompt:
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


def cmd_import(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail import")
    parser.parse_args(argv)

    git_state = git_safety_preflight()
    if git_state_blocks_new_work(git_state):
        print_git_state_blocked("import", git_state)
        print("Resolve or abort the merge before importing.")
        return 1

    if not rail_dir().exists():
        print("No .rail folder found. Run: rail init", file=sys.stderr)
        return 1
    if not gh_available():
        print("GitHub CLI `gh` is required for rail import.", file=sys.stderr)
        return 1
    repo = detected_repository_for_github()
    if not repo:
        print("Could not detect GitHub repository. Set .rail/config.json repository or git remote origin.", file=sys.stderr)
        return 1

    try:
        open_issues = fetch_github_issues(repo, "open")
        project_name = str(cfg().get("project_name") or root().name)
        roadmap, multiple = roadmap_issue_from_open_issues(open_issues, expected_project_name=project_name)
        if not roadmap:
            closed_issues = fetch_github_issues(repo, "closed")
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
        closed_issues = fetch_github_issues(repo, "closed")
        remote_block = extract_remote_memory(str(roadmap.get("body") or ""))
        if remote_block is None:
            print("Import failed: roadmap issue has no managed AI Rail project memory block.", file=sys.stderr)
            print(f"Update the GitHub roadmap issue with exactly one valid strict {RAIL_ROADMAP_START} / {RAIL_ROADMAP_END} block, then run rail import again.", file=sys.stderr)
            return 1
        strict_blocks = extract_strict_roadmap_blocks(remote_block)
        if len(strict_blocks) != 1:
            count = "no" if not strict_blocks else f"{len(strict_blocks)}"
            print(f"Import failed: managed roadmap memory contains {count} strict AI RAIL ROADMAP blocks; expected exactly one.", file=sys.stderr)
            print(f"Update the GitHub roadmap issue with exactly one valid strict {RAIL_ROADMAP_START} / {RAIL_ROADMAP_END} block, then run rail import again.", file=sys.stderr)
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
    verified_snapshot_commands: list[str] | None = None
    if not ns.no_checks:
        checks_args = ["--timeout", str(ns.timeout), *ns.run_commands]
        checks_rc = delegate(["checks", *checks_args], stream=True)
        if review_rc == 0 and checks_rc == 0:
            verified_snapshot_commands = configured_check_commands(ns.run_commands)

    prompt_args = ["review"]
    append_flag(prompt_args, ns.copy, "--copy")
    prompt_rc = cmd_prompt(prompt_args)
    if verified_snapshot_commands is not None and prompt_rc == 0:
        write_verify_snapshot(verified_snapshot_commands, checks_result())
        print("[rail] Verified snapshot saved.")

    return checks_rc or review_rc or prompt_rc


def cmd_ship(argv: list[str]) -> int:
    """Commit the issue branch, merge it to the default branch, then close.

    Safety checks are enforced by the underlying commit command. Closing the
    GitHub issue and clearing active state happen only after default-branch
    integration succeeds unless --no-merge is explicitly requested.
    """
    parser = argparse.ArgumentParser(prog="rail ship")
    parser.add_argument("message", help="Commit message.")
    parser.add_argument("--no-push", action="store_true", help="Commit but do not push; ship pauses before issue-close/done.")
    parser.add_argument("--amend", action="store_true", help="Amend previous commit.")
    parser.add_argument("--force", action="store_true", help="Pass --force to commit/done where applicable.")
    parser.add_argument("--allow-missing-checks", action="store_true", help="Allow ship when checks are missing/unknown.")
    parser.add_argument("--allow-stale", action="store_true", help="Allow ship when checks are older than changed files.")
    parser.add_argument("--recheck", action="store_true", help="Rerun checks even when the last verify snapshot is fresh.")
    parser.add_argument("--no-close", action="store_true", help="Do not close the active GitHub issue.")
    parser.add_argument("--no-done", action="store_true", help="Do not clear the active AI Rail state.")
    parser.add_argument("--no-sync", action="store_true", help="Pause after committing; do not integrate, close, or clear active state.")
    parser.add_argument("--no-merge", action="store_true", help="Advanced/manual: do not merge the issue branch into the default branch.")
    parser.add_argument("--keep-active", action="store_true", help="Keep active issue when running done.")
    ns = parser.parse_args(argv)
    return run_ship(ns, ShipContext(
        active=active,
        append_flag=append_flag,
        branch_exists_remotely=branch_exists_remotely,
        can_update_stale_default_node_check=can_update_stale_default_node_check,
        cfg=cfg,
        check_block_reason=check_block_reason,
        check_output_mentions_missing_npm_script=check_output_mentions_missing_npm_script,
        checks_path=checks_path,
        checks_result=checks_result,
        cmd_done=cmd_done,
        configured_check_commands=configured_check_commands,
        configured_default_branch=configured_default_branch,
        current_branch=current_branch,
        delegate=delegate,
        git_safety_preflight=git_safety_preflight,
        git_state_blocks_new_work=git_state_blocks_new_work,
        git_ref_exists=git_ref_exists,
        local_py=local_py,
        mark_project_issue_completed=mark_project_issue_completed,
        missing_npm_check_recovery=missing_npm_check_recovery,
        npm_run_script=npm_run_script,
        package_json_scripts=package_json_scripts,
        print_ship_phase_progress=print_ship_phase_progress,
        rail_dir=rail_dir,
        rail_icon=rail_icon,
        rail_print=rail_print,
        rail_runtime_tracked_on_branch=rail_runtime_tracked_on_branch,
        refresh_review_and_check_artifacts=refresh_review_and_check_artifacts,
        run=run,
        validate_verify_snapshot=validate_verify_snapshot,
        verified_path=verified_path,
        write_json=write_json,
        write_verify_snapshot=write_verify_snapshot,
    ))
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


def render_plan_prompt() -> str:
    project_name, repository = planning_identity()
    return render_plan_prompt_text(
        project_name=project_name,
        repository=repository,
        remote_memory_start=REMOTE_MEMORY_START,
        remote_memory_end=REMOTE_MEMORY_END,
        rail_roadmap_start=RAIL_ROADMAP_START,
        rail_roadmap_end=RAIL_ROADMAP_END,
    )


def render_phase_prompt() -> str:
    project_name, repository = planning_identity()
    history = "\n".join(recent_history_lines(8))
    return render_phase_prompt_text(
        project_name=project_name,
        repository=repository,
        history=history,
        remote_memory_start=REMOTE_MEMORY_START,
        remote_memory_end=REMOTE_MEMORY_END,
        rail_roadmap_start=RAIL_ROADMAP_START,
        rail_roadmap_end=RAIL_ROADMAP_END,
    )

def cmd_plan(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail plan")
    parser.add_argument("--copy", action="store_true", help="Copy planning prompt to clipboard when possible.")
    ns = parser.parse_args(argv)
    text = render_plan_prompt()
    print(text)
    if ns.copy:
        if copy_to_clipboard(text):
            print("\n[rail] planning prompt copied to clipboard")
        else:
            print("\n[rail] copy requested, but no supported clipboard command was found")
    return 0


def cmd_phase(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail phase")
    parser.add_argument("--copy", action="store_true", help="Copy phase-audit prompt to clipboard when possible.")
    ns = parser.parse_args(argv)
    text = render_phase_prompt()
    print(text)
    if ns.copy:
        if copy_to_clipboard(text):
            print("\n[rail] phase-audit prompt copied to clipboard")
        else:
            print("\n[rail] copy requested, but no supported clipboard command was found")
    return 0


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


def cmd_clear_active(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rail clear-active")
    parser.add_argument("--force", action="store_true", help="Clear local active state even with dirty worktree.")
    ns = parser.parse_args(argv)

    if not active():
        print("[rail] No active issue to clear.")
        return 0

    files = changed_files()
    if files and not ns.force:
        print(f"Warning: {len(files)} uncommitted file(s) still exist.")
        print("Did you forget to commit?")
        print("")
        for path in files:
            print(f"  {path}")
        print("")
        print("Run `rail clear-active --force` to clear local active state anyway.")
        return 1

    active_path().unlink(missing_ok=True)
    print("[rail] Cleared local active issue state.")
    print("[rail] GitHub issue was not closed.")
    print("[rail] Branch was not changed.")
    return 0


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
    return git_status_porcelain_impl(run)


def git_safety_preflight() -> dict[str, Any]:
    return git_safety_preflight_impl(root(), configured_default_branch(), run)


def git_state_blocks_new_work(state: dict[str, Any]) -> bool:
    return git_state_blocks_new_work_impl(state)


def print_git_state_blocked(action: str, state: dict[str, Any]) -> None:
    rail_print(f"{rail_icon('error')} rail {action} is blocked because Git has unresolved state.")
    if state.get("unmerged_files"):
        rail_print(f"{rail_icon('warning')} Unresolved files:")
        for item in state["unmerged_files"]:
            rail_print(f"- {item}")
    active_ops = []
    if state.get("merge_active"):
        active_ops.append("merge")
    if state.get("rebase_active"):
        active_ops.append("rebase")
    if state.get("cherry_pick_active"):
        active_ops.append("cherry-pick")
    if state.get("revert_active"):
        active_ops.append("revert")
    if active_ops:
        rail_print(f"{rail_icon('context')} Active Git operation: " + ", ".join(active_ops))
    rail_print(f"{rail_icon('tip')} Run: git status --short")
    rail_print("Resolve conflicts and commit the merge, or abort it before continuing.")
    rail_print("If this is a merge you do not want to finish, run: git merge --abort")


def print_default_branch_rail_tracking_warning(default_branch: str, current: str) -> None:
    rail_print(f"\n{rail_icon('warning')} .rail/ is not tracked on the default branch.")
    rail_print("Ship/sync may remove local Rail runtime files.")
    rail_print("Checkout or sync can remove the repo-local Rail runtime when `.rail/` only exists on this branch.")
    if current != default_branch:
        rail_print(f"{rail_icon('info')} Current branch: `{current}` | default branch: `{default_branch}`")
    rail_print(f"\n{rail_icon('tip')} If this branch is intentional:")
    rail_print("git add -A")
    rail_print('git commit -m "chore: initialize ai rail workflow"')
    rail_print(f"git push -u origin {current}")
    rail_print(f"\n{rail_icon('tip')} If setup should happen on the default branch:")
    rail_print(f"git switch {default_branch}")
    rail_print("git pull")
    rail_print("rail init --clean-default")


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


def brain_context() -> BrainContext:
    return BrainContext(
        active_issue_summary=active_issue_summary,
        brain_dir=brain_dir,
        cfg=cfg,
        changed_files=changed_files,
        checks_path=checks_path,
        checks_result=checks_result,
        configured_repository=lambda config: configured_repository(config, detect_repo_from_tools),
        copy_to_clipboard=copy_to_clipboard,
        current_branch=current_branch,
        git_status_porcelain=git_status_porcelain,
        handoff_state_path=handoff_state_path,
        next_backup_path=next_backup_path,
        rail_dir=rail_dir,
        recent_history_lines=recent_history_lines,
        review_path=review_path,
        root=root,
        safe_read_text=safe_read_text,
        print_text=print_utf8_text,
        utc_now=utc_now,
        version=VERSION,
    )


def render_project_brain(max_history: int = 5) -> dict[str, str]:
    return brain_render_project_brain(brain_context(), max_history=max_history)


def cmd_snapshot(argv: list[str]) -> int:
    return brain_cmd_snapshot(argv, brain_context())


def render_handoff(target: str, max_history: int = 5, include_review: bool = False, include_checks: bool = False, max_section_chars: int = 12000) -> str:
    return brain_render_handoff(
        brain_context(),
        target=target,
        max_history=max_history,
        include_review=include_review,
        include_checks=include_checks,
        max_section_chars=max_section_chars,
    )


def cmd_handoff(argv: list[str]) -> int:
    return brain_cmd_handoff(argv, brain_context())


def export_path_for_target(target: str) -> Path:
    return brain_export_path_for_target(root(), target)


def export_label_for_target(target: str) -> str:
    return brain_export_label_for_target(target)


def render_export_context(max_history: int = 5) -> str:
    return brain_render_export_context(brain_context(), max_history=max_history)


def render_tool_export(target: str, max_history: int = 5) -> str:
    return brain_render_tool_export(brain_context(), target, max_history=max_history)


def write_managed_export(path: Path, content: str, *, force: bool = False, dry_run: bool = False) -> tuple[bool, str]:
    return brain_write_managed_export(brain_context(), path, content, force=force, dry_run=dry_run)


def cmd_export(argv: list[str]) -> int:
    return brain_cmd_export(argv, brain_context())


def cmd_ci_init(argv: list[str]) -> int:
    return support_cmd_ci_init(argv, support_context())


def render_demo_script() -> str:
    return support_render_demo_script(support_context())


def cmd_demo(argv: list[str]) -> int:
    return support_cmd_demo(argv, support_context())


def cmd_about(argv: list[str]) -> int:
    return support_cmd_about(argv, support_context())


def cmd_release_check(argv: list[str]) -> int:
    return support_cmd_release_check(argv, support_context())


def cmd_doctor(argv: list[str]) -> int:
    if not local_py().exists():
        print("No .rail/rail.py found. Run: rail init", file=sys.stderr)
        if is_inside_work_tree() and not has_github_remote():
            print_no_github_remote_guidance()
        return 1
    rc = delegate(["doctor", *argv])
    missing = []
    for name in ["CHATGPT.md", "CLAUDE.md", "CODEX.md", "AIDER.md", "THREE_MODELS.md", "AI_CONTRACT.md"]:
        if not (rail_dir() / name).exists():
            missing.append(f".rail/{name}")
    if missing:
        print("\n[rail] Missing AI contract files:")
        for item in missing:
            print(f"- {item}")
        return 1
    print("\n[rail] AI contract files: OK")
    if project_memory_has_placeholders():
        print("[rail] Project memory has placeholders. Run `rail plan --copy`, paste it into a GitHub-connected planning AI, then run `rail import`.")
        repo = detected_repository_for_github()
        if repo and gh_available():
            try:
                open_issues = fetch_github_issues(repo, "open", limit=20)
                project_name = str(cfg().get("project_name") or root().name)
                roadmap, _multiple = roadmap_issue_from_open_issues(open_issues, expected_project_name=project_name)
                if roadmap:
                    print("[rail] Roadmap issue exists, but local project memory is not imported. Run: rail import")
                open_impl = implementation_issues(open_issues)
                if not open_impl:
                    print("[rail] No open implementation issues found. Run `rail phase --copy` to create the next execution slice.")
            except RuntimeError as exc:
                print(f"[rail] Warning: could not inspect roadmap issue: {exc}")
            except Exception:
                pass
    project_path = rail_dir() / "PROJECT.md"
    if project_path.exists():
        roadmap_issue_number = None
        repo = detected_repository_for_github()
        if repo and gh_available():
            try:
                open_issues = fetch_github_issues(repo, "open", limit=20)
                project_name = str(cfg().get("project_name") or root().name)
                roadmap, _multiple = roadmap_issue_from_open_issues(open_issues, expected_project_name=project_name)
                if roadmap:
                    roadmap_issue_number = roadmap.get("number")
            except Exception:
                pass
        roadmap_warnings = validate_rail_roadmap(project_path.read_text(encoding="utf-8", errors="replace"), roadmap_issue_number=roadmap_issue_number)
        if roadmap_warnings:
            print("\n[rail] PROJECT.md roadmap warnings:")
            for item in roadmap_warnings:
                print(f"- {item}")
    config = cfg()
    checks = config.get("checks") or []
    scripts = package_json_scripts()
    if config.get("default_branch") and not branch_exists(config.get("default_branch")):
        detected = detect_default_branch()
        print("\n[rail] Default branch configuration warning:")
        print(f"Configured default_branch `{config.get('default_branch')}` was not found.")
        print(f"Detected default branch: `{detected}`.")
        print("Recommended: rail init --refresh-config")
    if checks == ["npm run check"] and scripts and "check" not in scripts:
        replacement = suggested_node_check_replacement()
        print("\n[rail] Check configuration warning:")
        print("Configured check `npm run check` does not exist in package.json.")
        if replacement and replacement != "npm run check":
            print(f"Suggested replacement: `{replacement}`.")
            print(f"Run now with: rail checks --run \"{replacement}\"")
            print("Recommended: rail init --refresh-config")
    return rc


def main(argv: list[str] | None = None) -> int:
    try:
        argv = list(sys.argv[1:] if argv is None else argv)
        if not argv or argv[0] in {"-h", "--help"}:
            print(f"AI Rail {VERSION}")
            print("Daily: init, resume, plan, import, phase, next, handoff, verify, ship, snapshot, export")
            print("Aliases: r, n, p, ph, im, v, s, snap, h, hc, hg, hl, x, xd, xf, rc")
            print("Advanced: doctor, status, start, prompt, patch, review, checks, commit, issue-close, done, clear-active, sync, log, report, github-create, ci-init, upgrade, about, demo, release-check")
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
        if cmd == "github-create":
            return cmd_github_create(rest)
        if cmd in {"status", "active", "resume"}:
            return cmd_status(rest)
        if cmd == "next":
            return cmd_next(rest)
        if cmd == "plan":
            return cmd_plan(rest)
        if cmd == "import":
            return cmd_import(rest)
        if cmd == "phase":
            return cmd_phase(rest)
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
        if cmd == "clear-active":
            return cmd_clear_active(rest)
        if cmd == "log":
            return cmd_log(rest)
        if cmd == "report":
            return cmd_report(rest)
        if cmd == "ci-init":
            return cmd_ci_init(rest)
        if cmd == "checks":
            return delegate([cmd, *rest], stream=True)

        # All unchanged advanced commands delegate to the local core.
        return delegate([cmd, *rest])
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
