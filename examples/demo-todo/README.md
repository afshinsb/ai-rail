# AI Rail Demo TODO

A tiny Node.js project for trying AI Rail in 5 minutes.

## Install AI Rail

Intended public install after publishing:

```bash
pipx install ai-rail
```

Development install from this source repo:

```bash
# From examples/demo-todo:
pip install -e "../..[dev]"
```

## Print demo script

```bash
rail demo
```

## Setup demo project

From this folder:

```bash
rail init --stack node --project-name "AI Rail Demo TODO"
rail doctor
rail resume
npm run check
```

## Demo issues

The `issues/` folder contains sample issue bodies.

Create one:

```bash
gh issue create --title "Add todo body validation" --body-file issues/001-add-body-validation.md
```

Run the short daily loop:

```bash
rail next --copy
# paste/run the generated prompt in your AI coding tool
rail verify --copy
# paste the generated review prompt into your AI reviewer for audit
rail handoff --for chatgpt --include-review --include-checks --copy
rail ship "fix(api): add todo body validation"
```

Detailed commands are still available if you want manual control:

```bash
rail issue-list
rail start next
rail prompt codex --copy
rail review
rail checks
rail prompt review --copy
rail commit "fix(api): add todo body validation"
rail issue-close --commit
rail done
rail sync
```
