# Workflows

AI Rail supports one daily loop and three interaction models. The short commands are the normal path; the detailed commands remain available when you need manual control.

## Full Lifecycle

`.rail/PROJECT.md` is the full local project memory and roadmap brain. The GitHub roadmap issue is the remote roadmap mirror. GitHub implementation issues are only the active execution queue.

Use `rail plan --copy` before the first coding issue exists. Paste it into a GitHub-connected AI agent so it can audit the repo, create or update one phased roadmap issue, and create only the first active execution slice as scoped GitHub Issues. Then run `rail import` to import the roadmap issue into `.rail/PROJECT.md`.

Use `rail next --copy` after issues exist. It still starts one issue at a time and generates the coding-agent prompt for that single issue.

After `rail s`, AI Rail marks the shipped issue completed locally when it appears in `.rail/PROJECT.md`. After several issues have shipped, use `rail phase --copy` to audit the current roadmap phase. Phase audit is not coding: the planning AI updates the GitHub roadmap issue and creates only the next right-sized execution slice. Then run `rail import` again.

## Daily Loop

```bash
rail next --copy
# paste/run the generated prompt in your AI coding tool
rail verify --copy
# paste the generated review prompt into your AI reviewer for audit
rail ship "type(scope): message"
```

Use `rail resume` before starting if you are returning to a repo after time away. Use `rail handoff --for chatgpt|codex|claude|cursor|aider --copy` when moving the task into another AI session.

## Model 1: Codex-Based

ChatGPT or another planning/review model helps shape the task. Codex, Claude Code, Cursor, Aider, or another coding agent edits locally. You validate and ship through AI Rail.

Use this for larger or multi-file implementation work.

Typical commands:

```bash
rail next --model codex --copy
rail verify --copy
rail ship "type(scope): message"
```

## Model 2: Patch-Based

ChatGPT or another model writes a small `.patch`. You apply it locally through AI Rail, then review and check it before shipping.

Use this for small, surgical edits where a patch is easier to inspect than a long live coding session.

Typical commands:

```bash
rail start ISSUE --model patch
rail patch path/to/change.patch --check-only
rail patch path/to/change.patch
rail verify --copy
rail ship "type(scope): message"
```

## Model 3: AI-Direct / GitHub-Direct

An AI tool changes GitHub directly. Treat this as the highest-risk model because the local checkout can fall behind the remote state.

Use this only for low-risk docs, config, or small static changes unless the human explicitly accepts the risk.

Required rule: if AI changes GitHub directly, it must provide the exact local `git fetch`/`git pull` commands needed to sync the local checkout.

Typical commands:

```bash
rail start ISSUE --model ai-direct --no-branch
# AI performs the GitHub-side change and provides exact sync commands
rail verify --copy
rail done
rail sync
```

## Manual Control

The short commands wrap the detailed workflow:

```bash
rail issue-list
rail start next
rail prompt codex --copy
rail review
rail checks
rail prompt review --copy
rail commit "type(scope): message"
rail issue-close --commit
rail done
rail sync
```
