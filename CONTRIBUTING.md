# Contributing

## Development checks

Use Python 3.12 and install the pinned development dependencies:

```powershell
py -m pip install -e ".[dev]"
py scripts/requirements_sync_check.py
py -m ruff check src tests
py -m pyright
py -m pip_audit -r requirements.txt
py -m pytest -q --cov --cov-report=term-missing
```

Do not weaken coverage with exclusions or replace tests with output-only checks. Add targeted regression tests for every parser, persistence, worker, or UI behavior changed.

## UI tests

The live Tk suite skips only when a desktop is genuinely unavailable. To require it locally, set `SCICALC_REQUIRE_LIVE_UI=1`; Linux CI runs it under Xvfb.

## Releases

Update all version locations and validate them before a release:

```powershell
py scripts/version_sync_check.py v1.0.2
```

The release workflow creates platform packages, SHA-256 checksums, and provenance attestations. Signing and physical-device compatibility testing need the relevant credentials and hardware; do not describe them as complete unless they have actually occurred.
