# Scientific Calculator agent guide

## Project purpose

Scientific Calculator is an offline desktop scientific calculator for Windows, Linux, and macOS. Its UX should feel like a physical scientific calculator: mathematical input and completed results stay on the LCD, and keyboard/keypad navigation is discoverable through focus, arrow keys, and concise prompts rather than persistent form instructions.

## Architecture

```text
Tk App
  -> LCD flows, MathTemplate slot graphs, and event bindings
  -> CalculationController
  -> typed CalculationRequest / allowlisted worker operation
  -> ScientificCalculatorEngine facade
  -> CalculusMixin, typed calculus results, and engine/ domain services
  -> explicit CAS worker policy, SymPy / NumPy / SciPy
  -> SQLite SettingsStore
```

`docs/ARCHITECTURE.md` is the authoritative statement of these layers and the
import rules between them; `tests/test_architecture_boundaries.py` enforces them
by parsing source imports. Read that document before moving code across a layer.

- `src/scientific_calculator/app.py` owns Tk rendering and user interaction only. Keep new domain logic out of `App`.
- `calculator_engine.py` remains the backwards-compatible facade and safe expression boundary.
- `engine/` holds the state-free domain services behind that facade: `expression_parser.py` (the restricted AST evaluator and its resource limits), `result_formatter.py` (display rendering), `expression_normalization.py`, `equations.py`, `linear_algebra.py`, `statistics.py`, `regression.py`, `distributions.py`, `numeric_tools.py`, `conversions.py`, `angles.py`, `base_n.py`, `complex_numbers.py`, `bounded_collections.py`, `outcomes.py`, `settings.py`, and `state_defaults.py`. New domain logic belongs in a service here, not in the facade. Callers outside this repository use the facade; `engine/` modules are internal.
- `engine/outcomes.py` carries `EngineOutcome`, the immutable description of a completed use case. A service returns one; only the facade commits its `Ans`, memory, and history changes.
- `calculus.py` holds integral, derivative, and ODE policy.
- `calculation_controller.py` owns one cancellable foreground worker and commits worker state only after success.
- `calculation_worker.py` has an explicit `CalculationOperation` registry. New engine methods are never worker-callable until deliberately added there and tested.
- `math_template.py` is pure navigation state. Define a real slot graph for new mathematical templates; do not put cursor geometry or edit rules in Tk callbacks.
- `calculation_result.py` carries semantic math outcomes. Preserve the distinction between a computed value, non-existence, divergence, domain error, timeout, and unevaluated symbolic form.
- `settings_store.py` owns SQLite schema, migration, validation, and transactions. Keep settings/history writes atomic.
- `lcd_layout.py` contains pure, testable LCD result layout helpers.
- `entry_rules.py` holds pure entry and recall rules: repairing a pasted integral body, bounding a table's row range, and rebuilding template fields from a stored history record.
- `lcd_forms.py` decides which inputs a matrix, vector, ratio, or distribution workflow needs, and answers read-only questions about a flow mapping. It never mutates flow state; starting and committing a form stays in `App`.
- `lcd_fields.py` builds LCD form field specifications, renders their text, and parses entered text back into values. It is Tk-free and takes the engine as a parameter, so numeric-entry rules stay testable without a display.

## Startup and development

Supported source runtime: Python 3.12 on Windows, Linux, or macOS with a graphical desktop.

```powershell
py -m pip install -e ".[dev]"
py -m scientific_calculator
```

Run the source smoke test with `py -m scientific_calculator --smoke-test`.

## Required validation

```powershell
py -m ruff check src tests
py -m pyright
py -m pip_audit -r requirements.txt
py -m pytest -q --cov --cov-branch --cov-fail-under=100 --cov-report=term-missing --cov-report=xml --cov-report=json
py scripts/verify_coverage.py coverage.json
py scripts/requirements_sync_check.py
```

