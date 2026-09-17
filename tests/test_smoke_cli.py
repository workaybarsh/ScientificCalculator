from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

import scientific_calculator.app as app_module

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


def test_module_entrypoint_delegates_to_application_main(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(app_module, "main", lambda: calls.append(True))

    runpy.run_module("scientific_calculator.__main__", run_name="__main__")

    assert calls == [True]
