# Install

## Recommended public install

Install the published package with `pipx`:

```bash
pipx install ai-rail
rail --version
rail demo
```

## Latest from GitHub

Use this when you need the latest source before a PyPI release:

```bash
pipx install git+https://github.com/afshinsb/ai-rail.git
rail --version
rail demo
```

## Contributor install

Use an editable install only when working from this source checkout:

```bash
pip install -e ".[dev]"
rail --version
rail demo
```

## Initialize a Git repo

```bash
rail init --stack node --project-name "My Project"
rail doctor
rail resume
```

## Daily loop

```bash
rail next --copy
rail verify --copy
rail ship "type(scope): message"
```

## Portable context

```bash
rail snapshot
rail handoff --for codex --copy
rail handoff --for chatgpt --include-review --include-checks --copy
rail export
```

## Release/build checks

```bash
python -m pytest -q
python -m py_compile src/ai_rail/cli.py
rail release-check
```
