"""CSV ingest for candidate cards and common types.

Schema: front, back, tags (UTF-8, quoted fields ok). Tags may be empty.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass
class CandidateRow:
    front: str
    back: str
    tags: str


def read_candidates_csv(path: str | Path) -> List[CandidateRow]:
    path = Path(path)
    rows: List[CandidateRow] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        expected = {"front", "back", "tags"}
        missing = expected - set(h.lower() for h in reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")
        for r in reader:
            rows.append(
                CandidateRow(
                    front=r.get("front", ""), back=r.get("back", ""), tags=r.get("tags", "")
                )
            )
    return rows


def write_csv(path: str | Path, rows: Iterable[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if not rows:
        # Write empty file with no rows
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

