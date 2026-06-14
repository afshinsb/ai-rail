from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

UNCONFIGURED_REPOSITORY_VALUES = {None, "", "CHANGE_ME"}
UNCONFIGURED_CONFIG_VALUES = {None, "", "CHANGE_ME"}
NODE_CHECK_SCRIPT_PRIORITY = ["check", "lint", "typecheck", "test"]


def is_unconfigured_repository(value: Any) -> bool:
    return value in UNCONFIGURED_REPOSITORY_VALUES


def is_unconfigured_config_value(value: Any) -> bool:
    return value is None or value == "" or value == "CHANGE_ME"


def package_json_scripts(root_path: Path | None = None) -> dict[str, Any]:
    base = Path.cwd() if root_path is None else root_path
    package_path = base / "package.json"
    if not package_path.exists():
        return {}
    try:
        data = json.loads(package_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    scripts = data.get("scripts")
    return scripts if isinstance(scripts, dict) else {}


def package_json_name(root_path: Path | None = None) -> str | None:
    base = Path.cwd() if root_path is None else root_path
    package_path = base / "package.json"
    if not package_path.exists():
        return None
    try:
        data = json.loads(package_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    name = data.get("name")
    return str(name) if isinstance(name, str) and name.strip() else None


def pyproject_data(root_path: Path | None = None) -> dict[str, Any]:
    base = Path.cwd() if root_path is None else root_path
    path = base / "pyproject.toml"
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return {}


def pyproject_name(root_path: Path | None = None) -> str | None:
    project = pyproject_data(root_path).get("project")
    if not isinstance(project, dict):
        return None
    name = project.get("name")
    return str(name) if isinstance(name, str) and name.strip() else None


def detect_project_name(root_path: Path | None = None) -> str:
    base = Path.cwd() if root_path is None else root_path
    return package_json_name(base) or pyproject_name(base) or base.name


def detected_node_check_command(root_path: Path | None = None) -> str | None:
    scripts = package_json_scripts(root_path)
    for script in NODE_CHECK_SCRIPT_PRIORITY:
        if script in scripts:
            return f"npm run {script}"
    return None


def suggested_node_check_replacement(root_path: Path | None = None) -> str | None:
    return detected_node_check_command(root_path)


def npm_run_script(command: str) -> str | None:
    match = re.match(r"^\s*npm(?:\.cmd)?\s+(?:run|run-script)\s+([^\s]+)", command)
    if not match:
        return None
    return match.group(1).strip("\"'")


def check_output_mentions_missing_npm_script(output: str, script: str) -> bool:
    if not output:
        return False
    missing_script = re.search(r"Missing script:\s*[\"']?" + re.escape(script) + r"[\"']?", output, re.IGNORECASE)
    return bool(missing_script or re.search(r"npm\s+(?:error|ERR!)\s+Missing script", output, re.IGNORECASE))


def missing_npm_check_recovery(checks: list[Any], output: str, root_path: Path | None = None) -> tuple[str, str] | None:
    scripts = package_json_scripts(root_path)
    if not scripts:
        return None
    for command in checks:
        if not isinstance(command, str):
            continue
        script = npm_run_script(command)
        if not script:
            continue
        if script in scripts:
            continue
        if not check_output_mentions_missing_npm_script(output, script):
            continue
        replacement = detected_node_check_command(root_path)
        if replacement and replacement != command:
            return command, replacement
    return None


def can_update_stale_default_node_check(checks: list[Any], failed_command: str, replacement: str, root_path: Path | None = None) -> bool:
    failed_script = npm_run_script(failed_command)
    return (
        checks == ["npm run check"]
        and failed_command == "npm run check"
        and failed_script == "check"
        and replacement != failed_command
        and "check" not in package_json_scripts(root_path)
    )


def pytest_likely_configured(root_path: Path | None = None) -> bool:
    base = Path.cwd() if root_path is None else root_path
    if (base / "tests").is_dir():
        return True
    data = pyproject_data(base)
    tool = data.get("tool")
    return isinstance(tool, dict) and "pytest" in tool


def detect_checks(root_path: Path | None = None) -> list[str]:
    base = Path.cwd() if root_path is None else root_path
    if (base / "package.json").exists():
        command = detected_node_check_command(base)
        return [command] if command else []
    if (base / "pyproject.toml").exists() and pytest_likely_configured(base):
        return ["python -m pytest -q"]
    return []


def is_unconfigured_checks(value: Any, root_path: Path | None = None) -> bool:
    if is_unconfigured_config_value(value):
        return True
    if value == []:
        return True
    detected = detect_checks(root_path)
    default_checks = [
        ["npm run check"],
        detected,
    ]
    return isinstance(value, list) and value in default_checks


def npm_checks_missing_script(checks: Any, root_path: Path | None = None) -> bool:
    if not isinstance(checks, list):
        return True
    scripts = package_json_scripts(root_path)
    if not scripts:
        return False
    for command in checks:
        if not isinstance(command, str):
            continue
        script = npm_run_script(command)
        if script and script not in scripts:
            return True
    return False


def should_update_checks(value: Any, detected: list[str], *, first_config: bool, root_path: Path | None = None) -> bool:
    if first_config:
        return True
    if is_unconfigured_config_value(value):
        return True
    if value == []:
        return bool(detected)
    if npm_checks_missing_script(value, root_path) and detected:
        return True
    if value == ["npm run check"] and detected != value:
        return True
    return False


def configured_repository(config: dict[str, Any], detect_repo_func: Callable[[], str | None]) -> str:
    repository = config.get("repository")
    if is_unconfigured_repository(repository):
        return detect_repo_func() or "not configured"
    return str(repository)


def apply_detected_init_config(
    config: dict[str, Any],
    *,
    had_valid_config: bool,
    project_name_arg: str | None,
    detect_repo_func: Callable[[], str | None],
    branch_exists_func: Callable[[Any], bool],
    detect_default_branch_func: Callable[[], str],
    root_path: Path | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    changed: list[str] = []
    preserved: list[str] = []
    first_config = not had_valid_config

    detected_project = project_name_arg or detect_project_name(root_path)
    if first_config or is_unconfigured_config_value(config.get("project_name")):
        if config.get("project_name") != detected_project:
            changed.append("project_name")
        config["project_name"] = detected_project
    else:
        preserved.append("project_name")

    detected_repo = detect_repo_func()
    if is_unconfigured_repository(config.get("repository")):
        value = detected_repo or "CHANGE_ME"
        if config.get("repository") != value:
            changed.append("repository")
        config["repository"] = value
    else:
        preserved.append("repository")

    detected_branch = detect_default_branch_func()
    if branch_exists_func(config.get("default_branch")):
        preserved.append("default_branch")
    else:
        if config.get("default_branch") != detected_branch:
            changed.append("default_branch")
        config["default_branch"] = detected_branch

    detected = detect_checks(root_path)
    if should_update_checks(config.get("checks"), detected, first_config=first_config, root_path=root_path):
        if config.get("checks") != detected:
            changed.append("checks")
        config["checks"] = detected
    else:
        preserved.append("checks")

    return config, changed, preserved
