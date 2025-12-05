"""Reporting utilities for lint results."""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, List

from .ingest import write_csv
from .detect_duplicates import DetectionResult


def results_to_rows(results: Iterable[DetectionResult]) -> List[dict]:
    return [asdict(r) for r in results]


def write_results_csv(path: str, results: Iterable[DetectionResult]) -> None:
    write_csv(path, results_to_rows(list(results)))


def print_summary(results: Iterable[DetectionResult]) -> None:
    counts = {"high": 0, "medium": 0, "low": 0, "none": 0}
    for r in results:
        counts[r.warning_level] = counts.get(r.warning_level, 0) + 1
    total = sum(counts.values())
    print("Summary:")
    for level in ("high", "medium", "low", "none"):
        print(f"  {level:>6}: {counts.get(level, 0)}")
    print(f"  total : {total}")