Statement coverage must remain 100%. Branch coverage must remain 100%. Coverage must exercise real behaviour; never lower thresholds, disable branch measurement, delete tests to improve a metric, or add broad omit rules.

## Security and worker rules

- Do not replace the safe parser with `eval`, unrestricted `sympify`, Python builtins, or arbitrary name resolution.
- Do not permit attribute traversal, callable injection, or bypasses for expression, exponent, factorial, or exact-result limits.
- Do not use dynamic `getattr` to dispatch worker requests. Extend `CalculationOperation` intentionally instead.
- Preserve timeout, cancellation, stale-result rejection, worker cleanup, and the rule that failed/cancelled workers do not modify `Ans`, memory, or history.
- Do not catch broad exceptions just to make a test or UI error disappear. Convert expected domain errors to `CalculatorError` at a well-defined boundary.

## Persistence

Settings and the last ten calculation-history entries share an SQLite transaction. Settings/data schema migration is explicit; corrupted or unsupported data is reported and falls back safely without deserializing arbitrary objects. Database locations are app-controlled (`%LOCALAPPDATA%\ScientificCalculator` on Windows, with `~/.scientific_calculator/ScientificCalculator` as the cross-platform fallback).

## UI design rules

- Advanced mathematical operations should prefer natural mathematical notation over multi-step form dialogs. A single integral template uses blank bounds for a symbolic result and two bounds for a definite result; its `d□` variable is always user-entered. Double/triple integrals use numbered editable layers with blank bounds and variables; `←`/`→` changes the active layer, while `▲`/`▼` on an ordinary result continues to recall the expression submitted before `=`.
- Persistent instructional labels should not clutter the LCD.
- Navigation should be discoverable through cursor position and arrow-key movement.
- Keep calculate/complex integral, derivative, ODE, matrix, vector, equation, table, and spreadsheet workflows inside the LCD where existing flows do so.
- Preserve the reference 100% UI scale and test supported scales when changing layout or hotspots. Every platform starts at 100% on first run or after Reset to Defaults; macOS may reduce only the effective scale when post-layout geometry cannot fit the full skin. Saved user scales are platform-independent.

## Calculus

Definite and symbolic integrals, real double/triple integrals, complex single integrals, derivatives, limits, and ODEs have focused engine APIs. Keep bound order, differential variables, and complex versus real behaviour explicit. Calculate exposes single/double/triple integrals; Complex exposes a single integral. Complex derivatives belong to the dedicated derivative template, not the complex-integral chooser. The history expression must include the integral or derivative itself, not only the result. Treat a mathematical non-existence/divergence as a semantic result or controlled calculator error, not as an internal application crash.

## Matrix, vector, and equation UX

Keep matrix/vector dimensions and entries validated before NumPy conversion; preserve finite-value and bounded-shape checks. Equation flows should remain equation-oriented and return explicit no-solution/infinite-solution conditions rather than silently choosing a root.

## Versioning and releases

Version values must agree in:

- `pyproject.toml`
- `src/scientific_calculator/__init__.py`
- `packaging/windows/installer.iss`
- `packaging/windows/version_info.txt`

The canonical version is `src/scientific_calculator/_version.py`; never duplicate it by hand. Validate each architecture tag with `py scripts/version_sync_check.py <platform>-vX.Y.Z`. The independent release tracks build matching packages: Windows x64/ARM64 Setup Wizard and ZIP; macOS Intel/Apple Silicon `.pkg` and ZIP; Linux x86_64/ARM64 `.deb` and `.tar.gz`. Every track publishes SHA-256 checksums. Native removal must close the calculator and remove only its own data.

Before publishing a six-track release, run `py scripts/verify_release_tag_set.py X.Y.Z`; it rejects a mixed-source tag set.

## Definition of done

For every behaviour change: implementation, focused regression tests, full branch coverage, Ruff, Pyright, dependency audit, documentation updates, and a security review are part of the same change. Update this file whenever architecture, safety boundaries, required validation, or UX contracts change.
