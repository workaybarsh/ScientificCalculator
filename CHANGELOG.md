# Changelog

## 1.0.3 — 2026-08-22

- Reworked Calculate and Complex calculus into LCD-only workflows, with configurable symbolic/definite derivatives, double/triple, line, surface, flux, complex-double, and contour integration.
- Added first- and second-order symbolic ordinary differential equation solving, including optional initial conditions and persistent History entries.
- Fixed complex generalized integration for integrable complex-valued expressions such as `sqrt(ln(x))` on `0` to `1`.
- Consolidated all user-facing calculation errors at the desktop boundary so legacy Turkish engine messages are rendered in English on the LCD.
- Removed unreachable duplicate workspace popup code and retained spreadsheet reference insertion through the LCD-only **Insert reference** workflow.
- Fixed ENG notation normalization (`1234` now displays as `1.234×10^3`).
- Hardened surface-integral CAS error handling, ODE initial-condition parsing, restart worker shutdown, and persistence fallback cleanup during uninstall.
- Expanded behavioral, runtime, persistence, parser, and calculus regression coverage without coverage exclusions.

## 1.0.2 — 2026-08-22

- Added bounded raw-expression, batch-expression, exact-power, and exact-intermediate-result handling.
- Added convergent generalized/infinite real integrals with explicit infinity aliases and non-principal-value singularity handling.
- Added complex definite integrals and parameterized contour integrals in Complex mode.
- Made application shutdown reap an active calculation worker before the Tk scheduler is destroyed.
- Made cancelled worker delivery tolerate a closed result pipe, avoiding a child-process traceback during normal cancellation.
- Extracted calculus policy, calculator domain errors, and finite-number validation into focused modules without changing the public engine API.
- Optimized one electronic-table recalculation pass to reuse shared dependency values without retaining deleted or empty cells.
- Made Linux CI require a real Tk runtime under Xvfb and added dependency-manifest consistency checks.
- Documented the executable release, calculus behavior, setup persistence, and supported release policy.
