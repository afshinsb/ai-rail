## Goal

Validate POST /todos request bodies.

## Current problem

POST /todos always creates an Untitled todo.

## Scope

- Parse JSON request body.
- Require a non-empty string `title`.
- Return 400 for invalid input.

## Out of scope

- No database.
- No frontend.
- No auth.

## Acceptance checks

- `npm run check` passes.
- POST /todos with invalid body returns 400.
- POST /todos with valid title returns 201.

## Codex rules

- Keep scope small.
- Touch only server.js.
- Do not commit.
