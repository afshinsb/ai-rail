from __future__ import annotations


def unconfigured_repository_prompt_warning(repository: str) -> str:
    if repository != "not configured":
        return ""
    return """

STOP: Repository is not configured.
- Do not create or update GitHub issues yet.
- First configure `.rail/config.json` repository or run `rail init --refresh-config`."""


def render_plan_prompt(
    *,
    project_name: str,
    repository: str,
    remote_memory_start: str,
    remote_memory_end: str,
    rail_roadmap_start: str,
    rail_roadmap_end: str,
) -> str:
    return f"""You are a GitHub-connected planning agent for this repository.

Project: {project_name}
Repository: {repository}{unconfigured_repository_prompt_warning(repository)}

Audit the repo enough to understand:
- project purpose
- tech stack
- current features
- missing backend/backbone/configuration
- fake UI or unimplemented controls
- risky/broken areas
- what should be done first

Create or update one GitHub roadmap issue as the remote roadmap mirror, titled:
Roadmap: {project_name} functional MVP

Put the full roadmap/project memory inside the roadmap issue body. Include this exact managed block:

{remote_memory_start}
...
{remote_memory_end}

The managed block should be complete enough to become the useful body of local `.rail/PROJECT.md` after `rail import`.
Do not include `CHANGE_ME`.
Do not duplicate default placeholder sections.
If updating an existing roadmap issue, replace the old managed block instead of appending another one.
If old roadmap content exists outside the managed block, update it only if needed; do not create duplicate roadmap sections.

Inside the managed block, include exactly one strict Rail-readable roadmap block:

{rail_roadmap_start}

## Phase P1 - Foundation / truth alignment
Status: active

### Goal
Plain text phase goal.

### Completion criteria
- Plain text criterion.

### Tasks
- [ ] P1-T01 | #123 | Existing active issue title
- [ ] P1-T02 | TBD | Future task title

{rail_roadmap_end}

Strict roadmap rules:
- Every task line must use exactly one of these forms:
  `- [ ] TASK_ID | ISSUE | TITLE`
  `- [x] TASK_ID | ISSUE | TITLE`
- `TASK_ID` must look like `P1-T01`, `P2-T03`, and be unique.
- `ISSUE` must be `#N` for GitHub issues that exist or `TBD` for future tasks not yet created.
- Legacy issue-first task lines are still accepted by Rail, but new roadmap text should use task-id-first.
- Phase `Status:` must be one of `planned`, `active`, `complete`, or `blocked`.
- Use checkboxes for every task.
- Do not use numbered lists for task status inside the strict block.
- Do not duplicate task status elsewhere as a second source of truth.
- Do not append duplicate roadmap blocks; replace/update the existing block.

AI RAIL PROJECT MEMORY contains human-readable project context:
- product summary
- stack
- non-negotiables
- current state
- target state
- blockers/postponed items
- completed work summary
- next recommended issue/task
- workflow notes

AI RAIL ROADMAP contains only Rail-readable phase/task state:
- phase headings
- Status
- Goal
- Completion criteria
- Tasks
- strict task lines

Do not put product summary, stack, non-negotiables, current state, target state, blockers, completed-work prose, workflow notes, or next-step prose inside AI RAIL ROADMAP.
Do not duplicate task status outside AI RAIL ROADMAP.

Inside the strict roadmap block, include:
- full phased roadmap
- phase goals
- completion criteria
- future tasks/backlog
- current phase
- active execution queue

AI Rail treats `.rail/PROJECT.md` as the local project memory and roadmap brain, but you should update the GitHub roadmap issue first. Do not edit `.rail/PROJECT.md` remotely unless the user explicitly asks.

Structure the roadmap into phases. Example phase styles:
- Phase 1 - Foundation / cleanup / truth alignment
- Phase 2 - Core functionality
- Phase 3 - UI/backbone connection
- Phase 4 - safety/polish/release readiness

Do not force those exact phase names; choose phases that fit this repo.

Create all issues for the first active execution slice/current phase as implementation-ready GitHub Issues:
- usually 3-10 right-sized implementation issues
- do not stop after creating one issue unless the phase truly has one task or GitHub/API failure blocks more
- do not create GitHub issues for the entire long-term roadmap
- assign `#N` issue refs in the strict roadmap block for issues you create
- keep future tasks as `Pn-Txx | TBD | title`
- small enough for one focused coding-agent pass
- big enough to be meaningful
- not tiny/noisy micro-tasks
- not huge phase-sized tasks
- ordered safest/foundation-first
- each issue should produce a clear diff
- avoid vague issues like "improve UI" or "refactor app"
- prefer backbone/config/foundation fixes before polish
- if GitHub blocks long issue bodies, create shorter issue bodies but still create issue shells and insert `#N` refs
- if not all active-slice issues are created, list which tasks remain `TBD` and why

Each implementation issue must include this body template:

## Goal

## Current problem

## Scope

## Out of scope

## Files likely touched

## Acceptance checks

## AI/Codex rules

- Keep scope small.
- Touch only necessary files.
- Do not commit.
- Do not close the issue.
- Do not run tests/checks by default.
- Do not run full suites like npm test, npm run build, or broad integration tests.
- Only run a tiny focused check if there is truly no safe way to finish the task without it.
- If you skip checks, say exactly: "Checks not run; human will run rail v."
- Stop and explain if this requires broader architecture changes.

Task-writing rules:
- One issue should fit one focused coding-agent session.
- Each issue should usually touch a small set of related files.
- Each issue should have enough detail that `rail n` can pass it to a coding agent without re-explaining the project.
- Do not create tiny noisy micro-tasks.
- Do not create huge phase-sized tasks.
- Do not bundle unrelated UI, backend, docs, and config changes into one issue.
- If a phase is large, split it into several scoped issues.
- If the coding agent would need to make architecture decisions, create a planning/audit issue first instead of a coding issue.

Do not:
- implement code
- make commits
- open PRs
- create GitHub issues for the entire future roadmap
- create vague or huge issues

After I create/update the roadmap issue and active execution issues, run `rail import` locally.
AI Rail will import the roadmap issue into local `.rail/PROJECT.md`.
Do not edit `.rail/PROJECT.md` remotely unless the user explicitly asks.

After import, the human will run:

rail n
# paste generated prompt into coding agent

rail v
# paste review prompt into AI reviewer

rail s "type(scope): message"

Implementation happens through the one-issue-at-a-time AI Rail loop."""


