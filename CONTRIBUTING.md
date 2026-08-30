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

Update all version locations and validate them before a release. The platform-and-architecture prefix keeps each release track independent:

```powershell
py scripts/version_sync_check.py windows-x64-v1.0.0
py scripts/version_sync_check.py windows-arm64-v1.0.0
py scripts/version_sync_check.py macos-intel-x64-v1.0.0
py scripts/version_sync_check.py macos-arm64-v1.0.0
py scripts/version_sync_check.py linux-x86_64-v1.0.0
py scripts/version_sync_check.py linux-arm64-v1.0.0
```

The release workflow creates one native installer, one portable package, and one SHA-256 checksum list for the selected platform-and-architecture track. Signing, notarization, and physical-device compatibility testing need the relevant credentials and hardware; do not describe them as complete unless they have actually occurred. See [Install, run, and remove](docs/INSTALLATION.md) for the public package names and removal policy.
