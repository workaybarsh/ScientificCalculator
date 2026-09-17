from __future__ import annotations

import scientific_calculator.restart_manager as restart_manager


def test_frozen_restart_launches_the_packaged_executable(monkeypatch):
    monkeypatch.setattr(restart_manager.sys, "frozen", True, raising=False)
    monkeypatch.setattr(restart_manager.sys, "executable", "C:/app/ScientificCalculator.exe")
    monkeypatch.setattr(restart_manager.sys, "argv", ["ScientificCalculator.exe"])
    calls = []

    restart_manager.restart_application(lambda *args, **kwargs: calls.append((args, kwargs)))

    assert calls == [((['C:/app/ScientificCalculator.exe'],), {"close_fds": True})]


def test_source_restart_launches_the_current_python_entrypoint(monkeypatch):
    monkeypatch.delattr(restart_manager.sys, "frozen", raising=False)
    monkeypatch.setattr(restart_manager.sys, "executable", "C:/Python/python.exe")
    monkeypatch.setattr(restart_manager.sys, "argv", ["C:/src/scientific_calculator/__main__.py", "--flag"])
    calls = []

    restart_manager.restart_application(lambda *args, **kwargs: calls.append((args, kwargs)))

    assert calls == [((['C:/Python/python.exe', 'C:/src/scientific_calculator/__main__.py', '--flag'],), {"close_fds": True})]
