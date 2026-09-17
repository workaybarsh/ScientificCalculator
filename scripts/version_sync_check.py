"""Verify that every current version surface matches the canonical release tag."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src" / "scientific_calculator" / "_version.py"
RELEASE_TAG_PATTERN = re.compile(
    r"(?P<platform>windows-x64|windows-arm64|macos-intel-x64|macos-arm64|linux-x86_64|linux-arm64)"
    r"-v(?P<version>\d+\.\d+\.\d+)"
)


def canonical_version() -> str:
    """Read the sole hand-maintained application version without importing the app."""

    version_module = ast.parse(VERSION_FILE.read_text(encoding="utf-8"), filename=str(VERSION_FILE))
    for statement in version_module.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == "__version__"
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            version = statement.value.value
            if re.fullmatch(r"\d+\.\d+\.\d+", version):
                return version
    raise ValueError(f"{VERSION_FILE.relative_to(ROOT)} must assign __version__ = 'X.Y.Z'")


def parse_release_tag(tag: str) -> tuple[str, str]:
    """Return the supported architecture track and semantic version in *tag*."""

    match = RELEASE_TAG_PATTERN.fullmatch(tag)
    if not match:
        raise ValueError(
            "invalid release tag: "
            f"{tag!r}; expected one of windows-x64-vX.Y.Z, windows-arm64-vX.Y.Z, "
            "macos-intel-x64-vX.Y.Z, macos-arm64-vX.Y.Z, linux-x86_64-vX.Y.Z, or linux-arm64-vX.Y.Z"
        )
    return match.group("platform"), match.group("version")


def _windows_version(version: str) -> tuple[str, tuple[int, int, int, int]]:
    major, minor, patch = (int(part) for part in version.split("."))
    return f"{version}.0", (major, minor, patch, 0)


def _current_document_errors(version: str) -> list[str]:
    expected_tags = tuple(
        f"{platform}-v{version}"
        for platform in (
            "windows-x64",
            "windows-arm64",
            "macos-intel-x64",
            "macos-arm64",
            "linux-x86_64",
            "linux-arm64",
        )
    )
    surfaces = {
        "README.md": f"# Scientific Calculator {version}",
        "USER_GUIDE.md": f"> Version {version}",
        "KULLANIM_KILAVUZU.md": f"> Sürüm {version}",
    }
    errors = [
        f"{path} missing current version marker {marker!r}"
        for path, marker in surfaces.items()
        if marker not in (ROOT / path).read_text(encoding="utf-8")
    ]
    for path in ("README.md", "CONTRIBUTING.md", "docs/INSTALLATION.md"):
        text = (ROOT / path).read_text(encoding="utf-8")
        errors.extend(f"{path} missing current release tag {tag}" for tag in expected_tags if tag not in text)
    return errors


def main(argv: list[str] | None = None) -> None:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        raise SystemExit("usage: python scripts/version_sync_check.py <platform>-vX.Y.Z")
    try:
        platform, tag_version = parse_release_tag(arguments[0])
        version = canonical_version()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_init = (ROOT / "src/scientific_calculator/__init__.py").read_text(encoding="utf-8")
    installer = (ROOT / "packaging/windows/installer.iss").read_text(encoding="utf-8")
    version_info = (ROOT / "packaging/windows/version_info.txt").read_text(encoding="utf-8")
    windows_version, version_tuple = _windows_version(version)
    errors: list[str] = []

    if tag_version != version:
        errors.append(f"release tag version {tag_version} does not match canonical version {version}")
    if "version" not in project.get("dynamic", []):
        errors.append("pyproject.toml must declare the canonical dynamic version")
    if "version" in project:
        errors.append("pyproject.toml must not duplicate the canonical version as a static value")
    if 'version = {attr = "scientific_calculator._version.__version__"}' not in pyproject:
        errors.append("pyproject.toml is not configured to read scientific_calculator._version.__version__")
    if "from ._version import __version__ as __version__" not in package_init:
        errors.append("src/scientific_calculator/__init__.py must re-export the canonical __version__")

    expected_installer_values = (
        f'#define MyAppVersion "{version}"',
        f"VersionInfoVersion={windows_version}",
        f"VersionInfoProductVersion={windows_version}",
    )
    expected_version_info_values = (
        *(f"{key}={version_tuple}" for key in ("filevers", "prodvers")),
        *(f"StringStruct('{key}', '{windows_version}')" for key in ("FileVersion", "ProductVersion")),
    )
    errors.extend(f"installer missing: {value}" for value in expected_installer_values if value not in installer)
    errors.extend(f"version_info missing: {value}" for value in expected_version_info_values if value not in version_info)
    errors.extend(_current_document_errors(version))
    if errors:
        raise SystemExit("Version mismatch:\n- " + "\n- ".join(errors))
    print(f"Version sync OK: {platform} / {version} / Windows metadata {windows_version}")


if __name__ == "__main__":
    main()
