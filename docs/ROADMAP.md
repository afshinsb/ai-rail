# Roadmap

This roadmap records completed product phases and likely future integrations. It is descriptive, not a second command reference.

## Completed

### 0.1.0a1: CLI Foundation

- Installable `rail` package and public command.
- Repo-local `.rail/` runtime copied by `rail init`.

### 0.1.0a2: Short Daily Commands

- `rail resume` shows the current task/workflow position.
- `rail next` starts the next issue and generates the first prompt.
- `rail verify` captures review context, runs checks, and generates an audit prompt.
- `rail ship` commits, closes, finishes local state, and syncs.

### 0.1.0a3: Safety Hardening

- Safer commit staging.
- Dangerous/generated-file guard.
- Fresh-review requirement before commit/ship.
- Fresh-check requirement before commit/ship.
- Untracked text file content in review packs.
- First-push upstream handling.
- Explicit escape hatches: `--allow-missing-checks`, `--allow-stale`, and `--force`.

### 0.1.0a4: Portable Project Brain And Handoff

- `rail snapshot` writes `.rail/brain/PROJECT.md`, `CURRENT_TASK.md`, `STATUS.md`, `RECENT_HISTORY.md`, and `HANDOFF.md`.
- `rail handoff` generates paste-ready handoffs for `chatgpt`, `codex`, `claude`, `cursor`, `aider`, or `generic`.
- Handoffs can include the last review pack and checks output.
- Handoff output is saved under `.rail/state/last-handoff-*.md`.

### 0.1.0a5: Tool-Specific Exports

- `rail export` generates tool-specific files from the project brain.
- Root `AGENTS.md` for Codex-compatible agents.
- Root `CLAUDE.md` for Claude Code.
- `.cursor/rules/ai-rail.mdc` for Cursor.
- Root `AIDER.md` for Aider.
- `.github/copilot-instructions.md` for GitHub Copilot.
- Managed export blocks update safely without overwriting existing human files unless `--force` is used.

### 0.1.0a6: Public Demo And Packaging Readiness

- `rail demo` prints a copyable public demo walkthrough.
- `rail release-check` checks packaging/docs readiness.
- Public quickstart, command reference, release checklist, and workflow docs.
- Demo docs for `examples/demo-todo`.
- Package test workflow for GitHub Actions.

### 0.1.0a11: Import-Based Roadmap Workflow

- `rail plan --copy` generates a prompt for a GitHub-connected planning AI to create or update one roadmap issue and only the first active execution slice.
- `rail import` imports the GitHub roadmap issue into local `.rail/PROJECT.md`.
- `.rail/PROJECT.md` is the full local project memory and roadmap brain.
- The GitHub roadmap issue is the remote roadmap mirror.
- GitHub implementation issues are only the active execution queue, not the full long-term roadmap.
- `rail phase --copy` asks the planning AI to audit/update the roadmap issue and next execution slice.
- `rail ship` marks matching local `.rail/PROJECT.md` checklist tasks complete when possible.

## Possible Future Integrations

- MCP server.
- VS Code helper.
- Richer GitHub issue linting.
- Optional roadmap quality/linting helpers.
