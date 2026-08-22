"""Fail a release build when its tag and package metadata disagree."""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _expected_versions(tag: str) -> tuple[str, str, str, tuple[int, int, int, int]]:
    match = re.fullmatch(r"v(\d+)\.(\d+)(?:\.(\d+))?", tag)
    if not match:
        raise ValueError(f"invalid release tag: {tag!r}; expected vX.Y or vX.Y.Z")
    major, minor = (int(part) for part in match.groups()[:2])
    patch = int(match.group(3) or 0)
    installer_version = f"{major}.{minor}" if match.group(3) is None else f"{major}.{minor}.{patch}"
    return installer_version, f"{major}.{minor}.{patch}", f"{major}.{minor}.{patch}.0", (major, minor, patch, 0)


def main(argv: list[str] | None = None) -> None:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        raise SystemExit("usage: python scripts/version_sync_check.py vX.Y[.Z]")
    try:
        installer_version, semver, windows_version, version_tuple = _expected_versions(arguments[0])
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    with (ROOT / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    package_init = (ROOT / "src/scientific_calculator/__init__.py").read_text(encoding="utf-8")
    installer = (ROOT / "packaging/windows/installer.iss").read_text(encoding="utf-8")
    version_info = (ROOT / "packaging/windows/version_info.txt").read_text(encoding="utf-8")

    expected_installer_values = (
        f'#define MyAppVersion "{installer_version}"',
        f"VersionInfoVersion={windows_version}",
        f"VersionInfoProductVersion={windows_version}",
    )
    expected_version_info_values = (
        *(f"{key}={version_tuple}" for key in ("filevers", "prodvers")),
        *(f"StringStruct('{key}', '{windows_version}')" for key in ("FileVersion", "ProductVersion")),
    )
    errors = []
    if project_version != semver:
        errors.append(f"pyproject.toml: expected {semver}, found {project_version}")
    if f'__version__ = "{semver}"' not in package_init:
        errors.append(f"src/scientific_calculator/__init__.py missing __version__ {semver}")
    errors.extend(f"installer missing: {value}" for value in expected_installer_values if value not in installer)
    errors.extend(f"version_info missing: {value}" for value in expected_version_info_values if value not in version_info)
    if errors:
        raise SystemExit("Version mismatch:\n- " + "\n- ".join(errors))
    print(f"Version sync OK: {arguments[0]} / {semver} / {windows_version}")


if __name__ == "__main__":
    main()
