from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class SupportContext:
    root: Callable[[], Path]
    rail_dir: Callable[[], Path]
    read_json: Callable[[Path, Any], Any]
    safe_read_text: Callable[..., str]
    copy_to_clipboard: Callable[[str], bool]
    backup_file: Callable[[Path], Path]
    version: str
    project_description: str
    author_name: str
    project_repository: str
    author_website: str
    project_license: str


def render_version(ctx: SupportContext) -> str:
    return f"""AI Rail {ctx.version}

Created by {ctx.author_name}
{ctx.project_repository}
"""


def render_about(ctx: SupportContext) -> str:
    return f"""AI Rail

{ctx.project_description}

Version: {ctx.version}
Author: {ctx.author_name}
Repository: {ctx.project_repository}
Website: {ctx.author_website}
License: {ctx.project_license}
"""


def cmd_ci_init(argv: list[str], ctx: SupportContext) -> int:
    parser = argparse.ArgumentParser(prog="rail ci-init")
    parser.add_argument("--force", action="store_true")
    ns = parser.parse_args(argv)
    cfg = ctx.read_json(ctx.rail_dir() / "config.json", {})
    checks = cfg.get("checks") or []
    if not checks:
        print("No checks configured in .rail/config.json.")
        return 1
    workflow = ctx.root() / ".github" / "workflows" / "rail.yml"
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

    def yaml_run_step(index: int, command: str) -> str:
        indented = "\n".join(f"          {line}" for line in command.splitlines() or [""])
        return f"      - name: Run check {index}\n        run: |\n{indented}\n"

    check_steps = "".join(yaml_run_step(i, str(cmd)) for i, cmd in enumerate(checks, 1))
    content = """name: AI Rail Checks

on:
  push:
  pull_request:

jobs:
  rail:
    runs-on: ubuntu-latest
    steps:
""" + "".join(setup_steps) + check_steps

    if workflow.exists() and ns.force:
        backup = ctx.backup_file(workflow)
        print(f"Backed up existing workflow to {backup}")
    workflow.write_text(content, encoding="utf-8")
    print(f"Created {workflow}")
    return 0


def render_demo_script(ctx: SupportContext) -> str:
    return f"""# AI Rail 3-minute demo

AI Rail is a local-first workflow rail and portable project brain for solo developers using AI coding assistants.

## 1. Install AI Rail

```bash
pipx install ai-rail
rail --version
```

Expected:

```text
AI Rail {ctx.version}
```

## 2. Try the bundled TODO demo

```bash
cd examples/demo-todo
rail init --stack node --project-name \"AI Rail Demo TODO\"
rail doctor
npm run check
```

## 3. Create or plan GitHub issues

For a new project with no scoped issues yet:

```bash
rail plan --copy
```

Paste the planning prompt into a GitHub-connected AI agent. It should create a phased roadmap issue and a first batch of small implementation issues.

After the AI creates or updates the roadmap issue and first issue slice:

```bash
rail import
```

For this demo, create one sample issue directly:

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

After several shipped issues, audit and update the current roadmap phase:

```bash
rail phase --copy
rail import
```

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


def cmd_demo(argv: list[str], ctx: SupportContext) -> int:
    parser = argparse.ArgumentParser(prog="rail demo")
    parser.add_argument("--copy", action="store_true", help="Copy the demo script to clipboard when possible.")
    parser.add_argument("--output", help="Write the demo script to a file.")
    ns = parser.parse_args(argv)

    text = render_demo_script(ctx)
    if ns.output:
        output = Path(ns.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(f"[rail] demo script written: {output}")
    else:
        print(text)

    if ns.copy:
        if ctx.copy_to_clipboard(text):
            print("[rail] demo script copied to clipboard")
        else:
            print("[rail] copy requested, but no supported clipboard command was found")
    return 0


def cmd_about(argv: list[str], ctx: SupportContext) -> int:
    parser = argparse.ArgumentParser(prog="rail about")
    parser.parse_args(argv)
    print(render_about(ctx))
    return 0


def cmd_release_check(argv: list[str], ctx: SupportContext) -> int:
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
        add(f"required file: {rel}", (ctx.root() / rel).exists())

    pyproject = ctx.safe_read_text(ctx.root() / "pyproject.toml")
    add("pyproject version matches CLI", f'version = "{ctx.version}"' in pyproject)
    add("pyproject exposes rail script", 'rail = "ai_rail.cli:main"' in pyproject)

    template_runtime = ctx.safe_read_text(ctx.root() / "src" / "ai_rail" / "template" / ".rail" / "rail.py")
    add("template runtime version matches CLI", f'VERSION = "{ctx.version}"' in template_runtime)

    cli_source = ctx.safe_read_text(ctx.root() / "src" / "ai_rail" / "cli.py")
    try:
        compile(cli_source, "src/ai_rail/cli.py", "exec")
        add("cli.py compiles", True)
    except SyntaxError as exc:
        add("cli.py compiles", False, str(exc))

    missing_docs = [name for name in ["QUICKSTART.md", "COMMANDS.md", "RELEASE.md"] if not (ctx.root() / "docs" / name).exists()]
    add("public docs present", not missing_docs, ", ".join(missing_docs))

    ok = all(item["ok"] for item in checks)
    payload = {"ok": ok, "version": ctx.version, "checks": checks}

    if ns.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"AI Rail release check for {ctx.version}")
        for item in checks:
            mark = "OK" if item["ok"] else "FAIL"
            suffix = f" \u2014 {item['detail']}" if item.get("detail") else ""
            print(f"- {mark}: {item['name']}{suffix}")
        print("\nResult: " + ("ready for alpha packaging" if ok else "not ready"))
    return 0 if ok else 1
