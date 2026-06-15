from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Callable

from ai_rail.config import apply_detected_init_config

PRESERVED_TEMPLATE_DIRS = {
    Path(".rail/state"),
    Path(".rail/reports"),
    Path(".rail/prompts"),
}
TEMPLATE_CONFIG = Path(".rail/config.json")
UPGRADE_PROTECTED_FILES = {
    Path(".rail/PROJECT.md"),
    Path(".rail/AGENTS.md"),
    Path(".rail/CLAUDE.md"),
    Path(".rail/AIDER.md"),
    Path(".rail/CHATGPT.md"),
    Path(".rail/CODEX.md"),
    Path(".rail/AI_CONTRACT.md"),
}


@dataclass
class TemplateContext:
    root: Callable[[], Path]
    rail_dir: Callable[[], Path]
    local_py: Callable[[], Path]
    read_json: Callable[[Path, Any], Any]
    write_json: Callable[[Path, Any], None]
    detect_repo_from_tools: Callable[[], str | None]
    branch_exists: Callable[[Any], bool]
    detect_default_branch: Callable[[], str]
    init_dirty_inspection: Callable[[str], dict[str, Any]]
    is_inside_work_tree: Callable[[], bool]
    has_git_dir: Callable[[], bool]
    git_safety_preflight: Callable[[], dict[str, Any]]
    git_state_blocks_new_work: Callable[[dict[str, Any]], bool]
    run_git_init: Callable[[], subprocess.CompletedProcess[str]]
    has_github_remote: Callable[[], bool]
    version: str


