## Goal

Add a small health endpoint.

## Current problem

There is no simple endpoint to confirm the demo server is alive.

## Scope

- Add GET /health.
- Return `{ "ok": true }`.

## Acceptance checks

- `npm run check` passes.
- GET /health returns 200.

## Codex rules

- Keep scope small.
- Touch only server.js.
- Do not commit.
