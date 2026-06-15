# Commands

## Daily Commands

AI Rail is a local CLI. It gives the current repo a project brain and a one-issue-at-a-time workflow for AI coding tools.

`.rail/PROJECT.md` is the full local project memory and roadmap brain. The GitHub roadmap issue is the permanent remote `.rail/PROJECT.md` mirror, should be labeled `ai-rail-roadmap`, and stays open. GitHub implementation issues are only the active execution queue and close after shipping.

On first import, `rail import` replaces the placeholder project-memory template with the imported managed roadmap memory. Later imports update only the managed block and preserve human notes outside the markers.

Imported project memory must contain one Rail-readable `AI RAIL ROADMAP START/END` block. Task lines use `TASK_ID | ISSUE | TITLE`, such as `P1-T01 | #123 | Title` or `P1-T02 | TBD | Title`. The roadmap block must not list the roadmap mirror issue itself as a task; the mirror issue is the container for PROJECT.md memory, not implementation work. `rail doctor` warns when `.rail/PROJECT.md` is missing that block or has malformed task lines, duplicate task IDs, duplicate issue refs, invalid phase statuses, multiple active phases, or a roadmap mirror issue listed as a normal task.

| Command | Purpose |
|---|---|
| `rail init` | Install AI Rail files into the current repo |
| `rail upgrade` | Refresh repo-local AI Rail runtime/template files safely |
| `rail doctor` | Check setup, placeholders, and required AI contract files |
| `rail resume` | Show active state and workflow position |
| `rail plan` | Generate a GitHub-connected AI prompt to create a phased issue roadmap |
| `rail import` | Import the GitHub roadmap issue memory into local `.rail/PROJECT.md` |
| `rail phase` | Generate a GitHub-connected AI prompt to audit/update the current roadmap phase |
| `rail next` | Start the next issue and generate the first coding prompt |
| `rail handoff` | Generate portable context for another AI session/model |
| `rail verify` | Write a review pack, run checks, and generate an audit prompt |
| `rail ship` | Commit the issue branch, merge/push the default branch, then close and mark done |
| `rail snapshot` | Refresh `.rail/brain/` project-brain files |
| `rail export` | Generate AI tool instruction files from the project brain |

## Short Aliases

Aliases are thin wrappers over existing commands.

| Alias | Expands to |
|---|---|
| `rail r` | `rail resume` |
| `rail n` | `rail next --copy` |
| `rail p` | `rail plan --copy` |
| `rail ph` | `rail phase --copy` |
| `rail im` | `rail import` |
| `rail v` | `rail verify --copy` |
| `rail s` | `rail ship` |
| `rail snap` | `rail snapshot` |
| `rail h` | `rail handoff --for generic --copy` |
| `rail hc` | `rail handoff --for codex --copy` |
| `rail hg` | `rail handoff --for chatgpt --copy` |
| `rail hl` | `rail handoff --for claude --copy` |
| `rail x` | `rail export` |
| `rail xd` | `rail export --dry-run` |
| `rail xf` | `rail export --force` |
| `rail rc` | `rail release-check` |

## Public And Demo Commands

| Command | Purpose |
|---|---|
| `rail demo` | Print the public demo walkthrough |
| `rail about` | Print project, author, repository, website, and license information |
| `rail release-check` | Verify packaging/docs readiness |

## Advanced Commands

These remain available when you want manual control:

