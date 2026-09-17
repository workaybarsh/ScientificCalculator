"""Static import and compatibility checks for the frozen application layers."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

import scientific_calculator.calculator_engine as facade

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "scientific_calculator"

_UI_OR_PRESENTATION_IMPORTS = frozenset(
    {
        "tkinter",
        "_tkinter",
        "PIL",
        "scientific_calculator.app",
        "scientific_calculator.application_persistence",
        "scientific_calculator.application_services",
        "scientific_calculator.calculation_controller",
        "scientific_calculator.entry_rules",
        "scientific_calculator.expression_document",
        "scientific_calculator.lcd_fields",
        "scientific_calculator.lcd_forms",
        "scientific_calculator.lcd_flow_state",
        "scientific_calculator.lcd_layout",
        "scientific_calculator.math_template",
        "scientific_calculator.restart_manager",
        "scientific_calculator.spreadsheet_cursor",
        "scientific_calculator.template_session",
    }
)
_ENGINE_PROCESS_IMPORTS = frozenset({"multiprocessing", "subprocess"})
_ENGINE_KERNEL_FILES = (
    PACKAGE_ROOT / "calculator_engine.py",
    PACKAGE_ROOT / "calculus.py",
    PACKAGE_ROOT / "calculation_result.py",
    PACKAGE_ROOT / "errors.py",
    PACKAGE_ROOT / "history.py",
    PACKAGE_ROOT / "numeric_validation.py",
)
_WORKER_FILES = (
    PACKAGE_ROOT / "calculation_worker.py",
    PACKAGE_ROOT / "cas_worker.py",
)


def _module_name(path: Path) -> str:
    return ".".join(("scientific_calculator", *path.relative_to(PACKAGE_ROOT).with_suffix("").parts))


def _imports(path: Path) -> set[str]:
    """Return absolute import modules without importing the inspected source."""
    module_parts = _module_name(path).split(".")
    package_parts = module_parts[:-1]
    imports: set[str] = set()

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    imports.add(node.module)
                else:
                    imports.update(alias.name for alias in node.names)
                continue
            base = package_parts[: len(package_parts) - max(node.level - 1, 0)]
            if node.module:
                imports.add(".".join((*base, node.module)))
            else:
                imports.add(".".join(base))
    return imports


def _matches(module: str, forbidden: str) -> bool:
    return module == forbidden or module.startswith(f"{forbidden}.")


def _boundary_violations(paths: Iterable[Path], forbidden_imports: Iterable[str]) -> list[str]:
    forbidden = tuple(forbidden_imports)
    violations: list[str] = []
    for path in paths:
        for module in sorted(_imports(path)):
            if any(_matches(module, blocked) for blocked in forbidden):
                relative_path = path.relative_to(REPOSITORY_ROOT).as_posix()
                violations.append(f"{relative_path}: {module}")
    return violations


def test_engine_kernel_does_not_depend_on_ui_controller_or_process_primitives() -> None:
    """The facade may request CAS work, but it cannot own UI or child processes."""
    paths = (*_ENGINE_KERNEL_FILES, *sorted((PACKAGE_ROOT / "engine").rglob("*.py")))
    violations = _boundary_violations(paths, (*_UI_OR_PRESENTATION_IMPORTS, *_ENGINE_PROCESS_IMPORTS))

    assert not violations, "\n".join(violations)


def test_workers_do_not_depend_on_ui_or_controller() -> None:
    """A spawned worker must remain runnable without a Tk or App import."""
    violations = _boundary_violations(_WORKER_FILES, _UI_OR_PRESENTATION_IMPORTS)

    assert not violations, "\n".join(violations)


def test_controller_stays_tk_agnostic() -> None:
    """The controller receives a scheduler protocol instead of importing Tk."""
    violations = _boundary_violations((PACKAGE_ROOT / "calculation_controller.py",), {"tkinter", "_tkinter", "PIL"})

    assert not violations, "\n".join(violations)


def test_compatibility_facade_keeps_the_documented_entry_points() -> None:
    """Internal service extraction must not remove the legacy facade entry points."""
    expected = {
        "CalculatorError",
        "CalculatorSettings",
        "CONSTANTS_DATASET_LABELS",
        "CONVERSIONS",
        "ScientificCalculatorEngine",
        "constants_for_dataset",
    }

    assert all(hasattr(facade, name) for name in expected)


def test_tests_never_patch_the_app_class_without_restoring_it() -> None:
    """A bare ``App.method = mock`` leaks into every later test in the session.

    Instance attributes and ``mock.patch.object`` both undo themselves; a class
    assignment does not, so the damage depends on collection order and moves
    when a test file is renamed.  Assign to the instance instead.
    """
    tests_root = Path(__file__).resolve().parent
    leaks: list[str] = []
    for source_path in sorted(tests_root.glob("test_*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "App"
                ):
                    leaks.append(f"{source_path.name}:{node.lineno} assigns App.{target.attr}")

    assert not leaks, "\n".join(leaks)
