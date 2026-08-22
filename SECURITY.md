# Security policy

## Supported releases

The latest release on the project's GitHub Releases page is supported. Earlier releases should be replaced with the latest available version.

## Reporting a vulnerability

Please use [GitHub's private vulnerability reporting form](https://github.com/workaybarsh/ScientificCalculator/security/advisories/new). Do not include proof-of-concept exploit details in public issues before a fix is available.

Include the version, platform, reproducible steps, and the expected and observed behaviour. We will acknowledge a report as soon as practical, assess it privately, and coordinate a fix or a public advisory when appropriate.

## Security boundaries

Scientific Calculator is designed to work offline. It does not require an account or telemetry service for normal operation. Preferences are stored locally under `%LOCALAPPDATA%\ScientificCalculator\`; they are never imported from a user-selected settings file.

The project accepts only releases published on its GitHub Releases page. Verify the published SHA-256 checksum before running a downloaded binary. Until a release is explicitly described as signed, Windows binaries must be treated as unsigned.
