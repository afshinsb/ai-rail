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

## Export project brain

```bash
rail snapshot
rail export --dry-run
rail export
```
