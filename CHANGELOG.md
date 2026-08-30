# Changelog

## 1.0.0 — 2026-08-29

Initial public release.

- Offline desktop scientific calculator for Windows, Linux, and macOS, with an
  LCD workflow that keeps mathematical input and completed results on screen
  and is fully navigable from the keyboard.
- Safe expression evaluation: a restricted AST interpreter with an explicit
  call allowlist and enforced bounds on expression size, exponents,
  factorials, combinatorics, and exact-result width. It never calls `eval` and
  never exposes Python builtins or attribute traversal. Generated tests cover
  that boundary as well as hand-written examples.
- Calculus, statistics, regression, linear algebra, equation solving,
  distributions, base-N, complex numbers, and unit conversion, with semantic
  results that distinguish a computed value from non-existence, divergence, a
  domain error, a timeout, and an unevaluated symbolic form.
- Long calculations run in a cancellable isolated worker. Timeouts,
  cancellations, and stale results leave `Ans`, memory, and history untouched.
- Atomic SQLite persistence for settings and history, with schema migration
  and validation.
- Error text is translated at the display boundary, so internal SymPy,
  tokenize, and AST messages never reach the LCD.
- Quality gates: Ruff, Pyright, pip-audit, and 100% statement and branch
  coverage, with architecture boundaries enforced by static import checks and
  the full suite running on Windows, Linux, and macOS.