def render_phase_prompt(
    *,
    project_name: str,
    repository: str,
    history: str,
    remote_memory_start: str,
    remote_memory_end: str,
    rail_roadmap_start: str,
    rail_roadmap_end: str,
) -> str:
    return f"""You are a GitHub-connected phase-audit agent for this repository.

Project: {project_name}
Repository: {repository}{unconfigured_repository_prompt_warning(repository)}

Inspect the repo and GitHub Issues. Find the roadmap issue, usually titled like:
Roadmap: {project_name} functional MVP

Update the GitHub roadmap issue. Update the managed project-memory block inside the roadmap issue:

{remote_memory_start}
...
{remote_memory_end}

Replace/update the existing managed block. Do not append duplicate managed blocks.
Do not leave stale phase/task sections.
Do not include `CHANGE_ME`.
Inside it, preserve and update exactly one strict `{rail_roadmap_start}` / `{rail_roadmap_end}` block.
Every task line in that block must stay exactly one of these forms:
`- [ ] TASK_ID | ISSUE | TITLE`
`- [x] TASK_ID | ISSUE | TITLE`
Use `#N` for existing GitHub issues and `TBD` for future tasks not yet created.
Legacy issue-first task lines are still accepted by Rail, but new roadmap text should use task-id-first.
Use phase statuses only from: planned, active, complete, blocked.
Do not use numbered lists for task status.
Do not invent alternate task structures.

AI RAIL PROJECT MEMORY contains human-readable project context: product summary, stack, non-negotiables, current state, target state, blockers/postponed items, completed work summary, next recommended issue/task, and workflow notes.
AI RAIL ROADMAP contains only Rail-readable phase/task state: phase headings, Status, Goal, Completion criteria, Tasks, and strict task lines.
Do not put product summary, stack, non-negotiables, current state, target state, blockers, completed-work prose, workflow notes, or next-step prose inside AI RAIL ROADMAP.
Do not duplicate task status outside AI RAIL ROADMAP.

AI Rail will import that roadmap issue into local `.rail/PROJECT.md`; do not edit `.rail/PROJECT.md` remotely unless explicitly asked.

Identify:
- current phase
- completed/closed issues in that phase
- open issues in that phase
- shipped work since the last phase audit

Recent AI Rail history, if available:
{history}

Audit whether the phase is really complete. Check for:
- whether completed issues really satisfy the phase completion criteria
- scope drift
- incomplete tasks
- broken assumptions
- missing tests/checks
- docs mismatch
- fake UI still not backed
- risky shortcuts
- roadmap mismatch

If the phase is complete:
- mark completed task lines as `[x]` in the strict roadmap block
- update phase `Status:` lines in the strict roadmap block
- update completed work, current phase, next recommended issue, and blockers/postponed work in the roadmap issue memory block
- mark or recommend the phase as complete in the GitHub roadmap issue
- recommend or create all issues for the next active execution slice/current phase
- usually create 3-10 right-sized implementation issues
- do not stop after creating one issue unless the slice truly has one task or GitHub/API failure blocks more
- keep new issues right-sized for coding agents

If the phase is not complete:
- list remaining blockers
- create or update only scoped blocker issues
- replace `TBD` with issue numbers when you create all issues for the next active execution slice/current phase
- add future tasks only as `- [ ] Pn-Txx | TBD | title`
- do not start the next phase yet
- if GitHub blocks long issue bodies, create shorter issue bodies but still create issue shells and insert `#N` refs
- if not all active-slice issues are created, list which tasks remain `TBD` and why

Review upcoming phases and decide whether the roadmap is still correct. If it is off-track, update upcoming phases in the GitHub roadmap issue, then clearly tell the user what changed and why.

Right-sized issue rules:
- one focused coding session
- clear diff
- not a micro-task
- not a giant phase-sized task
- no unrelated bundles
- enough detail for `rail next --copy`

Do not:
- implement code
- commit
- open PRs
- close roadmap phases unless the audit supports it
- silently create unrelated tasks
- create issues for the entire future roadmap
- edit `.rail/PROJECT.md` remotely unless explicitly asked

Implementation still happens one issue at a time through:

rail n -> coding agent -> rail v -> reviewer -> rail s

After I update the roadmap issue and active execution issues, run `rail import` locally.
AI Rail will import the updated roadmap issue into local `.rail/PROJECT.md`.

Return:
- phase audit verdict
- completed issue list
- remaining blockers
- roadmap updates made or recommended
- next phase recommendation
- next issue to run with AI Rail"""
