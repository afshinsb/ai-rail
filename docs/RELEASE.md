# Release checklist

AI Rail is currently alpha software. Use this checklist before tagging or publishing.

## Required checks

```bash
python -m pytest -q
python -m py_compile src/ai_rail/cli.py
python -m ai_rail --version
rail release-check
```

## Build package locally

```bash
python -m pip install --upgrade build twine
python -c "import pathlib, shutil; shutil.rmtree('dist', ignore_errors=True); pathlib.Path('dist').mkdir()"
python -m build
python -m twine check dist/*
```

If your terminal does not default to UTF-8, set UTF-8 output before running the test suite when assertions include Unicode output.

macOS/Linux:

```bash
PYTHONIOENCODING=utf-8 python -m pytest -q
```

Windows PowerShell:

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m pytest -q
```

## Inspect package artifacts

Before publishing, inspect the wheel and sdist contents:

- wheel contains `ai_rail/cli.py`, `ai_rail/__main__.py`, and `ai_rail/template/`
- wheel contains `ai_rail-*.dist-info/entry_points.txt` with `rail = ai_rail.cli:main`
- wheel contains the license under `.dist-info/licenses/`
- sdist contains `src/`, `docs/`, `examples/`, `README.md`, `LICENSE`, `CHANGELOG.md`, `SECURITY.md`, and `CONTRIBUTING.md`
- generated state, virtualenvs, caches, and local build scratch files are absent

## Smoke test wheel in a clean environment

macOS/Linux:

```bash
python -m venv .venv-smoke
. .venv-smoke/bin/activate
pip install dist/*.whl
rail --version
rail demo
```

Windows PowerShell:

```powershell
python -m venv .venv-smoke
.\.venv-smoke\Scripts\Activate.ps1
pip install dist/*.whl
rail --version
rail demo
```

Also smoke test an sdist install when preparing a TestPyPI upload:

macOS/Linux:

```bash
python -m venv .venv-sdist
. .venv-sdist/bin/activate
pip install dist/*.tar.gz
rail --version
rail demo
deactivate
```

Windows PowerShell:

```powershell
python -m venv .venv-sdist
.\.venv-sdist\Scripts\Activate.ps1
pip install (Get-ChildItem dist\*.tar.gz | Select-Object -First 1).FullName
rail --version
rail demo
deactivate
```

## TestPyPI upload

After local checks pass:

macOS/Linux:

```bash
python -m twine upload --repository testpypi dist/*
pipx install --pip-args="--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/" ai-rail
rail --version
rail demo
```

Windows PowerShell:

```powershell
python -m twine upload --repository testpypi dist/*
pipx install --pip-args="--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/" ai-rail
rail --version
rail demo
```

## PyPI upload

PyPI releases are published by GitHub Actions when a version tag is pushed:

```bash
git tag v0.1.0a8
git push origin v0.1.0a8
```

The `publish.yml` workflow builds, tests, checks distributions, and publishes to PyPI with Trusted Publishing. Do not configure PyPI API token secrets for this workflow.

Configure PyPI Trusted Publisher with:

- owner: `afshinsb`
- repository: `ai-rail`
- workflow: `publish.yml`
- environment: `pypi`

After the workflow publishes, smoke test the public package:

```bash
pipx install ai-rail
rail --version
rail demo
```

## Contributor editable install

Editable installs are for local development only:

macOS/Linux:

```bash
python -m venv .venv-editable
. .venv-editable/bin/activate
pip install -e ".[dev]"
rail --version
python -m pytest -q
deactivate
```

Windows PowerShell:

```powershell
python -m venv .venv-editable
.\.venv-editable\Scripts\Activate.ps1
pip install -e ".[dev]"
rail --version
python -m pytest -q
deactivate
```

## Public alpha release notes should include

- what AI Rail does
- alpha warning
- install command
- 3-minute demo
- safety defaults
- known limitations

## Do not publish until

- version is bumped consistently in `pyproject.toml`, `src/ai_rail/cli.py`, `src/ai_rail/__init__.py`, and `src/ai_rail/template/.rail/rail.py`
- docs mention the same version/features
- no old predecessor naming remains in public files
- zip/wheel smoke test passes
