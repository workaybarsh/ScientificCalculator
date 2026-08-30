"""Ensure the installable project metadata and compatibility lists stay aligned."""
from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _requirements(path: Path) -> list[str]:
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#") and not value.startswith("-"):
            values.append(value)
    return values


def main() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    runtime = _requirements(ROOT / "requirements.txt")
    development = _requirements(ROOT / "requirements-dev.txt")
    expected_runtime = list(project["dependencies"])
    expected_development = list(project["optional-dependencies"]["dev"])
    errors = []
    if sorted(runtime) != sorted(expected_runtime):
        errors.append("requirements.txt does not match project.dependencies")
    if sorted(development) != sorted(expected_development):
        errors.append("requirements-dev.txt does not match project.optional-dependencies.dev")
    if errors:
        raise SystemExit("Requirements mismatch:\n- " + "\n- ".join(errors))
    print("Requirements sync OK")


if __name__ == "__main__":
    main()
