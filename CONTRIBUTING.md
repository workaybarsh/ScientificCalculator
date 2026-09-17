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

## Local packaging

The release workflow builds every published package. To reproduce the Windows
build locally, use the same PyInstaller invocation that CI uses:

```powershell
py -m PyInstaller --noconfirm --clean --onedir --windowed --name ScientificCalculator --icon assets\icons\app.ico --hidden-import numpy.random._generator --collect-all numpy --collect-submodules scipy.stats --collect-submodules scipy.integrate --collect-submodules scipy.sparse --version-file packaging\windows\version_info.txt --add-data "assets\skins\skin_graphite.png;skins" --add-data "assets\skins\skin_blue.png;skins" --add-data "assets\skins\skin_pink.png;skins" --add-data "assets\skins\skin_white.png;skins" --add-data "assets\icons\app.ico;icons" --paths src src\scientific_calculator\__main__.py
```

The executable is written to `dist\ScientificCalculator\ScientificCalculator.exe`.
Compile `packaging\windows\installer.iss` with Inno Setup 6 to produce the
Setup Wizard. `build/` and `*.spec` are generated output and are not committed.

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
