# Agent Guidance

This repository builds AI Rail, the installable `rail` CLI for the `ai-rail` package.

## Contribution Rules

- Preserve the public command name: `rail`.
- Preserve the package name: `ai-rail`.
- Do not bump the version unless the task explicitly asks for a release/version change.
- Do not rename commands or redesign the workflow without an explicit product decision.
- Do not remove safety checks around review freshness, checks freshness, dangerous paths, or generated state.
- Do not modify generated `.rail/state/` files. Template files under `src/ai_rail/template/.rail/` are source files and may be edited when the task is about shipped defaults.
- Keep changes small and scoped to the request.
- Prefer documentation and tests that describe current behavior over broad refactors.

## Repo Map

- `src/ai_rail/cli.py` is the public wrapper CLI.
- `src/ai_rail/template/.rail/rail.py` is the repo-local workflow runtime copied by `rail init`.
- `src/ai_rail/template/.rail/` contains the template AI contract files installed into user repos.
- `docs/QUICKSTART.md` is the fast path for users.
- `docs/COMMANDS.md` is the command reference.
- `docs/WORKFLOWS.md` is the canonical home for the three interaction models.
- `docs/ARCHITECTURE.md` explains the public wrapper, repo-local runtime, generated brain, and exports.

## Verification

For documentation-only cleanup, run at least:

```bash
python -m pytest -q
```

For CLI/runtime edits, also run targeted manual commands in a temporary initialized repo when practical.
