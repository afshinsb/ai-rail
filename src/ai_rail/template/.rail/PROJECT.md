# Project Memory

This file is the local AI Rail project memory and roadmap brain.

GitHub Issues are the active task execution queue.
The GitHub roadmap issue is the remote roadmap mirror.
AI/planning agents create and update the roadmap.
AI Rail imports roadmap memory and tracks completed issue state.

## Product notes

CHANGE_ME: What does this project do?

## Stack

CHANGE_ME: Main technologies, framework, runtime, database, deployment target.

## Non-negotiables

CHANGE_ME: Constraints, architecture rules, safety rules, and things AI must not break.

<!-- AI RAIL MANAGED ROADMAP START -->

## Roadmap

The strict block below is the only Rail-readable task status source.
Free-form context may appear outside it, but Rail only edits task status inside `AI RAIL ROADMAP`.

<!-- AI RAIL ROADMAP START -->

## Phase P1 - Foundation
Status: active

### Goal
CHANGE_ME: Describe the current phase goal.

### Completion criteria
- CHANGE_ME: Define what makes this phase complete.

### Tasks
- [ ] TBD | P1-T01 | CHANGE_ME: First scoped task title
- [ ] TBD | P1-T02 | CHANGE_ME: Second scoped task title

## Phase P2 - Next phase
Status: planned

### Goal
CHANGE_ME: Describe the next phase goal.

### Completion criteria
- CHANGE_ME: Define what makes this phase complete.

### Tasks
- [ ] TBD | P2-T01 | CHANGE_ME: Future scoped task title

<!-- AI RAIL ROADMAP END -->

<!-- AI RAIL MANAGED ROADMAP END -->

## Roadmap maintenance rules

- Keep exactly one `AI RAIL ROADMAP START/END` block.
- Every task line in that block must be `- [ ] ISSUE | TASK_ID | TITLE` or `- [x] ISSUE | TASK_ID | TITLE`.
- `ISSUE` must be `#123` for active GitHub issues or `TBD` for future tasks.
- `TASK_ID` must look like `P1-T01`, `P2-T03`, and must be unique.
- Phase `Status:` must be `planned`, `active`, `complete`, or `blocked`.
- Do not use numbered lists for task status in the strict block.
- Do not duplicate task status elsewhere as a second source of truth.
- Keep only the active execution slice as GitHub implementation issues.
- Do not create `.rail/ROADMAP.md`.
- Do not use GitHub Issues for the entire roadmap.
- Use `rail import` after `rail plan --copy` or `rail phase --copy`.
- Use `rail s` to ship/close one issue and mark it completed locally.
