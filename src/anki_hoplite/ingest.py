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
        # Try to detect delimiter (CSV sniffer)
        sample = f.read(4096)
        f.seek(0)

        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample, delimiters=',;\t')
            reader = csv.DictReader(f, dialect=dialect)
        except csv.Error:
            # If sniffing fails, try common delimiters
            f.seek(0)
            first_line = f.readline()
            f.seek(0)

            if ';' in first_line:
                reader = csv.DictReader(f, delimiter=';')
            elif '\t' in first_line:
                reader = csv.DictReader(f, delimiter='\t')
            else:
                reader = csv.DictReader(f, delimiter=',')

        expected = {"front", "back", "tags"}

        # Create lowercase mapping of headers
        fieldnames = reader.fieldnames or []
        lower_to_actual = {h.lower(): h for h in fieldnames}

        # Check for missing columns
        missing = expected - set(lower_to_actual.keys())
        if missing:
            raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")

        # Get actual header names (case-insensitive)
        front_key = lower_to_actual["front"]
        back_key = lower_to_actual["back"]
        tags_key = lower_to_actual["tags"]

        for r in reader:
            rows.append(
                CandidateRow(
                    front=r.get(front_key, ""),
                    back=r.get(back_key, ""),
                    tags=r.get(tags_key, "")
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

