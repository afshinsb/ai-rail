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


def init_static_repo_with_commit(path: Path) -> None:
    git_init(path)
    run_cli(path, "init", "--stack", "static")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True, text=True, check=True)


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


def test_init_creates_node_config_with_check(tmp_path: Path) -> None:
    git_init(tmp_path)
    result = run_cli(tmp_path, "init", "--stack", "node", "--project-name", "Demo")
    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["project_name"] == "Demo"
    assert cfg["checks"] == ["npm run check"]
    assert (tmp_path / ".rail" / "CHATGPT.md").exists()
    assert (tmp_path / ".rail" / "AIDER.md").exists()


def test_init_rerun_updates_placeholder_project_name(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init").returncode == 0
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
    assert cfg["checks"] == ["npm run check"]
    assert "Updated placeholder config values: project_name" in result.stdout
    for path in preserved:
        assert path.read_text(encoding="utf-8") == "keep\n"
    doctor = run_cli(tmp_path, "doctor")
    assert "project_name is still CHANGE_ME" not in doctor.stdout


def test_init_rerun_preserves_existing_project_name(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert run_cli(tmp_path, "init", "--stack", "node", "--project-name", "Keep Me").returncode == 0

    result = run_cli(tmp_path, "init", "--stack", "python", "--project-name", "Other")

    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["project_name"] == "Keep Me"
    assert "project_name" not in result.stdout


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
    assert after["default_branch"] == "trunk"
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
    assert "## Current state" in text
    assert "## Target state" in text
    assert "## Phases" in text
    assert "## Active execution queue" in text
    assert "## Next recommended issue" in text
    assert "## Completed work" in text
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
    assert "mark completed tasks/phases in the roadmap issue memory block" in result.stdout
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
    assert "## Roadmap" in text
    assert "- [ ] #2 Build thing" in text
    assert not (tmp_path / ".rail" / "ROADMAP.md").exists()
    assert "Open issues: 1" in result.stdout
    assert "Closed issues: 1" in result.stdout


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
    assert "Run `rail phase --copy`" in result.stdout


def test_ship_marks_project_task_complete(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir(parents=True)
    rail.write_text("import sys\nprint('fake ' + sys.argv[1])\nraise SystemExit(0)\n", encoding="utf-8")
    state = tmp_path / ".rail" / "state"
    state.mkdir()
    (state / "active.json").write_text(json.dumps({"issue": {"number": 2, "title": "Build thing", "body": "", "url": ""}, "interaction_model": "codex"}), encoding="utf-8")
    (tmp_path / ".rail" / "PROJECT.md").write_text("<!-- AI RAIL MANAGED ROADMAP START -->\n## Completed work\n\n## Active execution queue\n\n- [ ] #2 Build thing\n<!-- AI RAIL MANAGED ROADMAP END -->\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push", "--no-sync")

    assert result.returncode == 0, result.stderr + result.stdout
    text = (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")
    assert "- [x] #2 Build thing" in text
    assert "Updated .rail/PROJECT.md for completed issue" in result.stdout


def test_ship_default_path_marks_project_before_commit_and_syncs(tmp_path: Path) -> None:
    rail = tmp_path / ".rail" / "rail.py"
    rail.parent.mkdir(parents=True)
    rail.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "cmd = sys.argv[1]\n"
        "Path('.rail/calls.txt').open('a', encoding='utf-8').write(cmd + '\\n')\n"
        "if cmd == 'commit' and '- [x] #2 Build thing' not in Path('.rail/PROJECT.md').read_text(encoding='utf-8'):\n"
        "    print('project not marked before commit')\n"
        "    raise SystemExit(2)\n"
        "print('fake ' + cmd)\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    state = tmp_path / ".rail" / "state"
    state.mkdir()
    (state / "active.json").write_text(json.dumps({"issue": {"number": 2, "title": "Build thing", "body": "", "url": ""}, "interaction_model": "codex"}), encoding="utf-8")
    (tmp_path / ".rail" / "PROJECT.md").write_text("## Completed work\n\n## Active execution queue\n\n- [ ] #2 Build thing\n", encoding="utf-8")

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push")

    assert result.returncode == 0, result.stderr + result.stdout
    calls = (tmp_path / ".rail" / "calls.txt").read_text(encoding="utf-8").splitlines()
    assert calls == ["commit", "issue-close", "done", "sync"]
    assert calls.count("commit") == 1
    assert "- [x] #2 Build thing" in (tmp_path / ".rail" / "PROJECT.md").read_text(encoding="utf-8")


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

    result = run_cli(tmp_path, "ship", "test: ship", "--no-push", "--no-sync")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Warning: could not update .rail/PROJECT.md before ship" in result.stdout


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


def test_ship_blocks_when_checks_are_missing(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("hello\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0

    result = ship_without_remote(tmp_path, "test: missing checks")

    assert result.returncode == 1
    assert "Error: last checks are MISSING. Refusing to commit." in result.stdout


def test_ship_blocks_when_checks_are_stale(tmp_path: Path) -> None:
    init_static_repo_with_commit(tmp_path)
    (tmp_path / "app.txt").write_text("before\n", encoding="utf-8")
    assert run_cli(tmp_path, "checks").returncode == 0
    checks_file = tmp_path / ".rail" / "state" / "last-checks.md"
    os.utime(checks_file, (1, 1))
    (tmp_path / "app.txt").write_text("after\n", encoding="utf-8")
    assert run_cli(tmp_path, "review").returncode == 0

    result = ship_without_remote(tmp_path, "test: stale checks")

    assert result.returncode == 1
    assert "Error: checks are older than current file changes." in result.stdout


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

    result = run_cli(tmp_path, "ship", "test: partial", "--no-push", "--no-done", "--no-sync")

    assert result.returncode == 1
    assert "fake commit" in result.stdout
    assert "fake issue-close" in result.stdout
    assert "Ship stopped after commit succeeded; issue close failed. Active state was kept." in result.stdout
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
    assert "AI Rail v0.1.0a12" in result.stdout



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
    assert "AI Rail 0.1.0a12" in result.stdout
    assert "Created by Afshin Saberi" in result.stdout
    assert "https://github.com/afshinsb/ai-rail" in result.stdout


def test_about_outputs_project_metadata() -> None:
    result = run_cli(ROOT, "about")

    assert result.returncode == 0
    assert "AI Rail" in result.stdout
    assert "A local-first workflow rail and portable project brain for AI-assisted development." in result.stdout
    assert "Version: 0.1.0a12" in result.stdout
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
