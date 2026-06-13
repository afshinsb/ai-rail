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


def test_init_creates_node_config_with_check(tmp_path: Path) -> None:
    git_init(tmp_path)
    result = run_cli(tmp_path, "init", "--stack", "node", "--project-name", "Demo")
    assert result.returncode == 0, result.stderr + result.stdout
    cfg = json.loads((tmp_path / ".rail" / "config.json").read_text(encoding="utf-8"))
    assert cfg["project_name"] == "Demo"
    assert cfg["checks"] == ["npm run check"]
    assert (tmp_path / ".rail" / "CHATGPT.md").exists()


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
    assert "Daily: init, resume, next, handoff, verify, ship, snapshot, export" in result.stdout


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
    assert "AI Rail v0.1.0a8" in result.stdout



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
    assert "AI Rail 0.1.0a8" in result.stdout
    assert "Created by Afshin Saberi" in result.stdout
    assert "https://github.com/afshinsb/ai-rail" in result.stdout


def test_about_outputs_project_metadata() -> None:
    result = run_cli(ROOT, "about")

    assert result.returncode == 0
    assert "AI Rail" in result.stdout
    assert "A local-first workflow rail and portable project brain for AI-assisted development." in result.stdout
    assert "Version: 0.1.0a8" in result.stdout
    assert "Author: Afshin Saberi" in result.stdout
    assert "Repository: https://github.com/afshinsb/ai-rail" in result.stdout
    assert "Website: https://theafshin.com" in result.stdout
    assert "License: Apache-2.0" in result.stdout


def test_pyproject_has_professional_author_and_project_urls() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'authors = [{ name = "Afshin Saberi" }]' in pyproject
    assert 'Homepage = "https://theafshin.com"' in pyproject
    assert 'Repository = "https://github.com/afshinsb/ai-rail"' in pyproject
    assert 'Documentation = "https://github.com/afshinsb/ai-rail/tree/main/docs"' in pyproject


def test_phase6_help_lists_public_phase_commands() -> None:
    result = run_cli(ROOT, "--help")
    assert result.returncode == 0
    assert "about" in result.stdout
    assert "demo" in result.stdout
    assert "release-check" in result.stdout
    assert "upgrade" in result.stdout
    assert "Aliases: r, n, v, s, snap, h, hc, hg, hl, x, xd, xf, rc" in result.stdout


def test_alias_expansion_table_matches_documented_shortcuts() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from ai_rail.cli import expand_alias

    cases = {
        ("r",): ["resume"],
        ("n",): ["next", "--copy"],
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
