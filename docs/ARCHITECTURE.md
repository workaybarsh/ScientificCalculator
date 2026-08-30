# Architecture and API Boundaries

This document defines the frozen layering for the Scientific Calculator source
tree. It is deliberately short: the implementation is tested as a desktop
application, while these boundaries prevent a future refactor from silently
coupling numerical work to Tk or a process owner.

```text
Tk App (`app.py`)
  -> LCD/template/persistence application helpers
  -> `CalculationController`
  -> typed `CalculationRequest` and allowlisted worker operation
  -> `ScientificCalculatorEngine` compatibility facade
  -> calculus policy, safe parser, and `engine/` domain services
  -> explicit CAS worker policy
```

## Stable compatibility surface

`scientific_calculator.calculator_engine` is the compatibility boundary for
callers that need the engine. Its documented entry points are
`ScientificCalculatorEngine`, `CalculatorSettings`, `CalculatorError`,
`CONVERSIONS`, `CONSTANTS_DATASET_LABELS`, and `constants_for_dataset`.
Internal `engine/` modules are implementation details: new callers should use
the facade unless they are adding or testing a domain service inside this
repository.

`CalculationResult` remains the semantic result contract for calculus and
other advanced mathematical outcomes. `EngineOutcome` is the immutable
use-case result used by state-free services; only the facade commits its
declared `Ans`, memory, and history changes.

## Import boundaries

- `app.py` owns all Tk, Pillow/UI image, display, and user-interaction code.
- `calculation_controller.py` owns the cancellable foreground process and is
  Tk-agnostic: it receives a scheduler rather than importing Tk.
- `calculation_worker.py` and `cas_worker.py` are headless protocol/process
  modules. They must never import the App, controller, Tk, or presentation
  helpers.
- The engine kernel is `calculator_engine.py`, `calculus.py`,
  `calculation_result.py`, `errors.py`, `history.py`, `numeric_validation.py`,
  and every `engine/*.py` module. It must never import the app, controller,
  Tk, Pillow, LCD/template helpers, or process primitives.
- The engine may request an allowlisted CAS action through `cas_worker`, but it
  may not directly start child processes or use `subprocess`. Process lifetime
  and timeout policy remain at the controller/CAS-worker boundaries.

The static checks in `tests/test_architecture_boundaries.py` enforce these
rules by parsing source imports. They do not import the UI and therefore also
protect headless engine and worker test execution.

## Worker and state rules

Only operations listed in `CalculationOperation` can cross the foreground
worker boundary. A worker receives an `EngineCalculationSnapshot`, returns a
`CalculationPayload`, and does not commit state to the live engine. The
controller/app commits a successful payload; errors, timeouts, cancellations,
and stale results leave the live `Ans`, memory, and history untouched.

CAS dispatch is similarly allowlisted by `CASOperation`. Do not replace either
registry with dynamic attribute lookup.
