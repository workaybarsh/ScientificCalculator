# Changelog

All notable changes to this project are documented here. This project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.0.0 — 2026-09-17

Initial public release.

### Added

- Offline desktop scientific calculator for Windows, Linux, and macOS, with an
  LCD workflow that keeps mathematical input and completed results on screen
  and is fully navigable from the keyboard.
- Twelve calculation modes: Calculate, Complex, Base-N, Matrix, Vector,
  Statistics, Distribution, Spreadsheet, Table, Equation/Function, Inequality,
  and Ratio.
- Numerical and symbolic calculus: definite, indefinite, improper, double, and
  triple integrals, derivatives, limits, and first- and second-order linear
  ordinary differential equations.
- Exact symbolic output alongside Norm, Fix, and Sci numeric formatting, four
  calculator skins, eight UI scales, and persistent settings and history.
- Six independent release tracks, each publishing a Setup Wizard, a direct-run
  package, and a SHA-256 checksum.

### Security

- Expression evaluation uses a restricted AST interpreter with an explicit call
  allowlist and enforced bounds on expression size, exponents, factorials,
  combinatorics, and exact-result width. It never calls `eval` and never
  exposes Python builtins or attribute traversal.
- Long calculations run in a cancellable isolated worker. A timeout, a
  cancellation, or a stale result leaves `Ans`, memory, and history untouched.
- Settings and history are stored as typed SQLite values in an
  application-controlled location, with explicit schema migration and without
  deserializing arbitrary objects.
- Internal SymPy, tokenize, and AST messages are never shown to the user; the
  display boundary reports a stable calculator-domain category instead.
