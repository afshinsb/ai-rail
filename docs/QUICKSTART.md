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

Use `rail upgrade --refresh-config` when you also want to re-detect safe config defaults such as repository, default branch, and checks.

Stack presets:

```bash
rail init --stack node
rail init --stack python
rail init --stack static
```

If the repo already has uncommitted work, `rail init` pauses before writing files. Use `rail init --allow-dirty` to initialize anyway, `rail init --adopt-dirty` to treat the current dirty branch as the intended baseline, or `rail init --clean-default` when setup must happen only on a clean default branch.

## Daily loop

For a new repo with no scoped GitHub Issues yet, generate a planning prompt first:

```bash
rail plan --copy
# paste into a GitHub-connected AI agent
```

That AI should create a phased roadmap issue and all issues for the first active execution slice.
It should put the full project memory and roadmap in the GitHub roadmap issue. Import that remote roadmap mirror locally:

```bash
rail import
```

`.rail/PROJECT.md` is the full local project memory and roadmap brain. GitHub Issues are only the active execution queue.

```bash
rail next --copy
# paste/run the generated prompt in your AI coding tool
rail verify --copy
# paste the generated review prompt into an AI reviewer for audit
rail ship "type(scope): message"
```

`rail verify` runs checks and saves a verified snapshot. `rail ship` ships only if the working tree still matches that snapshot, and normally does not rerun checks. Use `rail ship --recheck "type(scope): message"` to force a check rerun during ship.

For Node repos, `rail init --stack node` chooses the first available `package.json` script from `check`, `lint`, `typecheck`, then `test`. You can run focused checks directly:

```bash
rail checks --run "npm run typecheck"
```

After several shipped issues, audit and update the roadmap phase:

```bash
rail phase --copy
# paste into a GitHub-connected AI reviewer/agent
```

Phase audit asks the planning AI to update the GitHub roadmap issue and create all issues for the next active execution slice. `rail next` still starts one task at a time.

```bash
rail import
# refresh .rail/PROJECT.md after phase planning
rail next --copy
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