| Command | Purpose |
|---|---|
| `rail status` / `rail active` | Show active issue and workflow position |
| `rail issue-list` | List GitHub issues for the configured repo |
| `rail issue-template` | Print the standard issue body template |
| `rail issue-create` | Create a GitHub issue with `gh` |
| `rail issue-comment` | Comment on the active GitHub issue |
| `rail start` | Start an issue by number, `next`, or `latest` (also accepts `lastest` as a backward-compatible typo alias) |
| `rail prompt codex` | Generate an implementation prompt |
| `rail prompt review` | Generate an audit/review prompt |
| `rail patch` | Apply a local `.patch` file |
| `rail review` | Capture changed files and review context |
| `rail checks` | Run configured or supplied checks |
| `rail commit` | Safely stage changed paths, commit, and push |
| `rail issue-close` | Close the active GitHub issue |
| `rail pr-create` | Create a PR for the active issue |
| `rail done` | Finish local AI Rail state |
| `rail sync` | Checkout the default branch and pull, after checking that `.rail/rail.py` is tracked there |
| `rail repo` | Print the detected GitHub repository |
| `rail log` | Show recent AI Rail history |
| `rail report` | Summarize local AI Rail history |
| `rail ci-init` | Generate a GitHub Actions workflow from configured checks |

## Runtime Upgrade

Existing initialized repos can refresh their copied local runtime after installing a newer AI Rail version:

```bash
rail upgrade
```

`rail upgrade` preserves `.rail/config.json`, project/user files such as `.rail/PROJECT.md` and AI guidance files, `.rail/state/`, `.rail/reports/`, and `.rail/prompts/` while updating template-managed files such as `.rail/rail.py`.

Use `rail upgrade --refresh-config` to also re-detect safe config defaults such as repository, default branch, and checks.

## Init Safety

`rail init` inspects Git before writing files. On a clean repo it initializes normally. On a dirty repo it stops and reports the current branch, default branch, dirty/deleted/untracked counts, existing `.rail/`, and legacy workflow artifacts.

Use `rail init --allow-dirty` to initialize anyway without hiding the dirty state. Use `rail init --adopt-dirty` when the current dirty branch is the intended baseline and you plan to commit the Rail files and existing work together. Use `rail init --clean-default` for first setup that must happen only on a clean default branch.

## Common Workflows

### Normal Implementation

```bash
rail next --copy
rail verify --copy
rail ship "fix(scope): message"
```

`rail verify` runs checks and saves a verified snapshot of the reviewed diff. `rail ship` trusts that snapshot when the working tree still matches it, so the normal ship path does not rerun checks. Use `rail ship --recheck "fix(scope): message"` when you intentionally want checks rerun during ship. The review guard, dangerous-path guard, and explicit escape hatches such as `--allow-missing-checks`, `--allow-stale`, and `--force` still apply.

By default, `rail ship` means the issue branch is integrated into the configured default branch. It commits and pushes the issue branch, verifies the default branch and `.rail/rail.py`, checks out and pulls the default branch, merges the issue branch, pushes the default branch, then closes the issue and clears active state. If the merge conflicts, the issue remains open and active state remains. If `.rail/` is not tracked on the default branch, ship pauses before checkout so `.rail/rail.py`, `.rail/PROJECT.md`, `.rail/config.json`, and local state folders are not removed.

`rail ship --no-push`, `rail ship --no-sync`, and `rail ship --no-merge` are pause/manual modes. `--no-push` commits locally but pauses before issue-close/done because the branch was not pushed. These modes do not close the issue or clear active state unless the default branch was integrated and pushed; merge and push manually before running `rail issue-close --commit && rail done && rail sync`.

### Run A Focused Check

```bash
rail checks --run "npm run typecheck"
rail checks --run "npm run typecheck" --run "npm run lint"
```

For Node repos, `rail init --stack node` inspects `package.json` scripts and chooses the first available script from `check`, `lint`, `typecheck`, then `test`. `rail doctor` warns when the configured default `npm run check` does not exist and a better script is available.

### Continue In A New AI Chat

```bash
rail handoff --for chatgpt --include-review --include-checks --copy
```

### Update AI Tool Files

```bash
rail snapshot
rail export
```

Privacy note: `rail snapshot`, handoff, and `rail export` can include active issue body text, project state, current task details, changed file names, and generated `.rail/brain/` context. Review generated files before sharing or committing them.

### Generate CI Workflow From Configured Checks

```bash
rail ci-init
```

See [WORKFLOWS.md](WORKFLOWS.md) for the three interaction models and when to use each one.
