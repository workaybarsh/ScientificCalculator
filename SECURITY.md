# Security policy

## Supported releases

The project has independent release tracks. Use the latest release in the matching track for your platform: **Windows** (`windows-v*`), **Linux** (`linux-v*`), or **macOS** (`macos-v*`). Earlier releases in the same platform track should be replaced with the current one. The release page and [installation guide](docs/INSTALLATION.md) identify the matching file and architecture.

## Reporting a vulnerability

Please use [GitHub's private vulnerability reporting form](https://github.com/workaybarsh/ScientificCalculator/security/advisories/new). Do not include proof-of-concept exploit details in public issues before a fix is available.

Include the version, platform, reproducible steps, and the expected and observed behaviour. We will acknowledge a report as soon as practical, assess it privately, and coordinate a fix or a public advisory when appropriate.

## Security boundaries

Scientific Calculator is designed to work offline. It does not require an account or telemetry service for normal operation. On Windows, preferences are stored locally under `%LOCALAPPDATA%\ScientificCalculator\`; if that location is unavailable, Windows, Linux, and macOS use `~/.scientific_calculator/ScientificCalculator/`. They are never imported from a user-selected settings file.

The project accepts only releases published on its GitHub Releases page. Verify the published SHA-256 checksum before running a downloaded binary. Until a release is explicitly described as signed, all Windows, Linux, and macOS packages must be treated as unsigned; macOS packages are also not notarized.
