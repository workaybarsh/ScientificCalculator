"""Integration coverage for the canonical-version release gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "version_sync_check.py"


@pytest.mark.parametrize(
    "tag",
    (
        "windows-x64-v1.0.0",
        "windows-arm64-v1.0.0",
        "macos-intel-x64-v1.0.0",
        "macos-arm64-v1.0.0",
        "linux-x86_64-v1.0.0",
        "linux-arm64-v1.0.0",
    ),
)
def test_version_sync_accepts_each_supported_current_architecture_tag(tag: str) -> None:
    result = subprocess.run(
        (sys.executable, str(SCRIPT), tag),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert f"Version sync OK: {tag.removesuffix('-v1.0.0')} / 1.0.0 / Windows metadata 1.0.0.0" in result.stdout


@pytest.mark.parametrize(
    "tag",
    ("windows-v1.0.0", "windows-x64-v1.1", "linux-x64-v1.0.0", "macos-arm64-v1.1.1"),
)
def test_version_sync_rejects_legacy_malformed_or_mismatched_tags(tag: str) -> None:
    result = subprocess.run(
        (sys.executable, str(SCRIPT), tag),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "release tag" in result.stderr or "invalid release tag" in result.stderr
