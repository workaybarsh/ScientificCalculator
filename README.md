# Scientific Calculator 1.0.0

<p align="center">
  <img src="assets/branding/scientific-calculator-promo.png" alt="Scientific Calculator's current Blue skin, shown directly as the project promotional image" width="360">
</p>

<p align="center">
  A desktop scientific calculator for Windows, Linux, and macOS with a classic scientific-calculator-inspired interface,
  advanced calculation modes, responsive UI scaling, and offline operation.
</p>

## Contents

- [For Download](#for-download)
- [Overview](#overview)
- [Interface Tour](docs/INTERFACE.md)
- [Install, Run, and Remove](docs/INSTALLATION.md)
- [User Guides](#user-guides)
- [Interface and Independence Notice](#interface-and-independence-notice)
- [Features](#features)
- [Calculation Modes](#calculation-modes)
- [Scientific Constants](#scientific-constants)
- [Persistent Settings](#persistent-settings)
- [Error Behavior](#error-behavior)
- [Security Hardening](#security-hardening)
- [Percent Key Behaviour](#percent-key-behaviour)
- [Result Formatting](#result-formatting)
- [Installation](#installation)
- [Release Support](#release-support)
- [Run from Source](#run-from-source)
- [Python Dependencies](#python-dependencies)
- [Project Structure](#project-structure)
- [Build the Windows Executable](#build-the-windows-executable)
- [Build the Installer](#build-the-installer)
- [Default Configuration](#default-configuration)
- [Privacy and Offline Use](#privacy-and-offline-use)
- [Development Notes](#development-notes)
- [Tests](#tests)
- [License](#license)

## For Download

Choose the Setup Wizard for your operating system and processor. Each link starts the matching 1.0.0 installer download directly.

| Device | Setup Wizard download |
| --- | --- |
| Windows — Intel/AMD 64-bit | [Download for Windows x64](https://github.com/workaybarsh/ScientificCalculator/releases/download/windows-x64-v1.0.0/ScientificCalculator_Setup_x64.exe) |
| Windows — ARM64 | [Download for Windows ARM64](https://github.com/workaybarsh/ScientificCalculator/releases/download/windows-arm64-v1.0.0/ScientificCalculator_Setup_arm64.exe) |
| macOS — Intel | [Download for macOS Intel](https://github.com/workaybarsh/ScientificCalculator/releases/download/macos-intel-x64-v1.0.0/ScientificCalculator_Setup_macos-intel-x64.dmg) |
| macOS — Apple silicon | [Download for macOS Apple silicon](https://github.com/workaybarsh/ScientificCalculator/releases/download/macos-arm64-v1.0.0/ScientificCalculator_Setup_macos-m-series.dmg) |
| Linux — Intel/AMD 64-bit | [Download for Linux x86_64](https://github.com/workaybarsh/ScientificCalculator/releases/download/linux-x86_64-v1.0.0/ScientificCalculator_Setup_linux-x86_64.run) |
| Linux — ARM64 | [Download for Linux ARM64](https://github.com/workaybarsh/ScientificCalculator/releases/download/linux-arm64-v1.0.0/ScientificCalculator_Setup_linux-arm64.run) |

## Overview

**Scientific Calculator 1.0.0** is an open-source desktop calculator designed for scientific, engineering, and mathematical workflows.

The application combines a familiar physical-calculator-style interface with desktop convenience. It supports standard scientific calculations as well as calculus, equations, matrices, vectors, statistics, tables, complex numbers, and additional calculation modes.

The application works fully offline and does not require an internet connection for normal calculations.

User guides: [English](USER_GUIDE.md) · [Türkçe](KULLANIM_KILAVUZU.md).

## User Guides

The promotional image is the current Graphite calculator appearance. It shows the same LCD-first workflow, centre directional pad, calculus key, enlarged `∞` label above `OPTN`, and white numeric keypad used by the desktop application. For a control-by-control explanation, see the illustrated [Interface Tour](docs/INTERFACE.md). For platform downloads, native installers, portable packages, checksum verification, and full removal, see [Install, run, and remove](docs/INSTALLATION.md).

To report a security issue privately, see [SECURITY.md](SECURITY.md).

## Interface and Independence Notice

Scientific Calculator is **not an emulator, firmware clone, or affiliated product of any calculator manufacturer**. It is an independent calculation tool with its own open-source implementation. The interface is designed to present that functionality through the familiar, widely recognized layout conventions of classic scientific calculators; it does not reproduce proprietary firmware or claim compatibility with a specific brand or model.

## Features

- Scientific and engineering calculations
- Trigonometric and inverse trigonometric functions
- Hyperbolic and inverse hyperbolic functions
- Logarithmic and exponential functions
- Fractions, powers, roots, factorials, and combinatorics
- Numerical and symbolic calculus support
  - One editable integral template: blank bounds give an indefinite result; two bounds give a definite result, including `inf` / `∞` bounds
  - Derivatives
  - Complex definite and symbolic integrals
  - Complex derivatives with explicit existence/non-existence statuses
  - Double and triple integrals with editable nested expression bounds
- Equation solving, including common first-order and second-order linear ordinary differential equations
- Complex number calculations
- Base-N calculations
- Matrix calculations with row-by-row entry, signed `+` / `-` separators, and enforced column counts
- Vector calculations
- Statistics
- Probability distributions
- Spreadsheet mode
- Function table mode
- Equation / Function mode
- Inequality mode
- Ratio calculations
- Configurable number and angle formats
- Responsive calculator interface
- Four selectable calculator skins: Graphite, Blue, Pink, and White
- Persistent application settings
- Persistent last-10 calculation history, browsable on the LCD with `▲` / `▼` (`1` is the newest entry)
- Offline operation

## Calculation Modes

Scientific Calculator includes the following main modes:

1. Calculate
2. Complex
3. Base-N
4. Matrix
5. Vector
6. Statistics
7. Distribution
8. Spreadsheet
9. Table
10. Equation / Function
11. Inequality
12. Ratio

## Scientific Constants

Setup lets you choose between **Legacy CODATA 2010 (compatibility)**, which preserves the original calculator values, and **Current CODATA 2022**. `CONST` always labels the selected catalogue. The current catalogue follows [NIST's CODATA 2022 recommended values](https://physics.nist.gov/cuu/Constants/index.html); the legacy option remains available so older calculations are reproducible.

## Persistent Settings

Application settings can be saved directly from the calculator.

Saved preferences include the UI scale, selected calculator skin, and calculator setup options. Settings are stored as typed values in `%LOCALAPPDATA%\ScientificCalculator\settings.db` using SQLite; no JSON, pickle, `shelve`, or `dbm` data is read. If `LOCALAPPDATA` is unavailable, the fixed fallback is `%USERPROFILE%\.scientific_calculator\ScientificCalculator\settings.db`. The application only opens these app-controlled locations; it does not import user-selected settings files. Stored values are validated against the supported Setup choices, and invalid or damaged values fall back safely to in-memory defaults without overwriting the database.

The application also saves the active configuration when it closes normally. The last 10 successful calculations—including integrals, derivatives, summations, and SOLVE results—and their displayed results are stored locally in the same SQLite database. Open `MENU` → `History` to browse them directly on the LCD with `▲` / `▼`; no separate window is opened. Setup's **Clear History** removes only those saved calculations after confirmation; **Reset to Defaults** also clears settings. Common parenthesis-free trigonometric products such as `sinxcosx` are accepted as `sin(x)×cos(x)`.

Every mode, integral, and derivative transition first follows AC-style cleanup: it cancels a live calculation and clears the prior LCD state before opening the next workspace. In **Calculate** and **Complex** modes, `∫` then opens an LCD-only calculus chooser; it never opens a dialog window. The key has no calculus action in other modes. The single integral template is shared by definite and indefinite integration: enter both bounds for a definite result, or leave both blank for a symbolic result with `+ C`. In Calculate, the differential beside `d` is blank until you enter the desired variable. Calculate additionally offers double and triple integrals in numbered natural templates: `◀` / `▶` changes the editable expression, every bound, and each separately focused full-size `d□` variable layer; any single-letter variable such as `a` is accepted. Multi-integral bounds start blank and may contain expressions in already-bound outer variables (for example, an inner upper bound of `x`). Complex opens with a completely empty integrand and bounds, while retaining its fixed `dz` differential. `SHIFT + ∫` opens the dedicated derivative template only in these same two modes: leave its point blank for the derivative function, or enter a point to evaluate it there. `SHIFT + OPTN` inserts the visible, enlarged `∞` bound token; the normal definite-integral engine recognizes it as an improper bound when appropriate. History is available in Calculate and Complex modes and records the complete integral or derivative expression together with its result.

**Equation / Function** includes LCD-only templates for polynomial roots, simultaneous linear systems, and symbolic ordinary differential equations. Polynomial degrees 2–3 use empty coefficient squares navigated with `◀` / `▶`; their result rows are individually labelled `x1`, `x2`, and so on, and `▲` / `▼` moves between roots. A simultaneous equation commits one complete row per `=` and, after its final row, displays each `x1`, `x2`, … result on its own `▲` / `▼`-browsable row. A 4×4 simultaneous equation is split across two roomy rows instead of nesting all fields on one line. The ODE template presents `□·y'' + □·y' + □·y = □` in two clear rows: enter the four coefficient expressions, including functions of `x`, from left to right and press `=`. Long expressions remain in their own field with `…` while editing. The solver classifies the assembled supported linear ODE automatically. PDEs, third-and-higher order equations, and second-order nonlinear equations are rejected explicitly rather than being presented as solutions.

Long completed results and History rows retain their complete text. Use `◀` / `▶` to pan an overflowing result, `▲` / `▼` to change a result row, and `OPTN` in History to recall the selected raw expression without recalculating it. Immediately after `=`, the first `▲` restores the expression submitted for that calculation; after `AC`, the first `▲` starts at the newest saved entry.

**Reset to Defaults** clears the saved configuration and calculation history, then restores the default calculator settings. It is a Setup-only action: the `ON` key performs a normal application restart and preserves saved settings.

Settings and calculation history are committed together in one SQLite transaction. Database schema and settings-data versions are separate migration gates, so a failed write cannot be reported as a successful settings change.

Long SymPy calculations run in one controller-owned process with a 30-second wall-clock limit. During a calculation, the display shows `Calculating…` and only `AC` (or Escape) is accepted; cancellation returns the calculator to its normal clean state immediately. A timed-out or cancelled operation never changes `Ans` or History.

## Error Behavior

Calculation, input, and settings errors are shown on the calculator LCD, not in a separate error popup. The active input is cleared, the current mode is preserved, successful `Ans` and History values remain intact, and a new calculation can be entered immediately. Integral and derivative template errors use a compact, single-line lower-right result row so they cannot deform the mathematical layout. All user-facing error text is English; legacy engine messages are translated at the desktop boundary. Unexpected internal failures are logged and show `Internal ERROR` on the LCD.

No cloud account or online service is required.

## Security Hardening

The mathematical expression parser is hardened while preserving calculator syntax.

- SymPy token transformations feed a restricted arithmetic interpreter; Python `eval` and builtins are not used.
- Non-mathematical characters, attribute access, Python keywords, and non-whitelisted names are rejected before parsing.
- Implicit multiplication such as `2x` and `(x+1)(x-1)` remains supported.
- Products, quotients, powers, roots, equations, SOLVE, integrals, derivatives, and single-letter equation variables remain supported.
- Raw expression, batch, exponent, and exact-intermediate budgets bound resource use before display formatting.

As with any mathematical application, users should install binaries from the official project release and verify published hashes when available. See [third-party notices](THIRD_PARTY_NOTICES.md) for the pinned runtime and build dependencies.

## Percent Key Behaviour

The percent symbol means “divide this value by 100.” For example, `10%` evaluates to `0.1`. It is not a contextual retail-calculator operation, so `200 + 10%` means `200.1`, not `220`.

## Result Formatting

The calculator supports exact symbolic output and configurable numeric output. Depending on the selected mode and settings, results may be displayed as fractions, radicals, decimal values, scientific notation, or complex numbers.

Numeric formatting options include **Norm**, **Fix**, and **Sci**, with selectable digit precision. Complex numeric output follows the same selected numeric formatting and supports `a+bi` and polar `r∠θ` display modes.

---

## Installation

Choose the guided Setup Wizard for the matching cross-platform installation flow, or the direct-run package to use the calculator without installing. The complete, platform-specific guide is [Install, run, and remove](docs/INSTALLATION.md).

| Platform | Guided Setup Wizard | Direct-run package |
| --- | --- | --- |
| Windows x64 | `ScientificCalculator_Setup_x64.exe` | `ScientificCalculator-windows-x64.zip` |
| Windows ARM64 | `ScientificCalculator_Setup_arm64.exe` | `ScientificCalculator-windows-arm64.zip` |
| macOS Intel x64 | `ScientificCalculator_Setup_macos-intel-x64.dmg` | ZIP application bundle |
| macOS M Series | `ScientificCalculator_Setup_macos-m-series.dmg` | ZIP application bundle |
| Linux — Intel or AMD 64-bit architecture | `ScientificCalculator_Setup_linux-x86_64.run` | `.tar.gz` archive |
| Linux — ARM 64-bit architecture | `ScientificCalculator_Setup_linux-arm64.run` | `.tar.gz` archive |

The guided uninstall path always closes Scientific Calculator before removing only its own files, settings, history, SQLite sidecars, and diagnostic logs. The macOS wizard installs a dedicated **Scientific Calculator Uninstaller.app** because moving an app to Trash cannot safely run that cleanup itself. Direct-run packages make no operating-system changes; follow the portable removal instructions in the linked guide if a completely clean reset is required.

## Release Support

The current release is managed as six independent platform-and-architecture tracks. Each release page stays focused on one processor architecture, with its graphical Setup Wizard, native installer where available, direct-run package, and SHA-256 checksum.

| Release title | Tag | Files |
| --- | --- | --- |
| Windows x64 1.0.0 | `windows-x64-v1.0.0` | Inno Setup Wizard (`.exe`), portable ZIP archive, and SHA-256 checksum |
| Windows ARM64 1.0.0 | `windows-arm64-v1.0.0` | Inno Setup Wizard (`.exe`), portable ZIP archive, and SHA-256 checksum |
| macOS Intel x64 1.0.0 | `macos-intel-x64-v1.0.0` | Guided Setup Wizard disk image (`.dmg`), native Installer package (`.pkg`), direct-run portable bundle (`.zip`), and SHA-256 checksum |
| macOS Apple Silicon 1.0.0 | `macos-arm64-v1.0.0` | Guided Setup Wizard disk image (`.dmg`), native Installer package (`.pkg`), direct-run portable bundle (`.zip`), and SHA-256 checksum |
| Linux x86_64 1.0.0 | `linux-x86_64-v1.0.0` | Graphical Setup Wizard (`.run`), native Debian package (`.deb`), direct-run `.tar.gz` archive, and SHA-256 checksum |
| Linux ARM64 1.0.0 | `linux-arm64-v1.0.0` | Graphical Setup Wizard (`.run`), native Debian package (`.deb`), direct-run `.tar.gz` archive, and SHA-256 checksum |

macOS bundles and installer packages are not code-signed or notarized, so macOS may require the user to explicitly allow the application after verifying its checksum. Every platform starts at **100% UI scale**; macOS automatically selects a smaller effective scale only when its completed client area cannot fit the full skin. The macOS `.dmg` and Linux `.run` packages present the shared graphical Setup Wizard; ZIP and `.tar.gz` packages run directly after extraction. Removing a wizard installation first closes Scientific Calculator and removes only its app-owned settings, history, SQLite sidecars, and diagnostic logs; the macOS wizard also adds **Scientific Calculator Uninstaller** for this explicit full reset.

---

## Run from Source

### Requirements

- Windows, Linux, or macOS with a graphical desktop
- Python 3.12
- pip

Clone or download the repository, open a terminal in the project directory, and install the dependencies:

```powershell
py -m pip install -e .
```

Run the application:

```powershell
py -m scientific_calculator
```

### Python Dependencies

The project currently uses:

- SymPy
- SciPy
- NumPy
- Pillow

[`pyproject.toml`](pyproject.toml) is the canonical dependency and package definition. [`requirements.txt`](requirements.txt) and [`requirements-dev.txt`](requirements-dev.txt) are pinned compatibility lists for non-editable installs.

### Project Structure

```text
src/scientific_calculator/  Application package and runtime code
  calculator_engine.py      Parser, calculation modes, and stateful engine facade
  calculus.py               Real and complex integral/derivative policy
  numeric_validation.py     Shared finite-number validation
  calculation_controller.py Cancellable Tk-process coordination
assets/                     Branding, icons, skins, and installer artwork
packaging/windows/          Windows installer script and executable metadata
packaging/linux/            Debian/Ubuntu package builder
packaging/macos/            macOS package builder and explicit full uninstaller
tests/                      Automated regression tests
```


---

## Build the Windows Executable

From the project root, run:

```powershell
py -m PyInstaller --noconfirm --clean --onedir --windowed --name ScientificCalculator --icon assets\icons\app.ico --hidden-import numpy.random._generator --collect-all numpy --collect-all scipy --version-file packaging\windows\version_info.txt --add-data "assets\skins\skin_graphite.png;skins" --add-data "assets\skins\skin_blue.png;skins" --add-data "assets\skins\skin_pink.png;skins" --add-data "assets\skins\skin_white.png;skins" --add-data "assets\icons\app.ico;icons" --paths src src\scientific_calculator\__main__.py
```

The compiled executable will be created at:

```text
dist\ScientificCalculator\ScientificCalculator.exe
```

PyInstaller may also create temporary build files such as `build/` and `ScientificCalculator.spec`. These do not need to be included in the public source repository.

## Build the Installer

Install **Inno Setup 6**, then open:

```text
packaging\windows\installer.iss
```

Choose:

```text
Build → Compile
```

The installer will be created at:

```text
dist\ScientificCalculator_Setup.exe
```

---

## Default Configuration

The application starts with practical scientific-calculator defaults, including:

- Angle unit: **RAD**
- Result format: **Fix 3**
- UI scale: **100% on every platform; macOS may apply a temporary fit fallback**
- Skin: **Graphite**

These options can be changed from the calculator's setup menu and saved for future sessions.

## Privacy and Offline Use

Scientific Calculator is designed to operate locally.

- Calculations are performed on the user's computer.
- Normal calculator operation does not require an internet connection.
- Application settings are stored locally.
- No account is required.

---

## Development Notes

When modifying the interface, **100% scale remains the primary reference layout**. Changes to the LCD, fonts, cursors, calculus templates, or calculator skin should remain proportional at every supported scale; macOS additionally validates the completed client geometry before applying a bounded fit fallback.

When modifying calculation behavior, test both direct calculations and the relevant calculator mode before publishing a release.

The expression parser is intentionally restricted. New mathematical functions should be added explicitly to the calculator's parser whitelist instead of exposing Python builtins or a broad SymPy namespace.


## Tests

Install the pinned development tools and run lint, branch coverage, and the regression suite from the repository root:

```powershell
py -m pip install -e ".[dev]"
py -m ruff check src tests
py scripts/requirements_sync_check.py
py -m pytest -q --cov --cov-report=term-missing
py -m pyright
```

The Windows CI quality gate enforces **100% statement and branch coverage** and runs Pyright for the controller/worker/persistence modules. Critical engine, persistence, controller, calculus, and numeric-validation paths have dedicated regression tests. Coverage is increased through executable behavior tests only; no source exclusions are used to inflate it.

## License

Scientific Calculator is released as open-source software under the **MIT License**.

See [`LICENSE`](LICENSE) for the complete license text.

## Dedication

<p align="center">
  <img src="assets/branding/nizamettin.png" alt="Nizamettin" width="160">
  <img src="assets/branding/mamid.jpg" alt="Mamıd" width="160"><br>
  <strong>I dedicate this program to my cat, Nizamettin, and my bird, Mamıd.</strong>
</p>
