# Quickstart

AI Rail gives your repo a portable project brain and a short daily workflow for AI-assisted development.

## Install

Public install:

```bash
pipx install ai-rail
rail --version
```

Contributor install from source checkout:

```bash
git clone https://github.com/afshinsb/ai-rail.git
cd ai-rail
python -m pip install -e ".[dev]"
rail --version
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

For a new repo with no scoped GitHub Issues yet, generate a planning prompt first:

```bash
rail plan --copy
# paste into a GitHub-connected AI agent
```

That AI should create a phased roadmap issue and a first batch of small implementation issues.
It should also fill `.rail/PROJECT.md` as local project memory: product, stack, current state, target state, phased roadmap, blockers, and next recommended task.

```bash
rail next --copy
# paste/run the generated prompt in your AI coding tool
rail verify --copy
# paste the generated review prompt into an AI reviewer for audit
rail ship "type(scope): message"
```

After several shipped issues, audit and update the roadmap phase:

```bash
rail phase --copy
# paste into a GitHub-connected AI reviewer/agent
```

Phase audit updates `.rail/PROJECT.md`, keeps the GitHub roadmap issue aligned, and recommends the next phase or blocker issue. `rail next` still starts one task at a time.

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
