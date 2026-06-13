# Quickstart

AI Rail gives your repo a portable project brain and a short daily workflow for AI-assisted development.

## Install

From a source checkout:

```bash
pip install -e ".[dev]"
rail --version
```

After public release:

```bash
pipx install ai-rail
```

## Initialize a repo

```bash
rail init --stack node --project-name "My Project"
rail doctor
rail resume
```

To refresh an already initialized repo after upgrading AI Rail itself:

```bash
rail upgrade
```

Stack presets:

```bash
rail init --stack node
rail init --stack python
rail init --stack static
```

## Daily loop

```bash
rail next --copy
# paste/run the generated prompt in your AI coding tool
rail verify --copy
# paste the generated review prompt into ChatGPT/Claude for audit
rail ship "type(scope): message"
```

See [WORKFLOWS.md](WORKFLOWS.md) for the Codex-based, patch-based, and AI-direct interaction models.

## Switching AI tools

```bash
rail snapshot
rail handoff --for chatgpt --include-review --include-checks --copy
```

Targets:

```bash
rail handoff --for generic
rail handoff --for chatgpt
rail handoff --for codex
rail handoff --for claude
rail handoff --for cursor
rail handoff --for aider
```

## Export tool files

```bash
rail export --dry-run
rail export
```

Generated files:

```text
AGENTS.md
CLAUDE.md
AIDER.md
.cursor/rules/ai-rail.mdc
.github/copilot-instructions.md
```

## Demo

```bash
rail demo
cd examples/demo-todo
rail init --stack node --project-name "AI Rail Demo TODO"
rail doctor
npm run check
gh issue create --title "Add todo body validation" --body-file issues/001-add-body-validation.md
rail next --copy
```
