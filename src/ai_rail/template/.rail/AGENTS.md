# Agent Rules

These rules apply to AI coding agents working in this repository.

## Core rules

- Work only on the active GitHub issue.
- Keep scope small and surgical.
- Touch only necessary files.
- Do not commit.
- Do not close issues.
- Do not run broad/full checks unless explicitly asked.
- Do not rewrite architecture unless the issue explicitly asks.
- Stop and explain if the task requires broader architectural changes.

## AI Rail files

Do not read or modify `.rail/rail.py`, `.rail/state/`, or `Makefile` unless the GitHub issue is specifically about AI Rail/tooling.

For normal app tasks, only read:

- `.rail/AGENTS.md`
- `.rail/PROJECT.md`
- `.rail/CODEX.md`
- the active GitHub issue

## Required final summary

When finished, summarize:

- files changed
- behavior changed
- focused checks run, if any
- remaining risks