def is_relative_to_path(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def next_backup_path(path: Path) -> Path:
    i = 2
    first = path.with_name(f"{path.name}.rail.bak.1")
    if not first.exists():
        return first
    while True:
        candidate = path.with_name(f"{path.name}.rail.bak.{i}")
        if not candidate.exists():
            return candidate
        i += 1


def backup_file(path: Path) -> Path:
    backup = next_backup_path(path)
    shutil.copy2(path, backup)
    return backup


def install_template(
    ctx: TemplateContext,
    src: Path,
    dst: Path,
    force: bool = False,
    preserve_existing_files: set[Path] | None = None,
) -> dict[str, Any]:
    preserved_existing_dirs = {rel for rel in PRESERVED_TEMPLATE_DIRS if (dst / rel).exists()}
    protected_files = preserve_existing_files or set()
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "preserved_dirs": sorted(str(path).replace("\\", "/") for path in preserved_existing_dirs),
        "preserved_files": [],
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
        if rel in protected_files and target.exists():
            summary["skipped"] += 1
            summary["preserved_files"].append(str(rel).replace("\\", "/"))
            continue
        if rel == TEMPLATE_CONFIG and target.exists():
            try:
                ctx.read_json(target, {})
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
    if summary["preserved_files"]:
        print("- Preserved protected project/user files: " + ", ".join(summary["preserved_files"]))


INIT_ICONS = {
    "error": "❌",
    "warning": "⚠️",
    "success": "✅",
    "tip": "💡",
    "branch": "🧭",
}
INIT_ICON_FALLBACKS = {
    "error": "Error:",
    "warning": "Warning:",
    "success": "OK:",
    "tip": "Next:",
    "branch": "Branch:",
}


def stream_can_encode_text(text: str, stream: Any | None = None) -> bool:
    stream = sys.stdout if stream is None else stream
    encoding = getattr(stream, "encoding", None) or sys.getdefaultencoding() or "utf-8"
    try:
        text.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def init_icon(kind: str, stream: Any | None = None) -> str:
    icon = INIT_ICONS[kind]
    return icon if stream_can_encode_text(icon, stream) else INIT_ICON_FALLBACKS[kind]


def print_init_dirty_warning(inspection: dict[str, Any]) -> None:
    legacy = inspection.get("legacy_artifacts") or []
    print(f"{init_icon('warning')} AI Rail found existing repository work before init.")
    print(f"{init_icon('branch')} Current branch: {inspection.get('current_branch')} | default branch: {inspection.get('default_branch')}")
    if not inspection.get("on_default_branch"):
        print(f"{init_icon('warning')} You are not on the default branch.")
    print(f"- Dirty tracked files: {inspection.get('dirty_file_count', 0)}")
    print(f"- Deleted tracked files: {inspection.get('deleted_file_count', 0)}")
    print(f"- Untracked files/directories: {inspection.get('untracked_file_count', 0)}")
    print(f"- Existing .rail/: {'yes' if inspection.get('rail_exists') else 'no'}")
    print(f"- Legacy workflow artifacts: {', '.join(legacy) if legacy else 'none'}")
    print("")
    print("AI Rail can initialize here, but this repo state should be adopted or cleaned intentionally.")
    if legacy:
        print(f"{init_icon('warning')} Legacy workflow artifacts detected. If you are migrating to AI Rail, commit the deletion and `.rail/` addition together as a deliberate workflow migration.")


def print_init_git_next_commands(inspection: dict[str, Any], *, adopt: bool = False) -> None:
    current = inspection.get("current_branch") or "CURRENT_BRANCH"
    default = inspection.get("default_branch") or "DEFAULT_BRANCH"
    if adopt:
        print(f"\n{init_icon('success')} Treating the current dirty repository as the intended baseline.")
    print(f"\n{init_icon('tip')} Recommended Git commands:")
    if adopt:
        print('git add -A')
        print('git commit -m "chore: initialize ai rail workflow"')
        print('git push')
        return
    print("git status --short")
    print("git add -A")
    print('git commit -m "chore: initialize ai rail workflow"')
    if inspection.get("on_default_branch"):
        print("git push")
    else:
        print(f"git push -u origin {current}")
        print("")
        print(f"{init_icon('tip')} If Rail should be initialized on the default branch instead:")
        print(f"git switch {default}")
        print("git pull")
        print("rail init --clean-default")


def print_missing_git_repo_guidance() -> None:
    print(f"{init_icon('error')} AI Rail needs a Git repository.")
    print(f"{init_icon('branch')} Current folder is not inside a Git repo.")
    print(f"{init_icon('tip')} Local setup only:")
    print("rail init --git-init")
    print(f"{init_icon('branch')} Local setup = create local Git repo and initialize Rail. No GitHub repo.")
    print(f"{init_icon('tip')} Full setup:")
    print("rail bootstrap --private")
    print("rail bootstrap --public")
    print(f"{init_icon('branch')} Full setup = create local Git repo, commit baseline, initialize Rail, create GitHub repo, push.")
    print(f"{init_icon('tip')} Manual setup:")
    print("git init -b main")
    print("git add -A")
    print('git commit -m "chore: initial project baseline"')
    print("gh repo create OWNER/PROJECT --private --source . --remote origin --push")
    print("rail init --clean-default")


def print_missing_github_remote_guidance() -> None:
    print(f"{init_icon('warning')} No GitHub remote found.")
    print(f"{init_icon('branch')} AI Rail can work locally, but GitHub issues/roadmap sync need a remote.")
    print(f"{init_icon('tip')} Recommended:")
    print("gh repo create OWNER/PROJECT --private --source . --remote origin --push")
    print("rail init --clean-default")
    print(f"{init_icon('tip')} Or let Rail create the GitHub repo:")
    print("rail github-create --private")
    print("rail github-create --public")


def print_git_state_blocked(action: str, state: dict[str, Any]) -> None:
    print(f"{init_icon('error')} rail {action} is blocked because Git has unresolved state.")
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
        print(f"{init_icon('branch')} Active Git operation: {', '.join(active)}")
    if state.get("unmerged_files"):
        print(f"{init_icon('warning')} Unresolved files:")
        for item in state["unmerged_files"]:
            print(f"- {item}")
    print(f"{init_icon('tip')} Run: git status --short")
    print("Resolve conflicts and commit the merge, or abort it before continuing.")


BENIGN_INIT_UNTRACKED_FILES = {
    "README.md",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
}
RAIL_INIT_ROOT_FILES = {
    "Makefile",
}
LARGE_INIT_UNTRACKED_SET = 20


def init_has_installed_rail(ctx: TemplateContext) -> bool:
    return ctx.local_py().exists() and (ctx.rail_dir() / "config.json").exists()


def significant_init_untracked(inspection: dict[str, Any], *, existing_install: bool) -> list[str]:
    significant: list[str] = []
    for path in inspection.get("untracked_files") or []:
        normalized = str(path).replace("\\", "/").strip("/")
        if existing_install and (normalized == ".rail" or normalized.startswith(".rail/")):
            continue
        if existing_install and normalized in RAIL_INIT_ROOT_FILES:
            continue
        if normalized in BENIGN_INIT_UNTRACKED_FILES:
            continue
        significant.append(normalized)
    return sorted(significant)


def init_requires_dirty_flag(inspection: dict[str, Any], ctx: TemplateContext) -> bool:
    existing_install = init_has_installed_rail(ctx)
    significant_untracked = significant_init_untracked(inspection, existing_install=existing_install)
    if inspection.get("dirty_tracked_files") or inspection.get("deleted_tracked_files"):
        return True
    if inspection.get("legacy_artifacts"):
        return True
    if inspection.get("rail_exists") and not existing_install:
        return True
    if not inspection.get("on_default_branch") and (inspection.get("is_dirty") or inspection.get("rail_exists")):
        return True
    if len(significant_untracked) > LARGE_INIT_UNTRACKED_SET:
        return True
    return bool(significant_untracked)


def cmd_init(argv: list[str], ctx: TemplateContext) -> int:
    parser = argparse.ArgumentParser(prog="rail init")
    parser.add_argument("--stack", choices=["node", "python", "static"], default="node")
    parser.add_argument("--project-name")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--refresh-config", action="store_true", help="Re-detect safe config defaults without replacing state.")
    parser.add_argument("--allow-dirty", action="store_true", help="Initialize even when the working tree is dirty.")
    parser.add_argument("--adopt-dirty", action="store_true", help="Initialize and treat current dirty work as the intended baseline.")
    parser.add_argument("--clean-default", action="store_true", help="Refuse unless on the clean default branch.")
    parser.add_argument("--git-init", action="store_true", help="Create a local Git repo first when this folder is not already in one.")
    parser.add_argument("--quiet-next", action="store_true", help=argparse.SUPPRESS)
    ns = parser.parse_args(argv)

    if sum(bool(value) for value in [ns.allow_dirty, ns.adopt_dirty, ns.clean_default]) > 1:
        print(f"{init_icon('error', sys.stderr)} Choose only one of --allow-dirty, --adopt-dirty, or --clean-default.", file=sys.stderr)
        return 1

    if not shutil.which("git"):
        print(f"{init_icon('error')} Git is required for rail init.")
        return 1

    if not ctx.is_inside_work_tree():
        if ctx.has_git_dir():
            print(f"{init_icon('error')} AI Rail found Git metadata, but this is not a healthy Git work tree.")
            print(f"{init_icon('tip')} Run: git status --short")
            return 1
        if not ns.git_init:
            print_missing_git_repo_guidance()
            return 1
        result = ctx.run_git_init()
        if result.returncode != 0:
            print(f"{init_icon('error')} Could not create a local Git repo.")
            print(f"{init_icon('tip')} Try manually: git init -b main")
            return result.returncode or 1
        print(f"{init_icon('success')} Created local Git repo on branch main.")
    elif ns.git_init:
        state = ctx.git_safety_preflight()
        if ctx.git_state_blocks_new_work(state):
            print_git_state_blocked("init --git-init", state)
            return 1
        print(f"{init_icon('branch')} Git repo already exists; continuing with Rail initialization.")

    default_branch = ctx.detect_default_branch()
    inspection = ctx.init_dirty_inspection(default_branch)
    requires_dirty_flag = init_requires_dirty_flag(inspection, ctx)
    if ns.clean_default and (not inspection.get("on_default_branch") or inspection.get("is_dirty") or inspection.get("rail_exists")):
        print(f"{init_icon('error')} rail init --clean-default requires the current branch to be the clean default branch.")
        print_init_dirty_warning(inspection)
        return 1
    if requires_dirty_flag and not (ns.allow_dirty or ns.adopt_dirty or ns.force or ns.git_init):
        print_init_dirty_warning(inspection)
        print("")
        print(f"{init_icon('tip')} Run one of:")
        print("rail init --allow-dirty   # initialize without hiding existing work")
        print("rail init --adopt-dirty   # initialize and adopt this dirty state as the intended baseline")
        print("rail init --clean-default # initialize only from a clean default branch")
        return 1
    if inspection.get("is_dirty") or inspection.get("rail_exists") or inspection.get("legacy_artifacts"):
        print_init_dirty_warning(inspection)
        print("")

    cfg_path = ctx.rail_dir() / "config.json"
    had_config = cfg_path.exists()
    template_path = resources.files("ai_rail") / "template"
    summary = install_template(ctx, Path(str(template_path)), ctx.root(), force=ns.force)

    cfg = ctx.read_json(cfg_path, {})
    had_valid_config = had_config and summary["config"] == "preserved"
    cfg, config_updates, config_preserved = apply_detected_init_config(
        cfg,
        had_valid_config=had_valid_config,
        project_name_arg=ns.project_name,
        detect_repo_func=ctx.detect_repo_from_tools,
        branch_exists_func=ctx.branch_exists,
        detect_default_branch_func=ctx.detect_default_branch,
        root_path=ctx.root(),
    )

    summary["config_updates"] = config_updates
    if summary["config"] in {"created", "replaced"} or config_updates:
        ctx.write_json(cfg_path, cfg)

    try:
        ctx.local_py().chmod(ctx.local_py().stat().st_mode | 0o111)
    except Exception:
        pass

    print(f"Initialized AI Rail v{ctx.version} in {ctx.rail_dir()}")
    print(f"Project: {cfg.get('project_name')}")
    print(f"Repository: {cfg.get('repository')}")
    print(f"Default branch: {cfg.get('default_branch')}")
    checks = cfg.get("checks") or []
    print(f"Checks: {', '.join(checks) if checks else 'none detected'}")
    if config_preserved:
        print("Preserved config values: " + ", ".join(config_preserved))
    print_install_summary(summary)
    if not ns.quiet_next:
        print("\nNext:")
        print("rail doctor")
        print("rail status")
        if ns.allow_dirty or ns.adopt_dirty or ns.git_init:
            print_init_git_next_commands(inspection, adopt=ns.adopt_dirty or ns.git_init)
        if not ctx.has_github_remote():
            print("")
            print_missing_github_remote_guidance()
    return 0


def cmd_upgrade(argv: list[str], ctx: TemplateContext) -> int:
    parser = argparse.ArgumentParser(prog="rail upgrade")
    parser.add_argument("--refresh-config", action="store_true", help="Re-detect safe config defaults while upgrading.")
    ns = parser.parse_args(argv)

    if not ctx.rail_dir().exists():
        print("No .rail folder found. Run: rail init", file=sys.stderr)
        return 1

    cfg_path = ctx.rail_dir() / "config.json"
    had_config = cfg_path.exists()
    template_path = resources.files("ai_rail") / "template"
    summary = install_template(
        ctx,
        Path(str(template_path)),
        ctx.root(),
        force=True,
        preserve_existing_files=UPGRADE_PROTECTED_FILES,
    )

    config_preserved: list[str] = []
    if ns.refresh_config:
        cfg = ctx.read_json(cfg_path, {})
        had_valid_config = had_config and summary["config"] == "preserved"
        cfg, config_updates, config_preserved = apply_detected_init_config(
            cfg,
            had_valid_config=had_valid_config,
            project_name_arg=None,
            detect_repo_func=ctx.detect_repo_from_tools,
            branch_exists_func=ctx.branch_exists,
            detect_default_branch_func=ctx.detect_default_branch,
            root_path=ctx.root(),
        )
        summary["config_updates"] = config_updates
        if summary["config"] in {"created", "replaced"} or config_updates:
            ctx.write_json(cfg_path, cfg)

    try:
        ctx.local_py().chmod(ctx.local_py().stat().st_mode | 0o111)
    except Exception:
        pass

    print(f"Upgraded AI Rail local runtime/template files to v{ctx.version}.")
    if config_preserved:
        print("Preserved config values: " + ", ".join(config_preserved))
    print_install_summary(summary)
    return 0
