# Changelog

Maintained by Afshin Saberi.

## 0.1.0a14

- Slimmed Model 1 coding prompts to reduce token use and scope drift.
- Removed default `.rail/PROJECT.md` and `.rail/AGENTS.md` reads from coding prompts.
- Added expected-files and hard-scope sections to coding prompts.
- Clarified that coding agents should not run tests by default; humans verify with `rail v`.
- Clarified strict Rail-readable roadmap prompt boundaries.
- No breaking changes.

## 0.1.0a13

- Cleaned `.rail/PROJECT.md` import behavior so default placeholder sections are removed after successful roadmap import.
- Preserved real human notes outside managed roadmap markers.
- Updated planning and phase prompts to replace managed memory blocks instead of appending duplicates.
- Improved doctor/import behavior around stale `CHANGE_ME` placeholders.
- No breaking changes.

## 0.1.0a12

- Stabilized the import-based roadmap workflow.
- Fixed `rail ship` rollback so `.rail/PROJECT.md` is restored if the ship commit fails.
- Fixed generated demo ordering so `rail import` runs after the planning AI updates the roadmap issue.
- Kept `.rail/PROJECT.md` as the local roadmap brain and GitHub Issues as the active execution queue.
- No breaking changes.

## 0.1.0a11

- Added `rail plan` to generate a GitHub-connected AI prompt for phased roadmap creation.
- Added `rail phase` to generate a GitHub-connected AI prompt for phase audits and roadmap updates.
- Added `rail import` / `rail im` for one-way GitHub roadmap issue -> local `.rail/PROJECT.md` import.
- Added AI Rail project-memory managed block markers for roadmap import.
- Added aliases `rail p`, `rail ph`, and `rail im`.
- Changed planning/phase prompts to treat GitHub issues as the active execution queue only.
- Added `.rail/PROJECT.md` completion marking on `rail ship`.
- Updated README, quickstart, commands, workflows, demo, and installed template guidance for the import-based roadmap workflow.
- Added planning-agent rules for right-sized implementation issues.
- No breaking changes.

## 0.1.0a10

- Added README prerequisites for Python, pipx, Git, and authenticated GitHub CLI where missing.
- Made general reviewer wording tool-agnostic instead of ChatGPT-only.
- Improved PyPI project URLs with repository homepage, changelog, and bug tracker links.
- Kept public install first in quickstart/demo guidance.
- Added README security callout for shell-based configured checks.
- Added recovery guidance for partial `rail ship` failures.
- Added warning output when `--force` is used while dangerous paths are present.
- Added installed `.rail/AIDER.md` contract template when missing.
- Documented `lastest` as a backward-compatible typo alias.
- No breaking changes.

## 0.1.0a9

- Added clearer prerequisites and `pipx` install guidance.
- Improved PyPI project URLs for homepage, changelog, and issue tracking.
- Put public install first in quickstart and demo guidance.
- Clarified Model 1, Model 2, and Model 3 workflows and AI reviewer wording.
- Added clearer partial `rail ship` recovery instructions.
- No breaking changes.

## 0.1.0a7

- Made `rail init --force` safer when refreshing initialized repositories.
- Added `rail upgrade` to safely refresh repo-local AI Rail runtime/template files.
- Switched git path parsing to robust `porcelain -z` handling.
- Cleaned up cross-platform CI and documentation readiness.
- Added author/about metadata to public CLI output.
- Finished packaging readiness fixes for the alpha release.

## 0.1.0a6

- Added `rail demo` to print a copyable public demo walkthrough.
- Added `rail release-check` to validate public-alpha packaging and docs readiness.
- Added `docs/QUICKSTART.md`, `docs/COMMANDS.md`, and `docs/RELEASE.md`.
- Added `examples/demo-todo/DEMO_SCRIPT.md` and updated the demo README.
- Added a package test workflow under `.github/workflows/tests.yml`.
- Updated README and install docs for the final public-alpha workflow.
- Made repo detection during `rail init` prefer fast local git remote detection before falling back to `gh`.

## 0.1.0a5

- Added `rail export` to generate tool-specific context files from the AI Rail project brain.
- Added exports for root `AGENTS.md`, root `CLAUDE.md`, root `AIDER.md`, `.cursor/rules/ai-rail.mdc`, and `.github/copilot-instructions.md`.
- Added safe managed-block updates using `AI_RAIL_EXPORT` markers.
- Refuse to overwrite existing unmarked human files unless `--force` is used, with `.rail.bak` backups.
- Added `--target`, `--dry-run`, `--force`, `--no-snapshot`, and `--max-history` options for exports.
- Updated tests and docs for the one-project-brain/many-tool-files workflow.

## 0.1.0a4

- Added `rail snapshot` to generate a portable project brain under `.rail/brain/`.
- Added `rail handoff` to create paste-ready model-specific handoffs for ChatGPT, Codex, Claude, Cursor, Aider, or generic AI sessions.
- Added optional handoff inclusion for last review pack and last checks output.
- Saved handoff outputs under `.rail/state/last-handoff-*.md`.
- Updated docs and tests for the portable project brain workflow.

## 0.1.0a3

- Added commit/ship safety preflight requiring a fresh review pack and passed fresh checks by default.
- Added dangerous/generated path guard for `.env`, keys, local databases, build outputs, dependencies, caches, and `.rail/state/`.
- Changed commit staging to stage known changed paths instead of blindly staging the whole repository.
- Added small untracked text file contents to review packs so new files are visible during AI audit.
- Added first-push upstream handling with `git push -u origin HEAD` when needed.
- Added `--allow-missing-checks` and `--allow-stale` escape hatches for advanced users.
- Fixed legacy `mode=issue` active-state handling in the public wrapper.
- Aligned the embedded repo-local runtime version with the public alpha version after audit.
- Added Phase 3 regression tests for safety preflight, dangerous files, fresh review/check commit flow, and untracked review contents.

## 0.1.0a2

- Added short daily commands: `rail next`, `rail verify`, `rail ship`, and `rail resume`.
- Updated README/docs/demo templates to lead with the shorter daily workflow.
- Kept detailed legacy workflow commands available for manual control.

## 0.1.0a1

- Renamed project from AI Rail predecessor naming to `AI Rail`.
- Renamed install package to `ai-rail`.
- Renamed CLI entrypoint to `rail`.
- Renamed project state folder to `.rail/`.
- Renamed repo-local runtime file to `.rail/rail.py`.
- Updated docs, examples, templates, tests, and package metadata for the rename.
