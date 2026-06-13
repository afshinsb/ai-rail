# AI Contract

This repo is managed by AI Rail.

Model 1 normal workflow:

```text
Create GitHub issue -> rail next --copy -> paste prompt into Codex/Claude/Cursor/Aider -> agent edits only issue scope -> rail verify --copy -> ChatGPT review -> rail ship
```

ChatGPT is the planner/reviewer/workflow controller. The coding agent edits locally and stays scoped to the active issue.

Rules:

1. Work only on the active GitHub issue or explicitly requested task.
2. Do not create root task folders.
3. Do not create root `ROADMAP.md`.
4. Keep roadmap/current direction in `.rail/PROJECT.md`.
5. Short terminal commands go in chat.
6. Long commands go in downloadable `.txt` or `.md` files.
7. AI-direct GitHub changes must always include local fetch/pull commands.
8. Every response ends with exact next terminal commands.
9. Coding agents do not commit, close issues, or run broad/full test suites unless the issue explicitly asks for them.
10. Coding agents run only focused checks related to the issue, or the exact checks requested by the user or AI Rail.
11. Do not read or modify `.rail/rail.py`, `.rail/state/`, or `Makefile` unless the issue is specifically about AI Rail/tooling.
12. Stop and explain if the task requires broader architecture or extra files.

Model 2 patch workflow: create or choose issue -> ask ChatGPT for a surgical patch -> apply patch locally -> `rail verify --copy` -> ChatGPT review -> `rail ship`.

Model 3 AI-direct workflow is for low-risk docs/config/static changes unless risk is explicitly accepted. AI must state Model 3, change only requested GitHub files, provide `git fetch origin`, `git pull --ff-only`, and `git status`, and tell the user to run `rail verify --copy` after pulling.
