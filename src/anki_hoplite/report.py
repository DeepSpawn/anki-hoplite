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


def print_summary(
    results: Iterable[DetectionResult],
    include_tag_hygiene: bool = False,
    include_cloze: bool = False,
    include_context: bool = False,
    include_recommendations: bool = False
) -> None:
    """Print summary of detection results.

    Args:
        results: Detection results to summarize
        include_tag_hygiene: Whether to include tag hygiene statistics
        include_cloze: Whether to include cloze validation statistics
        include_context: Whether to include context analysis statistics
        include_recommendations: Whether to include cloze recommendation statistics
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

    # Cloze validation summary (if enabled)
    if include_cloze:
        cloze_counts = {"excellent": 0, "good": 0, "weak": 0, "poor": 0}
        total_cloze = 0
        total_non_cloze = 0

        for r in results_list:
            if r.cloze_quality:
                total_cloze += 1
                cloze_counts[r.cloze_quality] = cloze_counts.get(r.cloze_quality, 0) + 1
            else:
                total_non_cloze += 1

        print("Cloze Validation Summary:")
        print(f"  Total cloze cards:     {total_cloze}")
        print(f"  Total non-cloze cards: {total_non_cloze}")
        if total_cloze > 0:
            print(f"  Quality breakdown:")
            for level in ("excellent", "good", "weak", "poor"):
                count = cloze_counts.get(level, 0)
                pct = (count / total_cloze * 100) if total_cloze > 0 else 0
                print(f"    {level:>9}: {count:>3} ({pct:>5.1f}%)")
        print()

    # Context analysis summary (if enabled)
    if include_context:
        context_counts = {
            "rich_context": 0,
            "minimal_context": 0,
            "phrase_fragment": 0,
            "isolated": 0
        }
        recommendation_counts = {
            "good": 0,
            "consider_enhancing": 0,
            "needs_context": 0
        }

        for r in results_list:
            if r.context_level:
                context_counts[r.context_level] = context_counts.get(r.context_level, 0) + 1
            if r.context_recommendation:
                recommendation_counts[r.context_recommendation] = recommendation_counts.get(r.context_recommendation, 0) + 1

        print("Context Analysis Summary:")
        print(f"  Context levels:")
        print(f"    Rich context:       {context_counts['rich_context']}")
        print(f"    Minimal context:    {context_counts['minimal_context']}")
        print(f"    Phrase fragment:    {context_counts['phrase_fragment']}")
        print(f"    Isolated:           {context_counts['isolated']}")
        print(f"  Recommendations:")
        print(f"    Good:               {recommendation_counts['good']}")
        print(f"    Consider enhancing: {recommendation_counts['consider_enhancing']}")
        print(f"    Needs context:      {recommendation_counts['needs_context']}")
        print()

    # Cloze recommendations summary (if enabled)
    if include_recommendations:
        recommended_count = sum(1 for r in results_list if r.cloze_recommended)
        high_confidence = sum(1 for r in results_list if r.cloze_confidence >= 0.75)
        med_confidence = sum(1 for r in results_list if 0.5 <= r.cloze_confidence < 0.75)
        low_confidence = sum(1 for r in results_list if 0.3 <= r.cloze_confidence < 0.5)

        print("Cloze Recommendation Summary:")
        print(f"  Total cards analyzed:       {len(results_list)}")
        print(f"  Recommended for cloze:      {recommended_count}")
        print(f"    High confidence (≥0.75):  {high_confidence}")
        print(f"    Med confidence (0.5-0.75): {med_confidence}")
        print(f"    Low confidence (0.3-0.5):  {low_confidence}")
        print()

    # Self-duplicate detection summary
    self_dup_counts = {"high": 0, "medium": 0, "low": 0, "none": 0}
    for r in results_list:
        if r.self_duplicate_level:
            self_dup_counts[r.self_duplicate_level] = self_dup_counts.get(r.self_duplicate_level, 0) + 1

    total_self_dups = sum(v for k, v in self_dup_counts.items() if k != "none")
    if total_self_dups > 0:
        print("Self-Duplicate Detection Summary (within candidates):")
        for level in ("high", "medium", "low"):
            count = self_dup_counts.get(level, 0)
            if count > 0:
                print(f"  {level:>6}: {count}")
        print(f"  total : {total_self_dups}")
        print()

    # Duplicate detection summary (external, against deck)
    counts = {"high": 0, "medium": 0, "low": 0, "none": 0}
    for r in results_list:
        counts[r.warning_level] = counts.get(r.warning_level, 0) + 1
    total = sum(counts.values())
    print("Duplicate Detection Summary:")
    for level in ("high", "medium", "low", "none"):
        print(f"  {level:>6}: {counts.get(level, 0)}")
    print(f"  total : {total}")

