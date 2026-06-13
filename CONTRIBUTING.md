# Contributing

Project goals:

- keep AI Rail local-first
- keep the CLI small
- keep GitHub Issues as the task database
- keep AI workflows explicit and auditable

## Setup

```bash
pip install -e ".[dev]"
```

## Tests

Run the full test suite:

```bash
python -m pytest -q
```

Also run the basic CLI checks:

```bash
python -m py_compile src/ai_rail/cli.py
python -m ai_rail --version
```

## Before opening a PR

```bash
python -m pytest -q
python -m py_compile src/ai_rail/cli.py
```
