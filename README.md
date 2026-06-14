# AI Rail

[![Tests](https://github.com/afshinsb/ai-rail/actions/workflows/tests.yml/badge.svg?branch=master)](https://github.com/afshinsb/ai-rail/actions/workflows/tests.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](docs/RELEASE.md)

**AI Rail is a local CLI for keeping AI coding work scoped, reviewable, and easy to resume.**

AI coding agents can drift, edit too much, skip checks, or lose context between chats. AI Rail gives your Git repo a local project brain and a safe one-issue-at-a-time workflow, so tools like ChatGPT, Codex, Claude, Cursor, and Aider can work from the same source of truth.

It is not a hosted service and it does not run AI models. It runs on your machine, shells out to `git`, `gh`, and your local checks, and gives you paste-ready prompts for the AI tools you already use.

```bash
pipx install ai-rail
rail init
rail plan --copy
rail import
rail n
rail v
rail s "type(scope): message"
```

<p align="center">
  <img src="docs/assets/ai-rail.png" alt="AI Rail overview" width="900">
</p>

## Alpha Status

AI Rail is public alpha software. It is intended for developers who are comfortable with Git, GitHub Issues, and local command-line tools. The default workflow is conservative: it tries to protect your repo from stale reviews, stale checks, unsafe files, and accidental broad changes.

## Install

Prerequisites:

- Python 3.10+ and [pipx](https://pipx.pypa.io/)
- [Git](https://git-scm.com/)
- [GitHub CLI (`gh`)](https://cli.github.com/) installed and authenticated with `gh auth login`

Recommended public install:

```bash
pipx install ai-rail
rail --version
rail demo
```

If `pipx` is not installed yet:

```bash
python -m pip install --user pipx
python -m pipx ensurepath
```

Restart your terminal, then run:

```bash
pipx install ai-rail
```

Latest source from GitHub:

```bash
pipx install git+https://github.com/afshinsb/ai-rail.git
rail --version
```

Contributor install from this source checkout:

```bash
git clone https://github.com/afshinsb/ai-rail.git
cd ai-rail
python -m pip install -e ".[dev]"
rail --version
```

## 5-Minute Demo

Print the built-in walkthrough:

```bash
rail demo
```

Try the bundled demo app:

```bash
cd examples/demo-todo
rail init --stack node --project-name "AI Rail Demo TODO"
rail doctor
npm run check
gh issue create --title "Add todo body validation" --body-file issues/001-add-body-validation.md
rail n
```

`rail n` starts the next issue and copies the implementation prompt when clipboard support is available. Paste that prompt into your AI coding tool.

## Normal Workflow

Inside a Git repo, initialize AI Rail:

```bash
rail init --stack node --project-name "My Project"
rail doctor
rail resume
```

For a new repo with no scoped GitHub Issues yet, create the roadmap and first issue slice:

```bash
rail plan --copy
# paste into a GitHub-connected AI agent
rail import
```

Then work one issue at a time:

```bash
rail n
# paste/run the generated prompt in your AI coding tool

rail v
# paste the generated review prompt into an AI reviewer

rail s "type(scope): message"
```

After several shipped issues, ask a planning/review AI to audit the phase, update the roadmap issue, and create the next slice:

```bash
rail phase --copy
# paste into a GitHub-connected AI reviewer/agent
rail import
rail n
```

Long command names are available too:

```bash
rail next --copy
rail verify --copy
rail ship "type(scope): message"
```

## Core Commands

| Command | Purpose |
|---|---|
| `rail init` | Add AI Rail files to the current repo |
| `rail resume` | Show where you stopped |
| `rail plan` | Generate a GitHub-connected AI prompt to create a phased issue roadmap |
| `rail import` | Import the GitHub roadmap issue into local `.rail/PROJECT.md` |
| `rail phase` | Generate a prompt to audit/update the current roadmap phase |
| `rail next` / `rail n` | Start the next issue and generate the first coding prompt |
| `rail verify` / `rail v` | Capture review info, run checks, and generate an audit prompt |
| `rail ship` / `rail s` | Commit the issue branch, merge/push default, close the issue, and mark done |
| `rail handoff` | Generate portable context for another AI session/model |
| `rail snapshot` | Refresh `.rail/brain/` project-brain files |
| `rail export` | Generate `AGENTS.md`, `CLAUDE.md`, Cursor rules, `AIDER.md`, and Copilot instructions |
| `rail demo` | Print the public demo walkthrough |
| `rail release-check` | Check packaging/docs readiness |

Common aliases are thin wrappers over the long commands: `rail r` for `resume`, `rail n` for `next --copy`, `rail p` for `plan --copy`, `rail ph` for `phase --copy`, `rail im` for `import`, `rail v` for `verify --copy`, `rail s` for `ship`, `rail snap` for `snapshot`, `rail h`/`hc`/`hg`/`hl` for handoffs, `rail x`/`xd`/`xf` for exports, and `rail rc` for `release-check`.

Detailed commands such as `rail start`, `rail prompt`, `rail review`, `rail checks`, `rail commit`, `rail issue-close`, `rail done`, and `rail sync` remain available for manual control.

For Node repos, `rail init --stack node` inspects `package.json` scripts and chooses the first available check command from `check`, `lint`, `typecheck`, then `test`. You can override checks manually:

```bash
rail checks --run "npm run typecheck"
rail checks --run "npm run typecheck" --run "npm run lint"
```

## Safety Model

AI Rail is designed for small, reviewable steps:

- `rail next` starts one GitHub issue at a time.
- `rail verify` captures the reviewed diff, runs configured local checks, and saves a verified snapshot.
- `rail ship` trusts that snapshot only when the working tree and configured checks still match.
- `rail ship` closes the GitHub issue only after default-branch integration succeeds.
- Dangerous or generated paths such as `.env`, keys, local databases, `node_modules/`, `dist/`, `.rail/brain/`, and `.rail/state/` are blocked by default.

Use `rail ship --recheck "type(scope): message"` when you intentionally want checks rerun during ship. Escape hatches exist for advanced users, but the normal path is intentionally conservative.

## Project Brain, Handoff, And Export

`.rail/PROJECT.md` is the local project memory and roadmap brain. The GitHub roadmap issue is the remote roadmap mirror. GitHub implementation issues are the active execution queue, not the whole long-term roadmap.

`rail snapshot` writes portable context into:

```text
.rail/brain/PROJECT.md
.rail/brain/CURRENT_TASK.md
.rail/brain/STATUS.md
.rail/brain/RECENT_HISTORY.md
.rail/brain/HANDOFF.md
```

Use handoff when switching tools or opening a new chat:

```bash
rail snapshot
rail handoff --for chatgpt --include-review --include-checks --copy
```

Use export when you want tool-specific instruction files from the same project brain:

```bash
rail export --dry-run
rail export
```

Generated targets:

```text
AGENTS.md
CLAUDE.md
AIDER.md
.cursor/rules/ai-rail.mdc
.github/copilot-instructions.md
```

Exports are guarded. AI Rail updates its own managed block when markers are present, but refuses to overwrite existing human files unless you pass `--force`, which first writes a numbered `.rail.bak.N` backup.

## Privacy

AI Rail does not send your code anywhere by itself. It shells out to `git`, `gh`, and your configured local checks. You decide what generated prompts, handoffs, review packs, and exports to paste into AI tools.

Privacy note: `rail snapshot`, handoff, and `rail export` can include active issue body text, project state, current task details, changed file names, and generated `.rail/brain/` context. Review generated files before sharing or committing them.

Security note: `rail verify` and `rail checks` run the check commands configured in `.rail/config.json` using the system shell. Always review `.rail/config.json` in repositories you did not author before running them.

By default, `.rail/state/history.jsonl` is ignored by git to avoid committing personal workflow history into team repos.

## Who This Is For

AI Rail is for developers who:

- use one or more AI coding tools on the same repo
- want GitHub Issues to be the task source of truth
- want repeatable prompts, review packs, checks, and handoffs
- prefer local-first tooling over hosted workflow state
- work solo or in small repos where conservative commit safety matters

AI Rail is not an AI model, agent runtime, hosted service, replacement for Git, or replacement for your test suite.

## Docs

- [Quickstart](docs/QUICKSTART.md)
- [Install](docs/INSTALL.md)
- [Commands](docs/COMMANDS.md)
- [Workflows](docs/WORKFLOWS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Release checklist](docs/RELEASE.md)
- [Roadmap](docs/ROADMAP.md)

## Author

- Afshin Saberi
- GitHub: https://github.com/afshinsb
- Website: https://theafshin.com

## License

Apache License 2.0.
