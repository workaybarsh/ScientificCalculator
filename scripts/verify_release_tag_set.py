"""Verify that the six architecture release tags resolve to one source commit."""

from __future__ import annotations

import subprocess
import sys

from version_sync_check import canonical_version, parse_release_tag

TRACKS = (
    "windows-x64", "windows-arm64", "macos-intel-x64", "macos-arm64", "linux-x86_64", "linux-arm64",
)


def _commit(tag: str) -> str:
    result = subprocess.run(
        ("git", "rev-parse", f"{tag}^{{commit}}"), check=False, capture_output=True, text=True
    )
    if result.returncode:
        raise ValueError(f"cannot resolve release tag {tag}: {result.stderr.strip()}")
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> None:
    arguments = sys.argv[1:] if argv is None else argv
    version = arguments[0] if len(arguments) == 1 else canonical_version()
    if version != canonical_version():
        raise SystemExit(f"requested version {version} does not match canonical version {canonical_version()}")
    tags = tuple(f"{track}-v{version}" for track in TRACKS)
    for tag in tags:
        parse_release_tag(tag)
    try:
        commits = {tag: _commit(tag) for tag in tags}
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if len(set(commits.values())) != 1:
        details = ", ".join(f"{tag}={commit}" for tag, commit in commits.items())
        raise SystemExit(f"release tags do not share one commit: {details}")
    print(f"Release tag set OK: {version} -> {next(iter(commits.values()))}")


if __name__ == "__main__":
    main()
