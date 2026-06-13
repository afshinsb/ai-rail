## Goal

Return 404 when deleting a missing todo.

## Current problem

DELETE /todos/:id always returns 200 even when the todo does not exist.

## Scope

- Detect whether a todo existed before deletion.
- Return 404 if not found.

## Acceptance checks

- `npm run check` passes.
- Missing delete returns 404.
- Existing delete returns 200.

## Codex rules

- Keep scope small.
- Touch only server.js.
- Do not commit.
