# AI Rail Three Interaction Models

## Model 1: Codex-Based

ChatGPT plans/reviews. Codex, Claude Code, Cursor, Aider, or another coding agent edits locally. You validate and ship through AI Rail.

Use for larger or multi-file work.

## Model 2: Patch-Based

ChatGPT writes a `.patch`. You apply it locally with AI Rail.

Use for small, surgical edits.

## Model 3: AI-Direct / GitHub-Direct

ChatGPT or another AI tool changes GitHub directly.

Use only for low-risk docs, config, or small static changes unless risk is explicitly accepted.

Mandatory: if AI changes GitHub, it must provide exact local fetch/pull commands.
