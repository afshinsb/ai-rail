# AI Rail Demo TODO Script

This is the public demo flow for AI Rail.

## Setup

```bash
pipx install ai-rail
rail --version
rail init --stack node --project-name "AI Rail Demo TODO"
rail doctor
npm run check
```

## Create sample issue

For a brand-new app, start with a roadmap prompt:

```bash
rail plan --copy
# paste into a GitHub-connected AI agent
```

After the AI creates or updates the roadmap issue and first issue slice:

```bash
rail import
# import the roadmap issue into .rail/PROJECT.md
```

For this demo, create one sample issue directly:

```bash
gh issue create --title "Add todo body validation" --body-file issues/001-add-body-validation.md
```

## Run AI Rail loop

```bash
rail next --copy
# paste the prompt into an AI coding tool
rail verify --copy
# paste the review prompt into an AI reviewer for audit
rail handoff --for chatgpt --include-review --include-checks --copy
rail ship "fix(api): add todo body validation"
```

## Audit the phase

```bash
rail phase --copy
# paste into a GitHub-connected AI reviewer/agent
rail import
# refresh .rail/PROJECT.md from the roadmap issue
```

## Export project brain

```bash
rail snapshot
rail export --dry-run
rail export
```
