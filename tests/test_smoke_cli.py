from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_headless_smoke_check_validates_assets_and_engine() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "scientific_calculator", "--smoke-test"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
