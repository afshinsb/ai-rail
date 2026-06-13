# Commands

## Daily Commands

| Command | Purpose |
|---|---|
| `rail init` | Install AI Rail files into the current repo |
| `rail upgrade` | Refresh repo-local AI Rail runtime/template files safely |
| `rail doctor` | Check setup, placeholders, and required AI contract files |
| `rail resume` | Show active state and workflow position |
| `rail next` | Start the next issue and generate the first prompt |
| `rail handoff` | Generate model-specific portable context |
| `rail verify` | Write a review pack, run checks, and generate an audit prompt |
| `rail ship` | Commit, push, close the issue, mark done, and sync |
| `rail snapshot` | Refresh `.rail/brain/` |
| `rail export` | Generate AI tool instruction files |

## Short Aliases

Aliases are thin wrappers over existing commands.

| Alias | Expands to |
|---|---|
| `rail r` | `rail resume` |
| `rail n` | `rail next --copy` |
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
| `rail start` | Start an issue by number, `next`, `latest`, or `lastest` |
| `rail prompt codex` | Generate an implementation prompt |
| `rail prompt review` | Generate an audit/review prompt |
| `rail patch` | Apply a local `.patch` file |
| `rail review` | Capture changed files and review context |
| `rail checks` | Run configured or supplied checks |
| `rail commit` | Safely stage changed paths, commit, and push |
| `rail issue-close` | Close the active GitHub issue |
| `rail pr-create` | Create a PR for the active issue |
| `rail done` | Finish local AI Rail state |
| `rail sync` | Checkout the default branch and pull |
| `rail repo` | Print the detected GitHub repository |
| `rail log` | Show recent AI Rail history |
| `rail report` | Summarize local AI Rail history |
| `rail ci-init` | Generate a GitHub Actions workflow from configured checks |

## Runtime Upgrade

Existing initialized repos can refresh their copied local runtime after installing a newer AI Rail version:

```bash
rail upgrade
```

`rail upgrade` preserves `.rail/config.json`, `.rail/state/`, `.rail/reports/`, and `.rail/prompts/` while updating template-managed files such as `.rail/rail.py`.

## Common Workflows

### Normal Implementation

```bash
rail next --copy
rail verify --copy
rail ship "fix(scope): message"
```

### Continue In A New AI Chat

```bash
rail handoff --for chatgpt --include-review --include-checks --copy
```

### Update AI Tool Files

```bash
rail snapshot
rail export
```

### Generate CI Workflow From Configured Checks

```bash
rail ci-init
```

See [WORKFLOWS.md](WORKFLOWS.md) for the three interaction models and when to use each one.
