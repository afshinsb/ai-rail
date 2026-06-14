from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ai_rail", *args],
        cwd=cwd,
        env=ENV,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )


def git_init(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=path, check=True)


def git_current_branch(path: Path) -> str:
    result = subprocess.run(["git", "branch", "--show-current"], cwd=path, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def add_bare_origin(path: Path) -> Path:
    bare = path.parent / f"{path.name}-origin.git"
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=path, check=True)
    return bare


def init_static_repo_with_commit(path: Path) -> None:
    git_init(path)
    run_cli(path, "init", "--stack", "static")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True, text=True, check=True)


def write_active_issue(path: Path, number: int = 1, title: str = "Test issue") -> None:
    state = path / ".rail" / "state"
    state.mkdir(parents=True, exist_ok=True)
    active = {"issue": {"number": number, "title": title, "body": "", "url": ""}, "interaction_model": "codex"}
    (state / "active.json").write_text(json.dumps(active), encoding="utf-8")


def ship_without_remote(path: Path, message: str, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return run_cli(path, "ship", message, "--no-push", "--no-close", "--no-done", "--no-sync", *extra_args)


def install_fake_gh(path: Path, monkeypatch, *, open_issues: list[dict], closed_issues: list[dict] | None = None) -> None:
    fake_dir = path / "fake-bin"
    fake_dir.mkdir()
    script = fake_dir / "fake_gh.py"
    script.write_text(
        "import json, sys\n"
        f"open_issues = {json.dumps(open_issues)!r}\n"
        f"closed_issues = {json.dumps(closed_issues or [])!r}\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['issue', 'list']:\n"
        "    state = args[args.index('--state') + 1] if '--state' in args else 'open'\n"
        "    print(open_issues if state == 'open' else closed_issues)\n"
        "    raise SystemExit(0)\n"
        "if args[:2] == ['issue', 'close']:\n"
        "    print('Closed issue #' + args[2])\n"
        "    raise SystemExit(0)\n"
        "print('unsupported gh call: ' + ' '.join(args), file=sys.stderr)\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    shim = f"@echo off\r\n{sys.executable} \"{script}\" %*\r\n"
    (fake_dir / "gh.cmd").write_text(shim, encoding="utf-8")
    (fake_dir / "gh.bat").write_text(shim, encoding="utf-8")
    posix = fake_dir / "gh"
    posix.write_text(f"#!/usr/bin/env sh\nexec \"{sys.executable}\" \"{script}\" \"$@\"\n", encoding="utf-8")
    posix.chmod(0o755)
    path_keys = [key for key in ENV if key.lower() == "path"] or ["PATH"]
    existing_path = ENV.get(path_keys[0], "")
    for key in path_keys:
        monkeypatch.setitem(ENV, key, str(fake_dir) + os.pathsep + ENV.get(key, existing_path))
    monkeypatch.setitem(ENV, "PATH", str(fake_dir) + os.pathsep + ENV.get("PATH", existing_path))


def install_fake_npm(path: Path, monkeypatch) -> None:
    fake_dir = path / "fake-bin"
    fake_dir.mkdir(exist_ok=True)
    script = fake_dir / "fake_npm.py"
    script.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "if len(args) < 2 or args[0] not in {'run', 'run-script'}:\n"
        "    print('unsupported npm call: ' + ' '.join(args), file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
        "name = args[1]\n"
        "package = json.loads(Path('package.json').read_text(encoding='utf-8'))\n"
        "scripts = package.get('scripts') or {}\n"
        "if name not in scripts:\n"
        "    print(f'npm error Missing script: \"{name}\"', file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
        "Path('.rail/npm-runs.txt').open('a', encoding='utf-8').write(name + '\\n')\n"
        "body = scripts[name]\n"
        "if body == 'fail':\n"
        "    print(f'{name} failed', file=sys.stderr)\n"
        "    raise SystemExit(7)\n"
        "print(f'{name} passed')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    shim = f"@echo off\r\n{sys.executable} \"{script}\" %*\r\n"
    (fake_dir / "npm.cmd").write_text(shim, encoding="utf-8")
    (fake_dir / "npm.bat").write_text(shim, encoding="utf-8")
    posix = fake_dir / "npm"
    posix.write_text(f"#!/usr/bin/env sh\nexec \"{sys.executable}\" \"{script}\" \"$@\"\n", encoding="utf-8")
    posix.chmod(0o755)
    path_keys = [key for key in ENV if key.lower() == "path"] or ["PATH"]
    existing_path = ENV.get(path_keys[0], "")
    for key in path_keys:
        monkeypatch.setitem(ENV, key, str(fake_dir) + os.pathsep + ENV.get(key, existing_path))
    monkeypatch.setitem(ENV, "PATH", str(fake_dir) + os.pathsep + ENV.get("PATH", existing_path))


def test_init_creates_node_config_with_fallback_check(tmp_path: Path) -> None:
    git_init(tmp_path)
    result = run_cli(tmp_path, "init", "--stack", "node", "--project-name", "Demo")
    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["project_name"] == "Demo"
    assert cfg["checks"] == []
    assert (tmp_path / ".rail" / "CHATGPT.md").exists()
    assert (tmp_path / ".rail" / "AIDER.md").exists()


def test_init_node_chooses_typecheck_when_check_script_missing(tmp_path: Path) -> None:
    git_init(tmp_path)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"typecheck": "tsc --noEmit"}}), encoding="utf-8")

    result = run_cli(tmp_path, "init", "--stack", "node", "--project-name", "Demo")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["checks"] == ["npm run typecheck"]


def test_init_node_prefers_check_script(tmp_path: Path) -> None:
    git_init(tmp_path)
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"check": "eslint .", "typecheck": "tsc --noEmit"}}),
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "init", "--stack", "node", "--project-name", "Demo")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["checks"] == ["npm run check"]


def test_init_node_prefers_lint_before_typecheck(tmp_path: Path) -> None:
    git_init(tmp_path)
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"typecheck": "tsc --noEmit", "lint": "eslint ."}}),
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "init", "--stack", "node")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["checks"] == ["npm run lint"]


def test_init_detects_package_json_project_name(tmp_path: Path) -> None:
    git_init(tmp_path)
    (tmp_path / "package.json").write_text(json.dumps({"name": "package-demo", "scripts": {"test": "vitest"}}), encoding="utf-8")

    result = run_cli(tmp_path, "init")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["project_name"] == "package-demo"
    assert cfg["checks"] == ["npm run test"]


def test_init_detects_pyproject_name_and_pytest(tmp_path: Path) -> None:
    git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = \"python-demo\"\n\n[tool.pytest.ini_options]\n",
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "init")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["project_name"] == "python-demo"
    assert cfg["checks"] == ["python -m pytest -q"]


def test_init_rerun_updates_placeholder_project_name(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init").returncode == 0
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["project_name"] = "CHANGE_ME"
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    preserved = [
        tmp_path / ".rail" / "state" / "keep.txt",
        tmp_path / ".rail" / "reports" / "keep.txt",
        tmp_path / ".rail" / "prompts" / "keep.txt",
    ]
    for path in preserved:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep\n", encoding="utf-8")

    result = run_cli(tmp_path, "init", "--stack", "node", "--project-name", "Voxa")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["project_name"] == "Voxa"
    assert cfg["checks"] == []
    assert "Updated placeholder config values: project_name" in result.stdout
    for path in preserved:
        assert path.read_text(encoding="utf-8") == "keep\n"
    doctor = run_cli(tmp_path, "doctor")
    assert "project_name is still CHANGE_ME" not in doctor.stdout


def test_doctor_warns_when_configured_node_check_script_is_missing(tmp_path: Path) -> None:
    git_init(tmp_path)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"typecheck": "tsc --noEmit"}}), encoding="utf-8")
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = ["npm run check"]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    doctor = run_cli(tmp_path, "doctor")

    assert doctor.returncode == 0, doctor.stderr + doctor.stdout
    assert "Configured check `npm run check` does not exist in package.json." in doctor.stdout
    assert "Suggested replacement: `npm run typecheck`." in doctor.stdout
    assert "rail init --refresh-config" in doctor.stdout


def test_init_refresh_config_updates_missing_npm_check_script(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"typecheck": "tsc --noEmit"}}), encoding="utf-8")
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = ["npm run check"]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    result = run_cli(tmp_path, "init", "--refresh-config")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["checks"] == ["npm run typecheck"]
    assert "Updated placeholder config values: checks" in result.stdout


