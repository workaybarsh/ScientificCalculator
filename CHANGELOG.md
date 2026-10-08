# Changelog

All notable changes to this project are documented here. This project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- A seventh `android-vX.Y.Z` release track. It downloads the universal Android
  APK already published by the
  [`workaybarsh/ScientificCalculator-android`](https://github.com/workaybarsh/ScientificCalculator-android)
  repository, verifies its SHA-256 checksum, and mirrors that identical file to
  this project's release. The README download table, the port repository, and
  this project's `android-v1.0.0` release therefore all resolve to the same APK.

### Changed

- The README and the installation guide point the Android download at the
  mirrored `android-v1.0.0` release file instead of the port repository's copy.

## 1.0.0 — 2026-10-05

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
- Results render natural mathematical notation in plain text: an exponential
  `exp(x)` shows as `eˣ`, and a single integer power such as `x^2` shows as
  `x²`. Exponents with no plain-text superscript (radicals, `*`, `/`) fall back
  to `e^(...)`, and chained powers such as `x^2^3` are left as-is. Letter
  superscripts are only used when the resolved LCD family carries them; a
  substituted family on another platform keeps the safe `e^(x)` form.
- Six independent release tracks, each publishing a native installer where that
  format is available, a portable package, and a SHA-256 checksum.
- An Android port published alongside the desktop application from the same
  engine and LCD interface.

### Fixed

- The LCD now resolves the best monospaced font family actually installed on the
  host (Consolas/Cascadia Mono on Windows, Menlo/SF Mono on macOS, DejaVu Sans
  Mono/Liberation Mono/Noto Sans Mono on Linux) instead of assuming the
  Windows-only Consolas and Cambria Math. A substituted family no longer shifts
  the measured LCD geometry, and the patchy Unicode letter superscripts are used
  only when the resolved family carries them, so macOS and Linux no longer draw
  missing-glyph boxes.
- The single-integral `d□` differential-variable slot and the derivative
  evaluation-point slot slice long input to their box width with an ellipsis,
  matching every other template field.

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
