"""Fail CI unless coverage JSON proves complete application coverage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "scientific_calculator"
SUPPRESSION_MARKERS = ("pragma: no cover", "pragma: no branch", "coverage: ignore")


def main(argv: list[str] | None = None) -> None:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        raise SystemExit("usage: python scripts/verify_coverage.py coverage.json")
    report_path = Path(arguments[0])
    if not report_path.is_file():
        raise SystemExit(f"coverage report does not exist: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    totals = report.get("totals", {})
    statements = int(totals.get("num_statements", -1))
    covered_statements = int(totals.get("covered_lines", -1))
    branches = int(totals.get("num_branches", -1))
    covered_branches = int(totals.get("covered_branches", -1))
    missing_lines = int(totals.get("missing_lines", -1))
    missing_branches = int(totals.get("missing_branches", -1))
    partial_branches = int(totals.get("num_partial_branches", -1))
    errors = []
    if statements != covered_statements or missing_lines != 0:
        errors.append(f"statements: {covered_statements}/{statements}; missing lines: {missing_lines}")
    if branches != covered_branches or missing_branches != 0 or partial_branches != 0:
        errors.append(
            f"branches: {covered_branches}/{branches}; missing branches: {missing_branches}; "
            f"partial branches: {partial_branches}"
        )
    for path in SOURCE.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        if any(marker in text for marker in SUPPRESSION_MARKERS):
            errors.append(f"coverage suppression found in {path.relative_to(ROOT)}")
    if errors:
        raise SystemExit("Coverage verification failed:\n- " + "\n- ".join(errors))
    print(f"Statements: {covered_statements}/{statements} (100%)")
    print(f"Branches: {covered_branches}/{branches} (100%)")
    print("Partial branches: 0")
    print("Missing lines: 0")
    print("Missing branches: 0")


if __name__ == "__main__":
    main()