def test_init_detects_repository_from_git_origin(tmp_path: Path) -> None:
    git_init(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/project.git"], cwd=tmp_path, check=True)

    result = run_cli(tmp_path, "init")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["repository"] == "owner/project"


def test_doctor_warns_when_strict_roadmap_block_is_missing(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    (tmp_path / ".rail" / "PROJECT.md").write_text("# Notes\n\nLoose roadmap only.\n", encoding="utf-8")

    doctor = run_cli(tmp_path, "doctor")

    assert "PROJECT.md roadmap is not Rail-readable. Run rail phase --copy, then rail import." in doctor.stdout


def test_doctor_warns_on_malformed_roadmap_task_line(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    (tmp_path / ".rail" / "PROJECT.md").write_text("<!-- AI RAIL ROADMAP START -->\n\n## Phase P1 - Foundation\nStatus: active\n\n### Tasks\n- [ ] #2 Build thing\n\n<!-- AI RAIL ROADMAP END -->\n", encoding="utf-8")

    doctor = run_cli(tmp_path, "doctor")

    assert "malformed task line" in doctor.stdout


def test_doctor_warns_on_duplicate_roadmap_task_ids(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    (tmp_path / ".rail" / "PROJECT.md").write_text("<!-- AI RAIL ROADMAP START -->\n\n## Phase P1 - Foundation\nStatus: active\n\n### Tasks\n- [ ] #2 | P1-T01 | One\n- [ ] #3 | P1-T01 | Two\n\n<!-- AI RAIL ROADMAP END -->\n", encoding="utf-8")

    doctor = run_cli(tmp_path, "doctor")

    assert "duplicate task ID `P1-T01`" in doctor.stdout


def test_doctor_warns_on_duplicate_roadmap_issue_refs(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    (tmp_path / ".rail" / "PROJECT.md").write_text("<!-- AI RAIL ROADMAP START -->\n\n## Phase P1 - Foundation\nStatus: active\n\n### Tasks\n- [ ] #2 | P1-T01 | One\n- [ ] #2 | P1-T02 | Two\n\n<!-- AI RAIL ROADMAP END -->\n", encoding="utf-8")

    doctor = run_cli(tmp_path, "doctor")

    assert "duplicate issue ref `#2`" in doctor.stdout


def test_init_rerun_preserves_existing_project_name(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "node", "--project-name", "Keep Me").returncode == 0

    result = run_cli(tmp_path, "init", "--stack", "python", "--project-name", "Other")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["project_name"] == "Keep Me"
    assert "Updated placeholder config values: project_name" not in result.stdout


def test_init_rerun_preserves_user_customized_node_checks(tmp_path: Path) -> None:
    git_init(tmp_path)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"check": "eslint .", "typecheck": "tsc --noEmit"}}), encoding="utf-8")
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = ["npm run typecheck"]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    result = run_cli(tmp_path, "init", "--stack", "node")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["checks"] == ["npm run typecheck"]
    assert "Updated placeholder config values: checks" not in result.stdout


def test_init_force_preserves_existing_config(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "node", "--project-name", "Demo").returncode == 0
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg.update(
        {
            "project_name": "User Project",
            "repository": "owner/repo",
            "default_branch": "trunk",
            "checks": ["custom check"],
        }
    )
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    result = run_cli(tmp_path, "init", "--force", "--stack", "python", "--project-name", "Other")

    assert result.returncode == 0, result.stderr + result.stdout
    after = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert after["project_name"] == "User Project"
    assert after["repository"] == "owner/repo"
    assert after["default_branch"] in {"main", "master"}
    assert after["checks"] == ["custom check"]
    assert "Preserved .rail/config.json" in result.stdout


def test_init_force_preserves_state_reports_and_prompts(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    files = [
        tmp_path / ".rail" / "state" / "user-state.txt",
        tmp_path / ".rail" / "reports" / "user-report.txt",
        tmp_path / ".rail" / "prompts" / "user-prompt.txt",
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"keep {path.name}\n", encoding="utf-8")

    result = run_cli(tmp_path, "init", "--force")

    assert result.returncode == 0, result.stderr + result.stdout
    for path in files:
        assert path.read_text(encoding="utf-8") == f"keep {path.name}\n"


def test_init_force_backs_up_invalid_config_before_replacement(tmp_path: Path) -> None:
    git_init(tmp_path)
    rail = tmp_path / ".rail"
    rail.mkdir()
    cfg_path = rail / "config.json"
    cfg_path.write_text("{not valid json\n", encoding="utf-8")

    result = run_cli(tmp_path, "init", "--force", "--stack", "static")

    assert result.returncode == 0, result.stderr + result.stdout
    backup = rail / "config.json.rail.bak"
    assert backup.read_text(encoding="utf-8") == "{not valid json\n"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["checks"] == []
    assert "Backed up invalid .rail/config.json" in result.stdout


def test_init_rejects_removed_makefile_flag(tmp_path: Path) -> None:
    git_init(tmp_path)

    result = run_cli(tmp_path, "init", "--makefile")

    assert result.returncode == 2
    assert "unrecognized arguments: --makefile" in result.stderr


def test_doctor_before_init_tells_user_to_init(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "doctor")

    assert result.returncode == 1
    assert "No .rail/rail.py found. Run: rail init" in result.stderr


def test_upgrade_fails_before_init(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "upgrade")

    assert result.returncode == 1
    assert "No .rail folder found. Run: rail init" in result.stderr


def test_upgrade_updates_runtime_and_preserves_local_data(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    cfg_path = tmp_path / ".rail" / "config.json"
    original_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    original_cfg["project_name"] = "Keep Me"
    cfg_path.write_text(json.dumps(original_cfg, indent=2) + "\n", encoding="utf-8")
    rail_py = tmp_path / ".rail" / "rail.py"
    rail_py.write_text("# old runtime\n", encoding="utf-8")
    preserved = [
        tmp_path / ".rail" / "state" / "keep.txt",
        tmp_path / ".rail" / "reports" / "keep.txt",
        tmp_path / ".rail" / "prompts" / "keep.txt",
    ]
    for path in preserved:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep\n", encoding="utf-8")

    result = run_cli(tmp_path, "upgrade")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "old runtime" not in rail_py.read_text(encoding="utf-8")
    assert json.loads(cfg_path.read_text(encoding="utf-8")) == original_cfg
    for path in preserved:
        assert path.read_text(encoding="utf-8") == "keep\n"
    assert "Preserved .rail/config.json" in result.stdout


def test_upgrade_is_idempotent(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0

    first = run_cli(tmp_path, "upgrade")
    second = run_cli(tmp_path, "upgrade")

    assert first.returncode == 0, first.stderr + first.stdout
    assert second.returncode == 0, second.stderr + second.stdout
    assert "Upgraded AI Rail local runtime/template files" in second.stdout



def test_template_makefile_exposes_current_daily_workflow() -> None:
    text = (ROOT / "src" / "ai_rail" / "template" / "Makefile").read_text(encoding="utf-8")

    assert "$(r) next --copy" in text
    assert "$(r) verify --copy" in text
    assert '$(r) ship "$(M)"' in text
    assert "$(r) snapshot" in text
    assert "$(r) handoff --for generic --copy" in text
    assert "$(r) export" in text
    assert "$(r) export --dry-run" in text


def test_project_template_defines_local_project_memory() -> None:
    text = (ROOT / "src" / "ai_rail" / "template" / ".rail" / "PROJECT.md").read_text(encoding="utf-8")

    assert "# Project Memory" in text
    assert "local AI Rail project memory and roadmap brain" in text
    assert "AI RAIL MANAGED ROADMAP START" in text
    assert "AI RAIL ROADMAP START" in text
    assert "- [ ] TBD | P1-T01 |" in text
    assert "Status: active" in text
    assert "## Roadmap maintenance rules" in text
    assert "Do not create `.rail/ROADMAP.md`" in text


def test_user_docs_do_not_introduce_rail_roadmap_file() -> None:
    docs = [
        ROOT / "README.md",
        ROOT / "docs" / "QUICKSTART.md",
        ROOT / "docs" / "COMMANDS.md",
        ROOT / "docs" / "WORKFLOWS.md",
    ]

    for path in docs:
        assert ".rail/ROADMAP.md" not in path.read_text(encoding="utf-8")


def test_readme_documents_import_command_and_alias() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "| `rail import` | Import the GitHub roadmap issue into local `.rail/PROJECT.md` |" in text
    assert "`rail im` for `import`" in text


def test_quickstart_phase_audit_uses_import_not_direct_local_update() -> None:
    text = (ROOT / "docs" / "QUICKSTART.md").read_text(encoding="utf-8")

    assert "Phase audit asks the planning AI to update the GitHub roadmap issue" in text
    assert "rail import" in text
    assert "Phase audit updates `.rail/PROJECT.md`" not in text


def test_generated_demo_includes_import_after_plan() -> None:
    result = run_cli(ROOT, "demo")

    assert result.returncode == 0, result.stderr + result.stdout
    plan_pos = result.stdout.index("rail plan --copy")
    paste_pos = result.stdout.index("Paste the planning prompt", plan_pos)
    import_pos = result.stdout.index("rail import", paste_pos)
    assert plan_pos < paste_pos < import_pos


def test_roadmap_docs_describe_import_workflow_not_stale_a6_future() -> None:
    text = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")

    assert "0.1.0a11: Import-Based Roadmap Workflow" in text
    assert "`rail import` imports the GitHub roadmap issue into local `.rail/PROJECT.md`" in text
    assert "GitHub implementation issues are only the active execution queue" in text
    assert "Optional roadmap-to-issues helper" not in text


def test_architecture_mentions_plan_import_and_phase() -> None:
    text = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "roadmap workflow commands: `plan`, `import`, and `phase`" in text
    assert "`rail import` is a deterministic one-way import" in text


def test_detect_repo_falls_back_to_git_remote_when_gh_is_missing(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/project.git"], cwd=tmp_path, check=True)
    sys.path.insert(0, str(ROOT / "src"))
    import ai_rail.cli as cli

    real_which = cli.shutil.which

    def fake_which(name: str) -> str | None:
        if name == "gh":
            return None
        return real_which(name)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", fake_which)

    assert cli.detect_repo_from_tools() == "owner/project"


def test_detect_repo_returns_none_when_gh_missing_and_remote_unavailable(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    sys.path.insert(0, str(ROOT / "src"))
    import ai_rail.cli as cli

    real_which = cli.shutil.which

    def fake_which(name: str) -> str | None:
        if name == "gh":
            return None
        return real_which(name)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", fake_which)

    assert cli.detect_repo_from_tools() is None


def test_plan_prints_planning_prompt_without_active_issue(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static", "--project-name", "Road Demo")
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["repository"] = "owner/road-demo"
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    result = run_cli(tmp_path, "plan")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Project: Road Demo" in result.stdout
    assert "Repository: owner/road-demo" in result.stdout
    assert "`.rail/PROJECT.md`" in result.stdout
    assert "local project memory" in result.stdout
    assert "AI RAIL PROJECT MEMORY START" in result.stdout
    assert "run `rail import` locally" in result.stdout
    assert "Do not edit `.rail/PROJECT.md` remotely" in result.stdout
    assert "Do not include `CHANGE_ME`" in result.stdout
    assert "replace the old managed block instead of appending another one" in result.stdout
    assert "Do not duplicate default placeholder sections" in result.stdout
    assert "current state" in result.stdout
    assert "target state" in result.stdout
    assert "full phased roadmap" in result.stdout
    assert "AI RAIL ROADMAP START" in result.stdout
    assert "`- [ ] ISSUE | TASK_ID | TITLE`" in result.stdout
    assert "TBD | Pn-Txx | title" in result.stdout
    assert "next recommended issue/task" in result.stdout
    assert "phased" in result.stdout.lower()
    assert "Roadmap: Road Demo functional MVP" in result.stdout
    assert "usually 3-10 right-sized implementation issues" in result.stdout
    assert "do not create GitHub issues for the entire long-term roadmap" in result.stdout
    assert "## Goal" in result.stdout
    assert "## Current problem" in result.stdout
    assert "## Scope" in result.stdout
    assert "## Out of scope" in result.stdout
    assert "## Files likely touched" in result.stdout
    assert "## Acceptance checks" in result.stdout
    assert "## AI/Codex rules" in result.stdout
    assert "One issue should fit one focused coding-agent session" in result.stdout
    assert "tiny noisy micro-tasks" in result.stdout
    assert "huge phase-sized tasks" in result.stdout
    assert "Do not bundle unrelated UI, backend, docs, and config changes" in result.stdout
    assert "create a planning/audit issue first" in result.stdout
    assert ".rail/ROADMAP.md" not in result.stdout
    assert "rail n" in result.stdout
    assert "rail v" in result.stdout
    assert 'rail s "type(scope): message"' in result.stdout


def test_plan_copy_does_not_crash_without_active_issue(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "plan", "--copy")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "GitHub-connected planning agent" in result.stdout


def test_phase_prints_phase_audit_prompt_without_active_issue(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static", "--project-name", "Phase Demo")

    result = run_cli(tmp_path, "phase")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Roadmap: Phase Demo functional MVP" in result.stdout
    assert "phase-audit agent" in result.stdout
    assert "AI RAIL PROJECT MEMORY START" in result.stdout
    assert "run `rail import` locally" in result.stdout
    assert "Do not append duplicate managed blocks" in result.stdout
    assert "Do not include `CHANGE_ME`" in result.stdout
    assert "update completed work, current phase, next recommended issue" in result.stdout
    assert "mark completed task lines as `[x]` in the strict roadmap block" in result.stdout
    assert "Review upcoming phases" in result.stdout
    assert "off-track" in result.stdout
    assert "tell the user what changed and why" in result.stdout
    assert "do not edit `.rail/PROJECT.md` remotely" in result.stdout
    assert ".rail/ROADMAP.md" not in result.stdout
    assert "completed/closed issues" in result.stdout
    assert "remaining blockers" in result.stdout
    assert "next phase recommendation" in result.stdout
    assert "one focused coding session" in result.stdout
    assert "rail n -> coding agent -> rail v -> reviewer -> rail s" in result.stdout
    assert "AI RAIL ROADMAP START" in result.stdout
    assert "`- [ ] ISSUE | TASK_ID | TITLE`" in result.stdout
    assert "TBD | Pn-Txx | title" in result.stdout


def test_phase_copy_does_not_crash_without_active_issue(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "phase", "--copy")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "GitHub-connected phase-audit agent" in result.stdout


def test_import_fails_before_init(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "import")

    assert result.returncode == 1
    assert "No .rail folder found. Run: rail init" in result.stderr


def test_import_help_exists() -> None:
    result = run_cli(ROOT, "import", "--help")

    assert result.returncode == 0
    assert "usage: rail import" in result.stdout


def test_import_fails_without_detected_repo(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    install_fake_gh(tmp_path, monkeypatch, open_issues=[])

    result = run_cli(tmp_path, "import")

    assert result.returncode == 1
    assert "Could not detect GitHub repository" in result.stderr


def test_import_fails_without_roadmap_issue(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/project.git"], cwd=tmp_path, check=True)
    run_cli(tmp_path, "init", "--stack", "static")
    install_fake_gh(tmp_path, monkeypatch, open_issues=[{"number": 2, "title": "Build thing", "body": "", "updatedAt": "2026-01-01T00:00:00Z"}])

    result = run_cli(tmp_path, "import")

    assert result.returncode == 1
    assert "No open roadmap issue found. Run `rail plan --copy` first." in result.stderr


def test_import_extracts_managed_memory_and_writes_project(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/project.git"], cwd=tmp_path, check=True)
    run_cli(tmp_path, "init", "--stack", "static")
    body = "intro\n<!-- AI RAIL PROJECT MEMORY START -->\n## Roadmap\n\n- [ ] #2 Build thing\n<!-- AI RAIL PROJECT MEMORY END -->"
    install_fake_gh(
        tmp_path,
        monkeypatch,
        open_issues=[
            {"number": 1, "title": "Roadmap: Demo functional MVP", "body": body, "updatedAt": "2026-01-02T00:00:00Z"},
            {"number": 2, "title": "Build thing", "body": "", "updatedAt": "2026-01-01T00:00:00Z"},
        ],
        closed_issues=[{"number": 3, "title": "Done thing", "body": "", "updatedAt": "2026-01-01T00:00:00Z"}],
    )

    result = run_cli(tmp_path, "import")

    assert result.returncode == 0, result.stderr + result.stdout
    text = (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")
    assert "AI RAIL MANAGED ROADMAP START" in text
    assert "AI RAIL ROADMAP START" in text
    assert "## Roadmap" in text
    assert "- [ ] #2 Build thing" in text
    assert not (tmp_path / ".rail" / "ROADMAP.md").exists()
    assert "Open issues: 1" in result.stdout
    assert "Closed issues: 1" in result.stdout


def test_import_preserves_strict_roadmap_block(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/project.git"], cwd=tmp_path, check=True)
    run_cli(tmp_path, "init", "--stack", "static")
    strict = "<!-- AI RAIL ROADMAP START -->\n\n## Phase P1 - Foundation\nStatus: active\n\n### Goal\nShip safely.\n\n### Completion criteria\n- Done.\n\n### Tasks\n- [ ] #2 | P1-T01 | Build thing\n\n<!-- AI RAIL ROADMAP END -->"
    body = f"<!-- AI RAIL PROJECT MEMORY START -->\n## Notes\n\n{strict}\n<!-- AI RAIL PROJECT MEMORY END -->"
    install_fake_gh(tmp_path, monkeypatch, open_issues=[{"number": 1, "title": "Roadmap: Demo", "body": body, "updatedAt": "2026-01-01T00:00:00Z"}])

    result = run_cli(tmp_path, "import")

    assert result.returncode == 0, result.stderr + result.stdout
    text = (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")
    assert text.count("<!-- AI RAIL ROADMAP START -->") == 1
    assert strict in text


def test_import_does_not_duplicate_strict_roadmap_blocks(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/project.git"], cwd=tmp_path, check=True)
    run_cli(tmp_path, "init", "--stack", "static")
    strict = "<!-- AI RAIL ROADMAP START -->\n\n## Phase P1 - Foundation\nStatus: active\n\n### Goal\nShip safely.\n\n### Completion criteria\n- Done.\n\n### Tasks\n- [ ] #2 | P1-T01 | Build thing\n\n<!-- AI RAIL ROADMAP END -->"
    body = f"<!-- AI RAIL PROJECT MEMORY START -->\n{strict}\n\n{strict}\n<!-- AI RAIL PROJECT MEMORY END -->"
    install_fake_gh(tmp_path, monkeypatch, open_issues=[{"number": 1, "title": "Roadmap: Demo", "body": body, "updatedAt": "2026-01-01T00:00:00Z"}])

    result = run_cli(tmp_path, "import")

    assert result.returncode == 0, result.stderr + result.stdout
    text = (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")
    assert text.count("<!-- AI RAIL ROADMAP START -->") == 1


def test_import_replaces_default_project_placeholders(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/project.git"], cwd=tmp_path, check=True)
    run_cli(tmp_path, "init", "--stack", "static", "--project-name", "Clean Import")
    body = "<!-- AI RAIL PROJECT MEMORY START -->\n## Product summary\n\nReal app.\n\n## Stack\n\nPython.\n<!-- AI RAIL PROJECT MEMORY END -->"
    install_fake_gh(tmp_path, monkeypatch, open_issues=[{"number": 1, "title": "Roadmap: Clean", "body": body, "updatedAt": "2026-01-01T00:00:00Z"}])

    result = run_cli(tmp_path, "import")

    assert result.returncode == 0, result.stderr + result.stdout
    text = (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")
    assert "CHANGE_ME" not in text
    before_block = text.split("<!-- AI RAIL MANAGED ROADMAP START -->", 1)[0]
    assert "## Product notes" not in before_block
    assert "## Stack" not in before_block
    assert "## Non-negotiables" not in before_block
    doctor = run_cli(tmp_path, "doctor")
    assert "PROJECT.md contains CHANGE_ME placeholders" not in doctor.stdout


def test_import_preserves_user_content_outside_managed_markers(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/project.git"], cwd=tmp_path, check=True)
    run_cli(tmp_path, "init", "--stack", "static")
    project = tmp_path / ".rail" / "PROJECT.md"
    project.write_text("# Human notes\n\nkeep me\n\n<!-- AI RAIL MANAGED ROADMAP START -->\nold\n<!-- AI RAIL MANAGED ROADMAP END -->\n\nfooter\n", encoding="utf-8")
    body = "<!-- AI RAIL PROJECT MEMORY START -->\nnew roadmap\n<!-- AI RAIL PROJECT MEMORY END -->"
    install_fake_gh(tmp_path, monkeypatch, open_issues=[{"number": 1, "title": "Roadmap: Demo", "body": body, "updatedAt": "2026-01-01T00:00:00Z"}])

    result = run_cli(tmp_path, "import")

    assert result.returncode == 0, result.stderr + result.stdout
    text = project.read_text(encoding="utf-8")
    assert "keep me" in text
    assert "footer" in text
    assert "new roadmap" in text
    assert "old" not in text


def test_import_appends_managed_block_after_human_notes_without_markers(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:owner/project.git"], cwd=tmp_path, check=True)
    run_cli(tmp_path, "init", "--stack", "static")
    project = tmp_path / ".rail" / "PROJECT.md"
    project.write_text("# Human project notes\n\nThis app handles invoices.\n", encoding="utf-8")
    body = "<!-- AI RAIL PROJECT MEMORY START -->\n## Roadmap\n\n- [ ] #2 Build invoices\n<!-- AI RAIL PROJECT MEMORY END -->"
    install_fake_gh(tmp_path, monkeypatch, open_issues=[{"number": 1, "title": "Roadmap: Demo", "body": body, "updatedAt": "2026-01-01T00:00:00Z"}])

    result = run_cli(tmp_path, "import")

    assert result.returncode == 0, result.stderr + result.stdout
    text = project.read_text(encoding="utf-8")
    assert "This app handles invoices." in text
    assert "AI RAIL MANAGED ROADMAP START" in text
    assert "- [ ] #2 Build invoices" in text


def test_next_does_not_import_and_warns_on_placeholders(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    rail = tmp_path / ".rail" / "rail.py"
    rail.write_text(
        "import sys\n"
        "print('fake ' + sys.argv[1])\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    before = (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")

    result = run_cli(tmp_path, "next", "--no-prompt", "--no-branch")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Project memory has placeholders. Run `rail import` after planning." in result.stdout
    assert (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8") == before


def test_next_warns_when_no_open_implementation_issue(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    rail = tmp_path / ".rail" / "rail.py"
    rail.write_text(
        "import sys\n"
        "print('Error: No open implementation issues found.')\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "next", "--no-prompt", "--no-branch")

    assert result.returncode == 1
    assert "No open implementation issues found." in result.stdout
    assert "Recommended next action: rail phase --copy" in result.stdout


def test_next_no_open_issue_output_includes_active_phase_progress(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    rail = tmp_path / ".rail" / "rail.py"
    rail.write_text(
        "import sys\n"
        "print('Error: No open implementation issues found.')\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    (tmp_path / ".rail" / "PROJECT.md").write_text(
        "<!-- AI RAIL ROADMAP START -->\n\n"
        "## Phase P4 - Account/runtime foundation and workflow cleanup\n"
        "Status: active\n\n"
        "### Tasks\n"
        "- [x] P4-T01 | #1 | Done task\n"
        "- [ ] P4-T08 | TBD | Add production rate-limit and runtime storage boundary\n"
        "\n<!-- AI RAIL ROADMAP END -->\n",
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "next", "--no-prompt", "--no-branch")

    assert result.returncode == 1
    assert "❌ No open implementation issues found." in result.stdout
    assert "ℹ️ Active phase: P4 - Account/runtime foundation and workflow cleanup" in result.stdout
    assert "ℹ️ Progress: 1/2 tasks complete" in result.stdout
    assert "ℹ️ Next roadmap task: P4-T08 - Add production rate-limit and runtime storage boundary" in result.stdout
    assert "💡 Recommended next action: rail phase --copy → rail import → rail n" in result.stdout
    assert "Why: GitHub has no open implementation issues, but PROJECT.md still has unchecked TBD tasks." in result.stdout


def test_next_with_active_issue_reuses_prompt_without_starting_next(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    state = tmp_path / ".rail" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "active.json").write_text(
        json.dumps({"issue": {"number": 5, "title": "Keep going", "body": "Do work.", "url": ""}, "interaction_model": "codex"}),
        encoding="utf-8",
    )
    rail = tmp_path / ".rail" / "rail.py"
    rail.write_text(
        "import sys\n"
        "if sys.argv[1] == 'start':\n"
        "    print('start should not run')\n"
        "    raise SystemExit(9)\n"
        "if sys.argv[1:3] == ['prompt', 'codex']:\n"
        "    print('prompt reused')\n"
        "    raise SystemExit(0)\n"
        "print('unexpected ' + ' '.join(sys.argv[1:]))\n"
        "raise SystemExit(8)\n",
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "next", "--copy")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "[rail] Issue #5 is already active. Reusing active issue prompt." in result.stdout
    assert "prompt reused" in result.stdout
    assert "start should not run" not in result.stdout
    assert "No open implementation issues found." not in result.stdout


def test_clear_active_clears_only_local_active_state(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    write_active_issue(tmp_path, number=5, title="Reset local prompt")

    result = run_cli(tmp_path, "clear-active")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "[rail] Cleared local active issue state." in result.stdout
    assert "[rail] GitHub issue was not closed." in result.stdout
    assert "[rail] Branch was not changed." in result.stdout
    assert not (tmp_path / ".rail" / "state" / "active.json").exists()
    assert not (tmp_path / ".rail" / "state" / "history.jsonl").exists()


def test_clear_active_no_active_issue_is_noop(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "clear-active")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "[rail] No active issue to clear." in result.stdout


def test_clear_active_refuses_dirty_worktree_unless_forced(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    write_active_issue(tmp_path, number=5, title="Reset local prompt")
    changed = tmp_path / "changed.txt"
    changed.write_text("work in progress\n", encoding="utf-8")

    result = run_cli(tmp_path, "clear-active")

    assert result.returncode == 1
    assert "Warning: 1 uncommitted file(s) still exist." in result.stdout
    assert "changed.txt" in result.stdout
    assert "rail clear-active --force" in result.stdout
    assert (tmp_path / ".rail" / "state" / "active.json").exists()

    forced = run_cli(tmp_path, "clear-active", "--force")

    assert forced.returncode == 0, forced.stderr + forced.stdout
    assert "[rail] Cleared local active issue state." in forced.stdout
    assert not (tmp_path / ".rail" / "state" / "active.json").exists()


def test_ship_marks_project_task_complete(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir(parents=True)
    rail.write_text("import sys\nprint('fake ' + sys.argv[1])\nraise SystemExit(0)\n", encoding="utf-8")
    state = tmp_path / ".rail" / "state"
    state.mkdir()
    (state / "active.json").write_text(json.dumps({"issue": {"number": 2, "title": "Build thing", "body": "", "url": ""}, "interaction_model": "codex"}), encoding="utf-8")
    (tmp_path / ".rail" / "PROJECT.md").write_text("<!-- AI RAIL ROADMAP START -->\n\n## Phase P1 - Foundation\nStatus: active\n\n### Tasks\n- [ ] #2 | P1-T01 | Build thing\n\n<!-- AI RAIL ROADMAP END -->\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push", "--no-sync", "--no-merge")

    assert result.returncode == 0, result.stderr + result.stdout
    text = (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")
    assert "- [x] #2 | P1-T01 | Build thing" in text
    assert "Status: active" in text
    assert "Updated .rail/PROJECT.md for completed issue" in result.stdout


def test_ship_ignores_loose_project_roadmap_prose(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir(parents=True)
    rail.write_text("import sys\nprint('fake ' + sys.argv[1])\nraise SystemExit(0)\n", encoding="utf-8")
    state = tmp_path / ".rail" / "state"
    state.mkdir()
    (state / "active.json").write_text(json.dumps({"issue": {"number": 2, "title": "Build thing", "body": "", "url": ""}, "interaction_model": "codex"}), encoding="utf-8")
    project = tmp_path / ".rail" / "PROJECT.md"
    project.write_text("## Loose roadmap\n\n1. #2 - Build thing\n- [ ] #2 Build thing\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push", "--no-sync", "--no-merge")

    assert result.returncode == 0, result.stderr + result.stdout
    text = project.read_text(encoding="utf-8")
    assert "- [x] #2" not in text
    assert "No matching roadmap task found for issue #2." in result.stdout
    assert "PROJECT.md was left unchanged." in result.stdout
    assert "Updated .rail/PROJECT.md for completed issue" not in result.stdout


def test_phase_progress_parser_supports_task_id_first_roadmap_tasks() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from ai_rail import cli

    text = (
        "<!-- AI RAIL ROADMAP START -->\n\n"
        "## Phase P4 - Account/runtime foundation and workflow cleanup\n"
        "Status: active\n\n"
        "### Tasks\n"
        "- [x] P4-T01 | #1 | Done task\n"
        "- [ ] P4-T13 | TBD | Complete account/runtime checkpoint\n"
        "\n<!-- AI RAIL ROADMAP END -->\n"
    )

    summary = cli.active_phase_summary_from_text(text)

    assert summary is not None
    assert summary["heading"] == "P4 - Account/runtime foundation and workflow cleanup"
    assert summary["completed"] == 1
    assert summary["total"] == 2
    assert summary["next_task"]["task_id"] == "P4-T13"


def test_ship_marks_task_id_first_issue_line_complete(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir(parents=True)
    rail.write_text("import sys\nprint('fake ' + sys.argv[1])\nraise SystemExit(0)\n", encoding="utf-8")
    state = tmp_path / ".rail" / "state"
    state.mkdir()
    (state / "active.json").write_text(json.dumps({"issue": {"number": 15, "title": "Complete account/runtime checkpoint", "body": "", "url": ""}, "interaction_model": "codex"}), encoding="utf-8")
    project = tmp_path / ".rail" / "PROJECT.md"
    before = "<!-- AI RAIL ROADMAP START -->\n\n## Phase P4 - Runtime\nStatus: active\n\n### Tasks\n- [ ] P4-T13 | #15 | Complete account/runtime checkpoint\n\n<!-- AI RAIL ROADMAP END -->\n"
    project.write_text(before, encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push", "--no-sync", "--no-merge")

    assert result.returncode == 0, result.stderr + result.stdout
    after = project.read_text(encoding="utf-8")
    assert after == before.replace("- [ ] P4-T13", "- [x] P4-T13")


def test_ship_marks_task_id_first_tbd_line_when_active_issue_mentions_task_id(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir(parents=True)
    rail.write_text("import sys\nprint('fake ' + sys.argv[1])\nraise SystemExit(0)\n", encoding="utf-8")
    state = tmp_path / ".rail" / "state"
    state.mkdir()
    (state / "active.json").write_text(json.dumps({"issue": {"number": 15, "title": "P4-T13 Complete account/runtime checkpoint", "body": "", "url": ""}, "interaction_model": "codex"}), encoding="utf-8")
    project = tmp_path / ".rail" / "PROJECT.md"
    before = "# Human notes\n\nkeep\n\n<!-- AI RAIL ROADMAP START -->\n\n## Phase P4 - Runtime\nStatus: active\n\n### Tasks\n- [ ] P4-T12 | TBD | Other task\n- [ ] P4-T13 | TBD | Complete account/runtime checkpoint\n\n<!-- AI RAIL ROADMAP END -->\n\nfooter\n"
    project.write_text(before, encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push", "--no-sync", "--no-merge")

    assert result.returncode == 0, result.stderr + result.stdout
    after = project.read_text(encoding="utf-8")
    assert after == before.replace("- [ ] P4-T13", "- [x] P4-T13")


def test_ship_leaves_project_unchanged_when_no_safe_roadmap_match(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir(parents=True)
    rail.write_text("import sys\nprint('fake ' + sys.argv[1])\nraise SystemExit(0)\n", encoding="utf-8")
    state = tmp_path / ".rail" / "state"
    state.mkdir()
    (state / "active.json").write_text(json.dumps({"issue": {"number": 15, "title": "Unmatched task", "body": "", "url": ""}, "interaction_model": "codex"}), encoding="utf-8")
    project = tmp_path / ".rail" / "PROJECT.md"
    before = "<!-- AI RAIL ROADMAP START -->\n\n## Phase P4 - Runtime\nStatus: active\n\n### Tasks\n- [ ] P4-T13 | TBD | Complete account/runtime checkpoint\n\n<!-- AI RAIL ROADMAP END -->\n"
    project.write_text(before, encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push", "--no-sync", "--no-merge")

    assert result.returncode == 0, result.stderr + result.stdout
    assert project.read_text(encoding="utf-8") == before
    assert "No matching roadmap task found for issue #15." in result.stdout
    assert "PROJECT.md was left unchanged." in result.stdout


def test_ship_default_path_marks_project_before_commit_and_syncs(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir(parents=True)
    rail.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "cmd = sys.argv[1]\n"
        "Path('.rail/calls.txt').open('a', encoding='utf-8').write(cmd + '\\n')\n"
        "if cmd == 'commit' and '- [x] #2 | P1-T01 | Build thing' not in Path('.rail/PROJECT.md').read_text(encoding='utf-8'):\n"
        "    print('project not marked before commit')\n"
        "    raise SystemExit(2)\n"
        "print('fake ' + cmd)\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    state = tmp_path / ".rail" / "state"
    state.mkdir()
    (state / "active.json").write_text(json.dumps({"issue": {"number": 2, "title": "Build thing", "body": "", "url": ""}, "interaction_model": "codex"}), encoding="utf-8")
    (tmp_path / ".rail" / "PROJECT.md").write_text("<!-- AI RAIL ROADMAP START -->\n\n## Phase P1 - Foundation\nStatus: active\n\n### Tasks\n- [ ] #2 | P1-T01 | Build thing\n\n<!-- AI RAIL ROADMAP END -->\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push", "--no-merge")

    assert result.returncode == 0, result.stderr + result.stdout
    calls = (tmp_path / ".rail" / "calls.txt").read_text(encoding="utf-8").splitlines()
    assert calls == ["checks", "commit", "issue-close", "done", "sync"]
    assert calls.count("commit") == 1
    assert "- [x] #2 | P1-T01 | Build thing" in (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")


def test_ship_restores_project_memory_when_commit_fails(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir(parents=True)
    rail.write_text(
        "import sys\n"
        "print('fake ' + sys.argv[1])\n"
        "raise SystemExit(1 if sys.argv[1] == 'commit' else 0)\n",
        encoding="utf-8",
    )
    state = tmp_path / ".rail" / "state"
    state.mkdir()
    (state / "active.json").write_text(json.dumps({"issue": {"number": 2, "title": "Build thing", "body": "", "url": ""}, "interaction_model": "codex"}), encoding="utf-8")
    before = "## Completed work\n\n## Active execution queue\n\n- [ ] #2 Build thing\n"
    project = tmp_path / ".rail" / "PROJECT.md"
    project.write_text(before, encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push")

    assert result.returncode == 1
    assert project.read_text(encoding="utf-8") == before
    assert "- [x] #2" not in project.read_text(encoding="utf-8")
    assert "Restored .rail/PROJECT.md because ship commit failed." in result.stdout
    assert "Ship stopped during commit" in result.stdout


def test_ship_does_not_fail_if_project_update_fails(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir(parents=True)
    rail.write_text("import sys\nprint('fake ' + sys.argv[1])\nraise SystemExit(0)\n", encoding="utf-8")
    state = tmp_path / ".rail" / "state"
    state.mkdir()
    (state / "active.json").write_text(json.dumps({"issue": {"number": 2, "title": "Build thing", "body": "", "url": ""}, "interaction_model": "codex"}), encoding="utf-8")
    project = tmp_path / ".rail" / "PROJECT.md"
    project.mkdir()

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push", "--no-sync", "--no-merge")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Could not update .rail/PROJECT.md before ship" in result.stdout


def install_local_issue_close_runtime_wrapper(path: Path) -> None:
    rail = path / ".rail" / "rail.py"
    real = path / ".rail" / "rail_real.py"
    real.write_text(rail.read_text(encoding="utf-8"), encoding="utf-8")
    rail.write_text(
        "import subprocess, sys\n"
        "from pathlib import Path\n"
        "cmd = sys.argv[1] if len(sys.argv) > 1 else ''\n"
        "if cmd == 'issue-close':\n"
        "    print('Closed issue #1')\n"
        "    raise SystemExit(0)\n"
        "if cmd == 'done':\n"
        "    Path('.rail/state/active.json').unlink(missing_ok=True)\n"
        "    print('Done.')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(subprocess.run([sys.executable, '.rail/rail_real.py', *sys.argv[1:]]).returncode)\n",
        encoding="utf-8",
    )


def setup_tracked_rail_remote_repo(tmp_path: Path) -> tuple[str, Path]:
    git_init(tmp_path)
    result = run_cli(tmp_path, "init", "--stack", "static")
    assert result.returncode == 0, result.stderr + result.stdout
    install_local_issue_close_runtime_wrapper(tmp_path)
    default_branch = git_current_branch(tmp_path)
    bare = add_bare_origin(tmp_path)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init rail"], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "push", "-u", "origin", default_branch], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "checkout", "-b", "issue-1-work"], cwd=tmp_path, capture_output=True, text=True, check=True)
    write_active_issue(tmp_path, number=1, title="Ship work")
    return default_branch, bare


def test_ship_merges_issue_branch_to_default_before_closing(tmp_path: Path, monkeypatch) -> None:
    default_branch, bare = setup_tracked_rail_remote_repo(tmp_path)
    (tmp_path / "app.txt").write_text("issue work\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: integrate issue", "--force")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Integrating `issue-1-work`" in result.stdout
    assert "Closed issue #1" in result.stdout
    assert git_current_branch(tmp_path) == default_branch
    assert (tmp_path / ".rail" / "rail.py").exists()
    assert not (tmp_path / ".rail" / "state" / "active.json").exists()
    default_log = subprocess.run(["git", "log", "--oneline", default_branch], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: integrate issue" in default_log.stdout
    remote_log = subprocess.run(["git", f"--git-dir={bare}", "log", "--oneline", default_branch], capture_output=True, text=True, check=True)
    assert "test: integrate issue" in remote_log.stdout
    assert result.stdout.index("Integrating `issue-1-work`") < result.stdout.index("Closed issue #1")


def test_ship_does_not_close_or_clear_active_when_default_merge_fails(tmp_path: Path, monkeypatch) -> None:
    default_branch, bare = setup_tracked_rail_remote_repo(tmp_path)
    (tmp_path / "conflict.txt").write_text("issue side\n", encoding="utf-8")
    subprocess.run(["git", "add", "conflict.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "prepare issue conflict"], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "push", "-u", "origin", "issue-1-work"], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "checkout", default_branch], cwd=tmp_path, capture_output=True, text=True, check=True)
    (tmp_path / "conflict.txt").write_text("default side\n", encoding="utf-8")
    subprocess.run(["git", "add", "conflict.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "default conflict"], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "push", "origin", default_branch], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "checkout", "issue-1-work"], cwd=tmp_path, capture_output=True, text=True, check=True)
    (tmp_path / "app.txt").write_text("more issue work\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: conflict ship", "--force")

    assert result.returncode != 0
    assert "Ship paused: merge into default branch has conflicts." in result.stdout
    assert "Closed issue #1" not in result.stdout
    assert (tmp_path / ".rail" / "state" / "active.json").exists()
    remote_issue_log = subprocess.run(["git", f"--git-dir={bare}", "log", "--oneline", "issue-1-work"], capture_output=True, text=True, check=True)
    assert "test: conflict ship" in remote_issue_log.stdout


def test_ship_pauses_when_rail_runtime_not_tracked_on_default(tmp_path: Path, monkeypatch) -> None:
    git_init(tmp_path)
    default_branch = git_current_branch(tmp_path)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base without rail"], cwd=tmp_path, capture_output=True, text=True, check=True)
    add_bare_origin(tmp_path)
    subprocess.run(["git", "push", "-u", "origin", default_branch], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "checkout", "-b", "issue-1-work"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["default_branch"] = default_branch
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    install_fake_gh(tmp_path, monkeypatch, open_issues=[])
    write_active_issue(tmp_path, number=1, title="Unsafe rail checkout")
    (tmp_path / "app.txt").write_text("issue work\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: unsafe rail", "--force")

    assert result.returncode == 1
    assert "Ship paused: `.rail/` is not tracked on the default branch." in result.stdout
    assert "Closed issue #1" not in result.stdout
    assert (tmp_path / ".rail" / "state" / "active.json").exists()
    assert (tmp_path / ".rail" / "rail.py").exists()
    assert git_current_branch(tmp_path) == "issue-1-work"


def test_doctor_warns_when_rail_runtime_not_tracked_on_default(tmp_path: Path) -> None:
    git_init(tmp_path)
    default_branch = git_current_branch(tmp_path)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base without rail"], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "checkout", "-b", "issue-1-work"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert run_cli(tmp_path, "init", "--stack", "static").returncode == 0
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["default_branch"] = default_branch
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    result = run_cli(tmp_path, "doctor")

    assert result.returncode == 0, result.stderr + result.stdout
    assert ".rail/ is not tracked on the default branch" in result.stdout
    assert "Ship/sync may remove local Rail runtime files" in result.stdout


def test_ship_no_merge_keeps_branch_only_behavior_and_warns(tmp_path: Path, monkeypatch) -> None:
    default_branch, _bare = setup_tracked_rail_remote_repo(tmp_path)
    (tmp_path / "app.txt").write_text("branch only\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: branch only", "--force", "--no-merge", "--no-sync")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "did not integrate this issue branch into the default branch" in result.stdout
    assert "Branch-only ship path complete" in result.stdout
    assert "Closed issue #1" in result.stdout
    assert git_current_branch(tmp_path) == "issue-1-work"
    default_log = subprocess.run(["git", "log", "--oneline", default_branch], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: branch only" not in default_log.stdout


def test_ship_default_branch_missing_fails_before_issue_close(tmp_path: Path, monkeypatch) -> None:
    setup_tracked_rail_remote_repo(tmp_path)
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["default_branch"] = "missing-default"
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("issue work\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: missing default", "--force")

    assert result.returncode == 1
    assert "configured default branch `missing-default` was not found" in result.stdout
    assert "Closed issue #1" not in result.stdout
    assert (tmp_path / ".rail" / "state" / "active.json").exists()


def test_ship_preserves_rail_project_and_config_during_default_merge(tmp_path: Path, monkeypatch) -> None:
    setup_tracked_rail_remote_repo(tmp_path)
    before_project = (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")
    before_config = (tmp_path / ".rail" / "config.json").read_text(encoding="utf-8")
    (tmp_path / "app.txt").write_text("issue work\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: preserve rail files", "--force")

    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8") == before_project
    assert (tmp_path / ".rail" / "config.json").read_text(encoding="utf-8") == before_config
    assert (tmp_path / ".rail" / "rail.py").exists()


def test_rail_icon_preserves_emoji_when_stdout_can_encode(monkeypatch) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from ai_rail import cli

    class FakeStdout:
        encoding = "utf-8"

    monkeypatch.setattr(cli.sys, "stdout", FakeStdout())

    assert cli.rail_icon("warning") == "⚠️"


def test_rail_icon_falls_back_on_non_utf_stdout(monkeypatch) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from ai_rail import cli

    class FakeStdout:
        encoding = "cp1252"

    monkeypatch.setattr(cli.sys, "stdout", FakeStdout())

    assert cli.rail_icon("warning") == "Warning:"


def test_rail_print_falls_back_without_crashing_on_charmap_stdout(monkeypatch) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from ai_rail import cli

    class CharmapStdout:
        encoding = "cp1252"

        def __init__(self) -> None:
            self.lines: list[str] = []

        def write(self, text: str) -> int:
            text.encode(self.encoding)
            self.lines.append(text)
            return len(text)

        def flush(self) -> None:
            pass

    stream = CharmapStdout()
    monkeypatch.setattr(cli.sys, "stdout", stream)

    cli.rail_print("⚠️ Ship paused: test → next")

    assert "Warning: Ship paused: test -> next" in "".join(stream.lines)


def test_model_guard_codex_refuses_on_patch(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "node")
    active = {
        "interaction_model": "patch",
        "issue": {"number": 1, "title": "Patch task", "body": "", "url": ""},
    }
    state = tmp_path / ".rail" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "active.json").write_text(json.dumps(active), encoding="utf-8")
    result = run_cli(tmp_path, "prompt", "codex")
    assert result.returncode == 1
    assert "Model `patch`" in result.stdout


def test_force_codex_prompt_warns_on_patch(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "node")
    active = {
        "interaction_model": "patch",
        "issue": {"number": 1, "title": "Patch task", "body": "", "url": ""},
    }
    state = tmp_path / ".rail" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "active.json").write_text(json.dumps(active), encoding="utf-8")
    result = run_cli(tmp_path, "prompt", "codex", "--force")
    assert "Warning: running Codex prompt despite active model" in result.stdout
    assert "unrecognized arguments: --force" not in result.stderr


def test_force_patch_warns_on_codex(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "node")
    active = {
        "interaction_model": "codex",
        "issue": {"number": 1, "title": "Codex task", "body": "", "url": ""},
    }
    state = tmp_path / ".rail" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "active.json").write_text(json.dumps(active), encoding="utf-8")
    result = run_cli(tmp_path, "patch", "missing.patch", "--force")
    assert "Warning: running patch despite active model" in result.stdout


def test_ci_init_generates_python_workflow(tmp_path: Path) -> None:
    git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"ci-demo\"\n\n[tool.pytest.ini_options]\n", encoding="utf-8")
    run_cli(tmp_path, "init", "--stack", "python")
    result = run_cli(tmp_path, "ci-init")
    assert result.returncode == 0, result.stderr + result.stdout
    yml = (tmp_path / ".github" / "workflows" / "rail.yml").read_text(encoding="utf-8")
    assert "actions/setup-python" in yml
    assert "actions/setup-node" not in yml
    assert "python -m pytest" in yml


def test_log_reads_history(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "node")
    hist = tmp_path / ".rail" / "state" / "history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    hist.write_text(json.dumps({"issue": 7, "interaction_model": "codex", "checks_result": "passed", "commit": "abc123", "title": "Test issue"}) + "\n", encoding="utf-8")
    result = run_cli(tmp_path, "log")
    assert result.returncode == 0
    assert "#7 | codex | passed | abc123 | Test issue" in result.stdout


def test_log_and_report_skip_corrupt_history_lines(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "node")
    hist = tmp_path / ".rail" / "state" / "history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    good1 = {"issue": 1, "interaction_model": "codex", "checks_result": "passed", "commit": "aaa111", "title": "One"}
    good2 = {"issue": 2, "interaction_model": "patch", "checks_result": "failed", "commit": None, "title": "Two"}
    hist.write_text(json.dumps(good1) + "\nnot-json\n" + json.dumps(good2) + "\n", encoding="utf-8")

    log = run_cli(tmp_path, "log", "--last", "10")
    assert log.returncode == 0, log.stderr
    assert "#1 | codex | passed | aaa111 | One" in log.stdout
    assert "#2 | patch | failed | - | Two" in log.stdout
    assert "Traceback" not in log.stderr

    report = run_cli(tmp_path, "report")
    assert report.returncode == 0, report.stderr
    assert "Completed issues: 2" in report.stdout
    assert "- codex: 1" in report.stdout
    assert "- patch: 1" in report.stdout


def test_delegated_output_rewrites_inline_o_alias() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from ai_rail.cli import rewrite_core_output

    text = (
        "rail issue-list  # then: o start next\n"
        "fix the failure, then run: o review && o checks\n"
        "rail start next   # or: o start latest / o start ISSUE_NUMBER\n"
        "option or output open should stay readable\n"
        "`o done` and Run `o status`\n"
    )
    out = rewrite_core_output(text)
    assert "then: rail start next" in out
    assert "run: rail review && rail checks" in out
    assert "# or: rail start latest / rail start ISSUE_NUMBER" in out
    assert "option or output open should stay readable" in out
    assert "`rail done`" in out
    assert "`rail status`" in out
    assert " o " not in out


def test_help_lists_short_daily_commands() -> None:
    result = run_cli(ROOT, "--help")
    assert result.returncode == 0
    assert "Daily: init, resume, plan, import, phase, next, handoff, verify, ship, snapshot, export" in result.stdout


def test_phase3_commit_requires_review_before_shipping(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")

    result = run_cli(tmp_path, "commit", "test: unsafe", "--no-push")

    assert result.returncode == 1
    assert "no fresh review pack" in result.stdout


def test_phase3_review_includes_untracked_text_file_contents(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    new_file = tmp_path / "src" / "new.py"
    new_file.parent.mkdir()
    new_file.write_text("print(123)\n", encoding="utf-8")

    result = run_cli(tmp_path, "review")

    assert result.returncode == 0
    review = (tmp_path / ".rail" / "state" / "last-review.md").read_text(encoding="utf-8")
    assert "### src/new.py" in review
    assert "print(123)" in review


def test_review_includes_untracked_text_file_with_spaces(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    new_file = tmp_path / "notes with spaces.txt"
    new_file.write_text("space path content\n", encoding="utf-8")

    result = run_cli(tmp_path, "review")

    assert result.returncode == 0
    review = (tmp_path / ".rail" / "state" / "last-review.md").read_text(encoding="utf-8")
    assert "### notes with spaces.txt" in review
    assert "space path content" in review


def test_snapshot_changed_paths_include_tracked_file_with_spaces(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    tracked = tmp_path / "tracked name.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked name.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "add spaced file"], cwd=tmp_path, capture_output=True, text=True, check=True)
    tracked.write_text("after\n", encoding="utf-8")

    result = run_cli(tmp_path, "snapshot")

    assert result.returncode == 0, result.stderr + result.stdout
    status = (tmp_path / ".rail" / "brain" / "STATUS.md").read_text(encoding="utf-8")
    assert "- tracked name.txt" in status


def test_review_skips_large_untracked_text_file_contents(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    large_file = tmp_path / "large.txt"
    large_file.write_text("x" * 21000, encoding="utf-8")

    result = run_cli(tmp_path, "review")

    assert result.returncode == 0
    review = (tmp_path / ".rail" / "state" / "last-review.md").read_text(encoding="utf-8")
    assert "### large.txt" in review
    assert "[skipped: binary or larger than 20KB]" in review


def test_phase3_commit_blocks_dangerous_env_file(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    assert run_cli(tmp_path, "checks").returncode == 0

    result = run_cli(tmp_path, "commit", "test: dangerous", "--no-push")

    assert result.returncode == 1
    assert "refusing to commit dangerous/generated paths" in result.stdout
    assert "- .env" in result.stdout


def test_commit_blocks_dangerous_key_files(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "deploy.key").write_text("PRIVATE KEY\n", encoding="utf-8")
    (tmp_path / "id_ed25519").write_text("PRIVATE KEY\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    assert run_cli(tmp_path, "checks").returncode == 0

    result = run_cli(tmp_path, "commit", "test: dangerous keys", "--no-push")

    assert result.returncode == 1
    assert "refusing to commit dangerous/generated paths" in result.stdout
    assert "- deploy.key" in result.stdout
    assert "- id_ed25519" in result.stdout


def test_commit_blocks_dangerous_file_with_spaces(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "secret key.pem").write_text("PRIVATE KEY\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    assert run_cli(tmp_path, "checks").returncode == 0

    result = run_cli(tmp_path, "commit", "test: dangerous spaced key", "--no-push")

    assert result.returncode == 1
    assert "refusing to commit dangerous/generated paths" in result.stdout
    assert "- secret key.pem" in result.stdout


def test_commit_force_warns_about_dangerous_paths(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")

    result = run_cli(tmp_path, "commit", "test: forced dangerous", "--no-push", "--force")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Warning: --force skips commit safety checks." in result.stdout
    assert "Warning: dangerous paths are present in the working tree:" in result.stdout
    assert "[rail]   - .env" in result.stdout
    assert "Warning: --force does not protect against committing these." in result.stdout


def test_phase3_commit_succeeds_after_fresh_review_and_checks(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    assert run_cli(tmp_path, "checks").returncode == 0

    result = run_cli(tmp_path, "commit", "test: safe", "--no-push")

    assert result.returncode == 0, result.stderr + result.stdout
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: safe" in log.stdout


def test_commit_stages_untracked_file_with_spaces_when_allowed(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "safe notes.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    assert run_cli(tmp_path, "checks").returncode == 0

    result = run_cli(tmp_path, "commit", "test: spaced path", "--no-push")

    assert result.returncode == 0, result.stderr + result.stdout
    show = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "safe notes.txt" in show.stdout


def test_checks_run_flag_writes_passing_last_checks(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    command = f'"{sys.executable}" -c "print(123)"'

    result = run_cli(tmp_path, "checks", "--run", command)

    assert result.returncode == 0, result.stderr + result.stdout
    checks = (tmp_path / ".rail" / "state" / "last-checks.md").read_text(encoding="utf-8")
    assert f"## `{command}`" in checks
    assert "Exit code: 0" in checks


def test_checks_run_flag_allows_multiple_commands(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    first = f'"{sys.executable}" -c "print(1)"'
    second = f'"{sys.executable}" -c "print(2)"'

    result = run_cli(tmp_path, "checks", "--run", first, "--run", second)

    assert result.returncode == 0, result.stderr + result.stdout
    checks = (tmp_path / ".rail" / "state" / "last-checks.md").read_text(encoding="utf-8")
    assert f"## `{first}`" in checks
    assert f"## `{second}`" in checks


def test_checks_run_flag_runs_npm_typecheck(tmp_path: Path, monkeypatch) -> None:
    init_static_repo_with_commit(tmp_path)
    install_fake_npm(tmp_path, monkeypatch)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"typecheck": "pass"}}), encoding="utf-8")

    result = run_cli(tmp_path, "checks", "--run", "npm run typecheck")

    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / ".rail" / "npm-runs.txt").read_text(encoding="utf-8").splitlines() == ["typecheck"]
    checks = (tmp_path / ".rail" / "state" / "last-checks.md").read_text(encoding="utf-8")
    assert "## `npm run typecheck`" in checks
    assert "Exit code: 0" in checks


def test_verify_writes_verified_snapshot(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    write_active_issue(tmp_path)
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")

    result = run_cli(tmp_path, "verify")

    assert result.returncode == 0, result.stderr + result.stdout
    snapshot = json.loads((tmp_path / ".rail" / "state" / "last-verify.json").read_text(encoding="utf-8"))
    assert snapshot["check_result"] == "passed"
    assert snapshot["branch"]
    assert "app.txt" in snapshot["changed_files"]
    assert snapshot["fingerprint"]
    assert "[rail] Verified snapshot saved." in result.stdout


def test_ship_after_fresh_verify_does_not_rerun_checks(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    write_active_issue(tmp_path)
    command = f'"{sys.executable}" -c "from pathlib import Path; Path(r\'{tmp_path / "check-count.txt"}\').open(\'a\', encoding=\'utf-8\').write(\'x\\n\')"'
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = [command]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "verify").returncode == 0

    result = ship_without_remote(tmp_path, "test: verified ship")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "[rail] Verified snapshot is fresh." in result.stdout
    assert "Checks already passed in last verify. Skipping recheck." in result.stdout
    assert "Running check 1/1" not in result.stdout
    assert (tmp_path / "check-count.txt").read_text(encoding="utf-8").splitlines() == ["x"]
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: verified ship" in log.stdout


def test_ship_blocks_if_tracked_file_changes_after_verify(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    write_active_issue(tmp_path)
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "verify").returncode == 0
    (tmp_path / "app.txt").write_text("changed after verify\n", encoding="utf-8")

    result = ship_without_remote(tmp_path, "test: stale verified ship")

    assert result.returncode == 1
    assert "Error: files changed after last review. Run: rail v" in result.stdout


def test_ship_blocks_if_reviewed_untracked_file_changes_after_verify(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    write_active_issue(tmp_path)
    (tmp_path / "notes.txt").write_text("reviewed\n", encoding="utf-8")
    assert run_cli(tmp_path, "verify").returncode == 0
    (tmp_path / "notes.txt").write_text("changed after verify\n", encoding="utf-8")

    result = ship_without_remote(tmp_path, "test: stale untracked")

    assert result.returncode == 1
    assert "Error: files changed after last review. Run: rail v" in result.stdout


def test_ship_includes_own_project_completion_update_after_verify(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    state = tmp_path / ".rail" / "state"
    active = {"issue": {"number": 2, "title": "Build thing", "body": "", "url": ""}, "interaction_model": "codex"}
    (state / "active.json").write_text(json.dumps(active), encoding="utf-8")
    (tmp_path / ".rail" / "PROJECT.md").write_text("<!-- AI RAIL ROADMAP START -->\n\n## Phase P1 - Foundation\nStatus: active\n\n### Tasks\n- [ ] #2 | P1-T01 | Build thing\n\n<!-- AI RAIL ROADMAP END -->\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "verify").returncode == 0

    result = run_cli(tmp_path, "ship", "test: project complete", "--no-push", "--no-close", "--no-done", "--no-sync")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Updating .rail/PROJECT.md for completed issue #2." in result.stdout
    assert "- [x] #2 | P1-T01 | Build thing" in (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")
    show = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert ".rail/PROJECT.md" in show.stdout


def test_ship_recheck_reruns_checks_with_fresh_verify(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    write_active_issue(tmp_path)
    command = f'"{sys.executable}" -c "from pathlib import Path; Path(r\'{tmp_path / "check-count.txt"}\').open(\'a\', encoding=\'utf-8\').write(\'x\\n\')"'
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = [command]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "verify").returncode == 0

    result = ship_without_remote(tmp_path, "test: verified recheck", "--recheck")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Running check 1/1" in result.stdout
    assert (tmp_path / "check-count.txt").read_text(encoding="utf-8").splitlines() == ["x", "x"]


def test_ship_blocks_without_passing_verify_snapshot_when_checks_are_legacy_passed(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    assert run_cli(tmp_path, "checks").returncode == 0

    result = ship_without_remote(tmp_path, "test: no verify snapshot")

    assert result.returncode == 1
    assert "Error: no passing verify snapshot found. Run: rail v" in result.stdout


def test_ship_auto_runs_checks_when_checks_are_missing(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0

    result = ship_without_remote(tmp_path, "test: missing checks")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Last checks are missing. Running checks now..." in result.stdout
    assert "Checks passed. Continuing ship." in result.stdout
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: missing checks" in log.stdout


def test_ship_auto_runs_checks_when_checks_are_stale(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("before\n", encoding="utf-8")
    assert run_cli(tmp_path, "checks").returncode == 0
    checks_file = tmp_path / ".rail" / "state" / "last-checks.md"
    os.utime(checks_file, (1, 1))
    (tmp_path / "app.txt").write_text("after\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0

    result = ship_without_remote(tmp_path, "test: stale checks")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Last checks are stale. Running checks now..." in result.stdout
    assert "Checks passed. Continuing ship." in result.stdout
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: stale checks" in log.stdout


def test_ship_auto_runs_checks_when_last_checks_failed(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = [f'"{sys.executable}" -c "print(123)"']
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    checks_file = tmp_path / ".rail" / "state" / "last-checks.md"
    checks_file.write_text("Exit code: 1\nold failure\n", encoding="utf-8")

    result = ship_without_remote(tmp_path, "test: rerun failed checks")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Last checks are failed. Running checks now..." in result.stdout
    assert "Checks passed. Continuing ship." in result.stdout
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: rerun failed checks" in log.stdout


def test_ship_recovers_from_missing_npm_check_script(tmp_path: Path, monkeypatch) -> None:
    init_static_repo_with_commit(tmp_path)
    install_fake_npm(tmp_path, monkeypatch)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"typecheck": "pass"}}), encoding="utf-8")
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = ["npm run check"]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    checks_file = tmp_path / ".rail" / "state" / "last-checks.md"
    checks_file.write_text("Exit code: 1\nold failure\n", encoding="utf-8")

    result = ship_without_remote(tmp_path, "test: recover npm check")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "[rail] Configured check `npm run check` is not available." in result.stdout
    assert "[rail] Found available project check: `npm run typecheck`." in result.stdout
    assert "[rail] Running replacement check now..." in result.stdout
    assert (tmp_path / ".rail" / "npm-runs.txt").read_text(encoding="utf-8").splitlines() == ["typecheck"]
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["checks"] == ["npm run typecheck"]
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: recover npm check" in log.stdout


def test_ship_stops_when_replacement_npm_check_fails(tmp_path: Path, monkeypatch) -> None:
    init_static_repo_with_commit(tmp_path)
    install_fake_npm(tmp_path, monkeypatch)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"typecheck": "fail"}}), encoding="utf-8")
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = ["npm run check"]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    checks_file = tmp_path / ".rail" / "state" / "last-checks.md"
    checks_file.write_text("Exit code: 1\nold failure\n", encoding="utf-8")

    result = ship_without_remote(tmp_path, "test: replacement fails")

    assert result.returncode == 7, result.stderr + result.stdout
    assert "[rail] Configured check `npm run check` is not available." in result.stdout
    assert "[rail] Found available project check: `npm run typecheck`." in result.stdout
    assert "Checks still failed. Ship stopped." in result.stdout
    assert (tmp_path / ".rail" / "npm-runs.txt").read_text(encoding="utf-8").splitlines() == ["typecheck"]
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["checks"] == ["npm run check"]
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: replacement fails" not in log.stdout


def test_ship_stops_when_missing_npm_check_has_no_replacement(tmp_path: Path, monkeypatch) -> None:
    init_static_repo_with_commit(tmp_path)
    install_fake_npm(tmp_path, monkeypatch)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"format": "pass"}}), encoding="utf-8")
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = ["npm run check"]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    checks_file = tmp_path / ".rail" / "state" / "last-checks.md"
    checks_file.write_text("Exit code: 1\nold failure\n", encoding="utf-8")

    result = ship_without_remote(tmp_path, "test: no npm replacement")

    assert result.returncode == 1, result.stderr + result.stdout
    assert "[rail] Configured check `npm run check` is not available." in result.stdout
    assert "[rail] No usable npm check script was found in package.json." in result.stdout
    assert "Checks still failed. Ship stopped." in result.stdout
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: no npm replacement" not in log.stdout


def test_ship_still_blocks_when_configured_npm_check_really_fails(tmp_path: Path, monkeypatch) -> None:
    init_static_repo_with_commit(tmp_path)
    install_fake_npm(tmp_path, monkeypatch)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"check": "fail", "typecheck": "pass"}}), encoding="utf-8")
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = ["npm run check"]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    checks_file = tmp_path / ".rail" / "state" / "last-checks.md"
    checks_file.write_text("Exit code: 1\nold failure\n", encoding="utf-8")

    result = ship_without_remote(tmp_path, "test: real check fails")

    assert result.returncode == 7, result.stderr + result.stdout
    assert "Found available project check" not in result.stdout
    assert "Checks still failed. Ship stopped." in result.stdout
    assert (tmp_path / ".rail" / "npm-runs.txt").read_text(encoding="utf-8").splitlines() == ["check"]
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: real check fails" not in log.stdout


def test_ship_still_refuses_when_auto_rerun_checks_fail(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    cfg_path = tmp_path / ".rail" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["checks"] = [f'"{sys.executable}" -c "raise SystemExit(7)"']
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0
    checks_file = tmp_path / ".rail" / "state" / "last-checks.md"
    checks_file.write_text("Exit code: 1\nold failure\n", encoding="utf-8")

    result = ship_without_remote(tmp_path, "test: fail checks")

    assert result.returncode == 7, result.stderr + result.stdout
    assert "Last checks are failed. Running checks now..." in result.stdout
    assert "Checks still failed. Ship stopped." in result.stdout
    assert "Fix checks and rerun `rail ship`, or use `--force` only if you intentionally accept the risk." in result.stdout
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: fail checks" not in log.stdout


def test_ship_does_not_bypass_review_safety_when_auto_checks_pass(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")

    result = ship_without_remote(tmp_path, "test: no review")

    assert result.returncode == 1
    assert "Last checks are missing. Running checks now..." in result.stdout
    assert "no fresh review pack" in result.stdout


def test_ship_force_does_not_auto_rerun_failed_checks(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    checks_file = tmp_path / ".rail" / "state" / "last-checks.md"
    checks_file.write_text("Exit code: 1\nold failure\n", encoding="utf-8")

    result = ship_without_remote(tmp_path, "test: forced ship", "--force")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Running checks now" not in result.stdout
    assert "Warning: --force skips commit safety checks." in result.stdout
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: forced ship" in log.stdout


def test_ship_allows_missing_checks_override(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0

    result = ship_without_remote(tmp_path, "test: allow missing checks", "--allow-missing-checks")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "continuing because --allow-missing-checks was used" in result.stdout
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: allow missing checks" in log.stdout


def test_ship_allows_stale_checks_override(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("before\n", encoding="utf-8")
    assert run_cli(tmp_path, "checks").returncode == 0
    checks_file = tmp_path / ".rail" / "state" / "last-checks.md"
    os.utime(checks_file, (1, 1))
    (tmp_path / "app.txt").write_text("after\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0

    result = ship_without_remote(tmp_path, "test: allow stale checks", "--allow-stale")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "continuing because --allow-stale was used" in result.stdout
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "test: allow stale checks" in log.stdout


def test_ship_reports_partial_state_when_issue_close_fails(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir()
    rail.write_text(
        "import sys\n"
        "cmd = sys.argv[1]\n"
        "print(f'fake {cmd}')\n"
        "raise SystemExit(1 if cmd == 'issue-close' else 0)\n",
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "ship", "test: partial", "--no-push", "--no-done", "--no-sync", "--no-merge")

    assert result.returncode == 1
    assert "fake commit" in result.stdout
    assert "fake issue-close" in result.stdout
    assert "Ship stopped after commit succeeded; issue close failed." in result.stdout
    assert "Active state was kept." in result.stdout
    assert "Recovery: manually close the GitHub issue or fix `gh auth login`, then run: rail done && rail sync" in result.stdout


def test_local_runtime_version_matches_public_alpha(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")

    result = subprocess.run(
        [sys.executable, str(tmp_path / ".rail" / "rail.py"), "--help"],
        cwd=tmp_path,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert "AI Rail v0.1.0a14" in result.stdout



def test_phase4_snapshot_writes_project_brain(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static", "--project-name", "Brain Demo")
    state = tmp_path / ".rail" / "state"
    state.mkdir(parents=True, exist_ok=True)
    active = {
        "interaction_model": "codex",
        "issue": {"number": 4, "title": "Add handoff", "body": "Build the project brain.", "url": "https://example.test/4"},
        "branch": "issue-4-add-handoff",
    }
    (state / "active.json").write_text(json.dumps(active), encoding="utf-8")

    result = run_cli(tmp_path, "snapshot")

    assert result.returncode == 0, result.stderr + result.stdout
    brain = tmp_path / ".rail" / "brain"
    assert (brain / "PROJECT.md").exists()
    assert (brain / "CURRENT_TASK.md").exists()
    assert (brain / "STATUS.md").exists()
    assert (brain / "RECENT_HISTORY.md").exists()
    assert (brain / "HANDOFF.md").exists()
    assert "Brain Demo" in (brain / "PROJECT.md").read_text(encoding="utf-8")
    assert "#4 — Add handoff" in (brain / "CURRENT_TASK.md").read_text(encoding="utf-8")


def test_phase4_handoff_generates_model_specific_file(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static", "--project-name", "Handoff Demo")
    state = tmp_path / ".rail" / "state"
    state.mkdir(parents=True, exist_ok=True)
    active = {
        "interaction_model": "codex",
        "issue": {"number": 8, "title": "Portable context", "body": "Create handoff output.", "url": "https://example.test/8"},
    }
    (state / "active.json").write_text(json.dumps(active), encoding="utf-8")

    result = run_cli(tmp_path, "handoff", "--for", "codex")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "AI Rail Handoff — codex" in result.stdout
    assert "Implement only the active issue" in result.stdout
    assert "#8 — Portable context" in result.stdout
    handoff = tmp_path / ".rail" / "state" / "last-handoff-codex.md"
    assert handoff.exists()
    assert "Handoff Demo" in handoff.read_text(encoding="utf-8")


def test_phase4_handoff_can_include_review_and_checks(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    state = tmp_path / ".rail" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "last-review.md").write_text("review-content\n", encoding="utf-8")
    (state / "last-checks.md").write_text("Exit code: 0\nchecks-content\n", encoding="utf-8")

    result = run_cli(tmp_path, "handoff", "--include-review", "--include-checks")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "review-content" in result.stdout
    assert "checks-content" in result.stdout



def test_phase5_export_writes_tool_specific_files(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static", "--project-name", "Export Demo")
    state = tmp_path / ".rail" / "state"
    state.mkdir(parents=True, exist_ok=True)
    active = {
        "interaction_model": "codex",
        "issue": {"number": 5, "title": "Export brain", "body": "Create tool exports.", "url": "https://example.test/5"},
    }
    (state / "active.json").write_text(json.dumps(active), encoding="utf-8")

    result = run_cli(tmp_path, "export")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "AGENTS.md / Codex-compatible agents" in result.stdout
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / "AIDER.md").exists()
    assert (tmp_path / ".cursor" / "rules" / "ai-rail.mdc").exists()
    assert (tmp_path / ".github" / "copilot-instructions.md").exists()
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "AI_RAIL_EXPORT_BEGIN" in agents
    assert "#5 — Export brain" in agents
    assert "Export Demo" in agents
    cursor = (tmp_path / ".cursor" / "rules" / "ai-rail.mdc").read_text(encoding="utf-8")
    assert "alwaysApply: true" in cursor


def test_phase5_export_refuses_unmarked_existing_file_without_force(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    existing = tmp_path / "AGENTS.md"
    existing.write_text("human instructions\n", encoding="utf-8")

    result = run_cli(tmp_path, "export", "--target", "agents")

    assert result.returncode == 1
    assert "refused existing unmarked file" in result.stdout
    assert existing.read_text(encoding="utf-8") == "human instructions\n"


def test_export_all_refuses_unmarked_files_without_overwriting_anything(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    agents = tmp_path / "AGENTS.md"
    claude = tmp_path / "CLAUDE.md"
    agents.write_text("human agents\n", encoding="utf-8")
    claude.write_text("human claude\n", encoding="utf-8")

    result = run_cli(tmp_path, "export")

    assert result.returncode == 1
    assert "refused existing unmarked file" in result.stdout
    assert agents.read_text(encoding="utf-8") == "human agents\n"
    assert claude.read_text(encoding="utf-8") == "human claude\n"


def test_phase5_export_force_backs_up_unmarked_existing_file(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    existing = tmp_path / "CLAUDE.md"
    existing.write_text("human claude memory\n", encoding="utf-8")

    result = run_cli(tmp_path, "export", "--target", "claude", "--force")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "replaced with backup" in result.stdout
    assert (tmp_path / "CLAUDE.md.rail.bak").read_text(encoding="utf-8") == "human claude memory\n"
    assert "AI_RAIL_EXPORT_BEGIN" in existing.read_text(encoding="utf-8")


def test_export_force_creates_backup_before_overwrite(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    existing = tmp_path / "AGENTS.md"
    existing.write_text("human agents before force\n", encoding="utf-8")

    result = run_cli(tmp_path, "export", "--target", "agents", "--force")

    assert result.returncode == 0, result.stderr + result.stdout
    backup = tmp_path / "AGENTS.md.rail.bak"
    assert backup.read_text(encoding="utf-8") == "human agents before force\n"
    rewritten = existing.read_text(encoding="utf-8")
    assert "human agents before force" not in rewritten
    assert "AI_RAIL_EXPORT_BEGIN" in rewritten


def test_phase5_export_updates_existing_managed_block_preserving_human_text(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static")
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "# Human header\n\n<!-- AI_RAIL_EXPORT_BEGIN -->\nold\n<!-- AI_RAIL_EXPORT_END -->\n\n# Human footer\n",
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "export", "--target", "agents")

    assert result.returncode == 0, result.stderr + result.stdout
    text = agents.read_text(encoding="utf-8")
    assert text.startswith("# Human header")
    assert text.rstrip().endswith("# Human footer")
    assert "old" not in text
    assert "Generated by `rail export --target agents`" in text



def test_phase6_demo_prints_public_walkthrough() -> None:
    result = run_cli(ROOT, "demo")
    assert result.returncode == 0
    assert "AI Rail 3-minute demo" in result.stdout
    assert "rail handoff --for chatgpt" in result.stdout
    assert "rail export" in result.stdout


def test_phase6_demo_can_write_output_file(tmp_path: Path) -> None:
    output = tmp_path / "demo.md"
    result = run_cli(ROOT, "demo", "--output", str(output))
    assert result.returncode == 0
    assert output.exists()
    assert "AI Rail 3-minute demo" in output.read_text(encoding="utf-8")


def test_phase6_release_check_passes_on_package_root() -> None:
    result = run_cli(ROOT, "release-check")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "ready for alpha packaging" in result.stdout
    assert "docs/QUICKSTART.md" in result.stdout


def test_version_output_includes_author_and_repository() -> None:
    result = run_cli(ROOT, "--version")

    assert result.returncode == 0
    assert "AI Rail 0.1.0a14" in result.stdout
    assert "Created by Afshin Saberi" in result.stdout
    assert "https://github.com/afshinsb/ai-rail" in result.stdout


def test_about_outputs_project_metadata() -> None:
    result = run_cli(ROOT, "about")

    assert result.returncode == 0
    assert "AI Rail" in result.stdout
    assert "A local-first workflow rail and portable project brain for AI-assisted development." in result.stdout
    assert "Version: 0.1.0a14" in result.stdout
    assert "Author: Afshin Saberi" in result.stdout
    assert "Repository: https://github.com/afshinsb/ai-rail" in result.stdout
    assert "Website: https://theafshin.com" in result.stdout
    assert "License: Apache-2.0" in result.stdout


def test_pyproject_has_professional_author_and_project_urls() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'authors = [{ name = "Afshin Saberi" }]' in pyproject
    assert 'Homepage = "https://github.com/afshinsb/ai-rail"' in pyproject
    assert 'Repository = "https://github.com/afshinsb/ai-rail"' in pyproject
    assert 'Documentation = "https://github.com/afshinsb/ai-rail/tree/main/docs"' in pyproject
    assert 'Changelog = "https://github.com/afshinsb/ai-rail/blob/main/CHANGELOG.md"' in pyproject
    assert '"Bug Tracker" = "https://github.com/afshinsb/ai-rail/issues"' in pyproject


def test_phase6_help_lists_public_phase_commands() -> None:
    result = run_cli(ROOT, "--help")
    assert result.returncode == 0
    assert "about" in result.stdout
    assert "demo" in result.stdout
    assert "release-check" in result.stdout
    assert "upgrade" in result.stdout
    assert "Aliases: r, n, p, ph, im, v, s, snap, h, hc, hg, hl, x, xd, xf, rc" in result.stdout


def test_alias_expansion_table_matches_documented_shortcuts() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from ai_rail.cli import expand_alias

    cases = {
        ("r",): ["resume"],
        ("n",): ["next", "--copy"],
        ("p",): ["plan", "--copy"],
        ("ph",): ["phase", "--copy"],
        ("im",): ["import"],
        ("v",): ["verify", "--copy"],
        ("s", "test: msg"): ["ship", "test: msg"],
        ("snap",): ["snapshot"],
        ("h",): ["handoff", "--for", "generic", "--copy"],
        ("hc",): ["handoff", "--for", "codex", "--copy"],
        ("hg",): ["handoff", "--for", "chatgpt", "--copy"],
        ("hl",): ["handoff", "--for", "claude", "--copy"],
        ("x",): ["export"],
        ("xd",): ["export", "--dry-run"],
        ("xf",): ["export", "--force"],
        ("rc",): ["release-check"],
        ("clear",): ["clear-active"],
        ("next", "--copy"): ["next", "--copy"],
    }

    for argv, expected in cases.items():
        assert expand_alias(list(argv)) == expected


def test_alias_rc_runs_release_check() -> None:
    result = run_cli(ROOT, "rc")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "ready for alpha packaging" in result.stdout


def test_alias_snap_writes_project_brain(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static", "--project-name", "Alias Demo")

    result = run_cli(tmp_path, "snap")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Updated AI Rail project brain:" in result.stdout
    assert (tmp_path / ".rail" / "brain" / "PROJECT.md").exists()


def test_alias_xd_dry_run_does_not_write_exports(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static", "--project-name", "Alias Dry Run Demo")

    result = run_cli(tmp_path, "xd")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "AI Rail tool exports: (dry run)" in result.stdout
    assert not (tmp_path / "AGENTS.md").exists()

def test_phase6_export_dry_run_does_not_write_files(tmp_path: Path) -> None:
    git_init(tmp_path)
    run_cli(tmp_path, "init", "--stack", "static", "--project-name", "Dry Run Demo")

    result = run_cli(tmp_path, "export", "--dry-run")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "AI Rail tool exports: (dry run)" in result.stdout
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "AIDER.md").exists()
    assert not (tmp_path / ".cursor").exists()
    assert not (tmp_path / ".github").exists()
    assert not (tmp_path / ".rail" / "brain").exists()
