# This repo uses AI Rail

AI Rail is a local-first workflow rail for AI-assisted development.

It turns GitHub Issues into controlled loops:

```text
Issue -> Start -> Prompt -> Edit/Patch/AI-direct -> Review -> Checks -> Audit -> Commit/PR -> Close -> Done -> Sync/Pull
```

## Daily loop

```bash
rail resume
rail next --copy
# paste/run the generated prompt in your AI coding tool
rail verify --copy
# paste the generated review prompt into ChatGPT/Claude for audit
rail ship "type(scope): message"
```

## Detailed manual flow

```bash
rail status
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

## Three interaction models

- Model 1: Codex-based. A coding agent edits locally.
- Model 2: Patch-based. ChatGPT gives a patch; you apply locally.
- Model 3: AI-direct / GitHub-direct. AI changes GitHub directly; you fetch/pull locally.

See `.rail/THREE_MODELS.md`.

## Portable project brain

Use `rail snapshot` to refresh `.rail/brain/`. Use `rail handoff --for chatgpt|codex|claude|cursor|aider --copy` when switching to a new AI session or model. Use `rail export` to update root AI tool files such as `AGENTS.md`, `CLAUDE.md`, Cursor rules, `AIDER.md`, and Copilot instructions from the same project brain.
