"""Reporting utilities for lint results."""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, List

from .ingest import write_csv
from .detect_duplicates import DetectionResult


def results_to_rows(results: Iterable[DetectionResult]) -> List[dict]:
    return [asdict(r) for r in results]


def write_results_csv(
    path: str,
    results: Iterable[DetectionResult],
    include_tag_hygiene: bool = False
) -> None:
    """Write detection results to CSV file.

    Args:
        path: Output CSV file path
        results: Detection results to write
        include_tag_hygiene: Whether tag hygiene was enabled (affects column order)

    Note:
        All tag hygiene columns are included in the output regardless of this flag.
        This parameter is for future extensibility and clear intent.
    """
    write_csv(path, results_to_rows(list(results)))


def print_summary(results: Iterable[DetectionResult], include_tag_hygiene: bool = False) -> None:
    """Print summary of detection results.

    Args:
        results: Detection results to summarize
        include_tag_hygiene: Whether to include tag hygiene statistics
    """
    results_list = list(results)

    # Tag hygiene summary (if enabled)
    if include_tag_hygiene:
        from .tag_hygiene import parse_tags

        total_tags = 0
        kept_count = 0
        deleted_count = 0
        unknown_count = 0
        auto_added_count = 0
        cards_need_review = 0

        for r in results_list:
            if r.tags_kept:
                kept_count += len(parse_tags(r.tags_kept))
            if r.tags_deleted:
                deleted_count += len(parse_tags(r.tags_deleted))
            if r.tags_unknown:
                unknown_count += len(parse_tags(r.tags_unknown))
            if r.tags_auto_added:
                auto_added_count += len(parse_tags(r.tags_auto_added))
            if r.tags_need_review:
                cards_need_review += 1
            # Total tags from original
            if r.tags:
                total_tags += len(parse_tags(r.tags))

        print("Tag Hygiene Summary:")
        print(f"  Total tags processed: {total_tags}")
        print(f"  Kept (allowed):       {kept_count}")
        print(f"  Deleted (blocked):    {deleted_count}")
        print(f"  Unknown (review):     {unknown_count}")
        print(f"  Auto-added:           {auto_added_count}")
        print(f"  Cards needing review: {cards_need_review}")
        print()

    # Duplicate detection summary
    counts = {"high": 0, "medium": 0, "low": 0, "none": 0}
    for r in results_list:
        counts[r.warning_level] = counts.get(r.warning_level, 0) + 1
    total = sum(counts.values())
    print("Duplicate Detection Summary:")
    for level in ("high", "medium", "low", "none"):
        print(f"  {level:>6}: {counts.get(level, 0)}")
    print(f"  total : {total}")

