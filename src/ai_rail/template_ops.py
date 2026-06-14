from __future__ import annotations

import argparse
import json
import shutil
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


def cmd_init(argv: list[str], ctx: TemplateContext) -> int:
    parser = argparse.ArgumentParser(prog="rail init")
    parser.add_argument("--stack", choices=["node", "python", "static"], default="node")
    parser.add_argument("--project-name")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--refresh-config", action="store_true", help="Re-detect safe config defaults without replacing state.")
    ns = parser.parse_args(argv)

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
    print(f"Checks: {', '.join(checks) if checks else 'none'}")
    if config_preserved:
        print("Preserved config values: " + ", ".join(config_preserved))
    print_install_summary(summary)
    print("\nNext:")
    print("rail doctor")
    print("rail status")
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
