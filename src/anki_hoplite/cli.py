"""CLI entrypoint for the Anki-Hoplite prototype.

Usage (planned):
  python -m anki_hoplite.cli lint --input candidates.csv --out out/lint_results.csv 
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from .ingest import read_candidates_csv
from .lemmatize import GreekLemmatizer
from .deck_index import build_from_export
from .detect_duplicates import analyze_candidates, analyze_deck_internal
from .report import write_results_csv, print_summary
from .cltk_setup import ensure_cltk_grc_models
from .tag_hygiene import load_tag_schema
from .tag_converter import load_tag_converter


def load_config(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        # Default config
        return {
            "deck_name": "Unified Greek",
            "export_path": "resources/Unified-Greek.txt",
            "model_field_map": "resources/model_field_map.json",
            "normalization": {
                "nfc": True,
                "lower": True,
                "strip_punct": True,
                "strip_accents": True,
            },
            "dry_run": True,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_lint(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)

    # Validate auto-tag flag
    if args.auto_tag and not args.enforce_tags:
        print("Error: --auto-tag requires --enforce-tags")
        return 1

    # Load tag schema if tag hygiene is enabled
    tag_schema = None
    if args.enforce_tags:
        try:
            tag_schema = load_tag_schema(args.tag_schema)
            print(f"Loaded tag schema from: {args.tag_schema}")
            print(f"  Allowed tags: {len(tag_schema.allowed_tags)}")
            print(f"  Blocked tags: {len(tag_schema.blocked_tags)}")
            print(f"  Auto-tag rules: {len(tag_schema.auto_tag_rules)}")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            return 1
        except ValueError as e:
            print(f"Error: {e}")
            return 1

    # Build deck index (export-backed for MVP).
    export_path = cfg.get("export_path", "resources/Unified-Greek.txt")
    model_map_path = cfg.get("model_field_map", "resources/model_field_map.json")
    lemmatizer = GreekLemmatizer()
    deck = build_from_export(export_path, model_map_path, lemmatizer=lemmatizer)

    # Load candidates
    candidates = [r.__dict__ for r in read_candidates_csv(args.input)]

    # Load cloze stop words if cloze validation is enabled
    cloze_stopwords = None
    if args.validate_cloze:
        from .cloze_validator import GreekStopWords
        try:
            cloze_stopwords = GreekStopWords.load(args.cloze_stopwords)
            print(f"Loaded Greek stop words from: {args.cloze_stopwords}")
            print(f"  Stop words: {len(cloze_stopwords.words)}")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            return 1

    # Analyze (with optional tag hygiene, cloze validation, context analysis, and recommendations)
    results = analyze_candidates(
        candidates,
        deck,
        lemmatizer,
        tag_schema=tag_schema,
        enable_auto_tag=args.auto_tag,
        enable_cloze_validation=args.validate_cloze,
        cloze_stopwords=cloze_stopwords,
        enable_context_analysis=args.analyze_context,
        enable_cloze_recommendations=args.recommend_cloze
    )

    # Report
    write_results_csv(args.out, results, include_tag_hygiene=args.enforce_tags)
    print_summary(
        results,
        include_tag_hygiene=args.enforce_tags,
        include_cloze=args.validate_cloze,
        include_context=args.analyze_context,
        include_recommendations=args.recommend_cloze
    )
    print(f"Wrote report: {args.out}")
    # Persist lemma cache for faster subsequent runs
    lemmatizer.save_cache()
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Generate clean import-ready CSV by removing duplicates and cleaning tags."""
    import csv
    from pathlib import Path

    cfg = load_config(args.config)

    # Load tag schema (required for clean command)
    try:
        tag_schema = load_tag_schema(args.tag_schema)
        print(f"Loaded tag schema from: {args.tag_schema}")
        print(f"  Allowed tags: {len(tag_schema.allowed_tags)}")
        print(f"  Blocked tags: {len(tag_schema.blocked_tags)}")
        if args.auto_tag:
            print(f"  Auto-tag rules: {len(tag_schema.auto_tag_rules)}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Build deck index
    export_path = cfg.get("export_path", "resources/Unified-Greek.txt")
    model_map_path = cfg.get("model_field_map", "resources/model_field_map.json")
    lemmatizer = GreekLemmatizer()
    print(f"Loading reference deck from: {export_path}")
    deck = build_from_export(export_path, model_map_path, lemmatizer=lemmatizer)
    print(f"Loaded {len(deck.notes)} reference cards")

    # Load candidates
    print(f"Reading input cards from: {args.input}")
    candidates = [r.__dict__ for r in read_candidates_csv(args.input)]
    print(f"Loaded {len(candidates)} candidate cards")

    # Analyze with tag hygiene enabled
    print("Analyzing candidates for duplicates...")
    results = analyze_candidates(
        candidates,
        deck,
        lemmatizer,
        tag_schema=tag_schema,
        enable_auto_tag=args.auto_tag,
        enable_cloze_validation=False,
        cloze_stopwords=None,
        enable_context_analysis=False,
        enable_cloze_recommendations=False
    )

    # Filter out duplicates and self-duplicates
    clean_results = []
    duplicate_count = 0
    self_duplicate_count = 0

    for r in results:
        # Skip if it's a duplicate against the reference deck
        if r.warning_level != "none":
            duplicate_count += 1
            continue

        # Skip if it's a self-duplicate within candidates
        if r.self_duplicate_level and r.self_duplicate_level != "none":
            self_duplicate_count += 1
            continue

        clean_results.append(r)

    print(f"\nFiltering results:")
    print(f"  Duplicates against reference deck: {duplicate_count}")
    print(f"  Self-duplicates within candidates:  {self_duplicate_count}")
    print(f"  Clean cards for import:             {len(clean_results)}")

    # Create output directory if needed
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write clean cards with simplified fields (front, back, tags_final)
    fieldnames = ['front', 'back', 'tags']
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in clean_results:
            writer.writerow({
                'front': r.front,
                'back': r.back,
                'tags': r.tags_final or ''  # Use cleaned tags
            })

    print(f"\nWrote clean cards to: {output_path}")

    # Print tag hygiene summary
    from .tag_hygiene import parse_tags

    total_kept = sum(len(parse_tags(r.tags_kept)) for r in clean_results if r.tags_kept)
    total_deleted = sum(len(parse_tags(r.tags_deleted)) for r in clean_results if r.tags_deleted)
    total_auto_added = sum(len(parse_tags(r.tags_auto_added)) for r in clean_results if r.tags_auto_added)
    cards_with_unknown = sum(1 for r in clean_results if r.tags_need_review)

    print(f"\nTag Hygiene Summary (clean cards only):")
    print(f"  Tags kept (allowed):     {total_kept}")
    print(f"  Tags deleted (blocked):  {total_deleted}")
    print(f"  Tags auto-added:         {total_auto_added}")
    print(f"  Cards with unknown tags: {cards_with_unknown}")

    if cards_with_unknown > 0:
        print(f"\nWarning: {cards_with_unknown} cards have unknown tags that need review.")
        print("Consider reviewing the tag schema or manually checking these cards.")

    # Persist lemma cache
    lemmatizer.save_cache()
    return 0


def cmd_lint_deck(args: argparse.Namespace) -> int:
    """Analyze the deck itself for internal duplicates."""
    cfg = load_config(args.config)

    # Build deck index (export-backed for MVP).
    export_path = cfg.get("export_path", "resources/Unified-Greek.txt")
    model_map_path = cfg.get("model_field_map", "resources/model_field_map.json")
    lemmatizer = GreekLemmatizer()
    print(f"Loading deck from: {export_path}")
    deck = build_from_export(export_path, model_map_path, lemmatizer=lemmatizer)
    print(f"Loaded {len(deck.notes)} cards from deck")

    # Analyze deck for internal duplicates
    print("Analyzing deck for internal duplicates...")
    results = analyze_deck_internal(deck, lemmatizer)

    # Filter by minimum level if specified
    if args.min_level:
        level_priority = {"high": 3, "medium": 2, "low": 1}
        min_priority = level_priority.get(args.min_level, 1)
        results = [r for r in results if level_priority.get(r.warning_level, 0) >= min_priority]
        print(f"Filtered to {args.min_level}+ severity: {len(results)} cards")

    # Report
    write_results_csv(args.out, results)
    print_summary(results)
    print(f"Wrote report: {args.out}")
    print(f"Found {len(results)} cards with duplicates (out of {len(deck.notes)} total)")

    # Persist lemma cache for faster subsequent runs
    lemmatizer.save_cache()
    return 0


def cmd_convert_tags(args: argparse.Namespace) -> int:
    """Convert non-standard tags to schema-compliant format."""
    import csv

    # Load tag schema for filtering
    tag_schema = load_tag_schema(args.tag_schema)
    print(f"Loaded tag schema from: {args.tag_schema}")
    print(f"  Allowed tags: {len(tag_schema.allowed_tags)}")

    # Load tag converter
    mapping_path = Path(args.mapping) if args.mapping else None
    converter = load_tag_converter(mapping_path)
    print(f"Loaded tag conversion mapping from: {args.mapping or 'default'}")

    # Read input CSV
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1

    # Process CSV
    converted_cards = []
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if 'front' not in reader.fieldnames or 'back' not in reader.fieldnames:
            print("Error: Input CSV must have 'front' and 'back' columns")
            return 1

        for row in reader:
            tags_string = row.get('tags', '')
            result = converter.convert_card_tags(tags_string, tag_schema=tag_schema)

            tags_converted = ' '.join(result.converted_tags)
            converted_cards.append({
                'front': row['front'],
                'back': row['back'],
                'tags': tags_converted,  # Compatible with lint command
                'tags_original': tags_string,
                'tags_converted': tags_converted,
                'chapter': result.chapter,
                'source': result.source,
                'section': result.section
            })

    # Write output CSV
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ['front', 'back', 'tags', 'tags_original', 'tags_converted', 'chapter', 'source', 'section']
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(converted_cards)

    # Print summary
    total_cards = len(converted_cards)
    with_chapter = sum(1 for c in converted_cards if c['chapter'])
    with_section = sum(1 for c in converted_cards if c['section'])
    total_tags_output = sum(len(c['tags'].split()) for c in converted_cards if c['tags'])
    cards_with_tags = sum(1 for c in converted_cards if c['tags'])

    print(f"Converted {total_cards} cards")
    print(f"  Cards with chapter metadata: {with_chapter}")
    print(f"  Cards with section metadata: {with_section}")
    print(f"  Cards with allowlist tags: {cards_with_tags}")
    print(f"  Total allowlist tags: {total_tags_output}")
    print(f"Wrote converted tags to: {output_path}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ankihoplite", description="Anki-Hoplite prototype CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    lint = sub.add_parser("lint", help="Analyze candidate CSV for duplicates")
    lint.add_argument("--input", required=True, help="Path to candidate CSV (front,back,tags)")
    lint.add_argument("--out", required=True, help="Path to output CSV report")
    lint.add_argument(
        "--config",
        default="resources/config.json",
        help="Path to config.json (optional; defaults will be used if missing)",
    )
    lint.add_argument(
        "--tag-schema",
        default="resources/tag_schema.json",
        help="Path to tag schema JSON (default: resources/tag_schema.json)",
    )
    lint.add_argument(
        "--enforce-tags",
        action="store_true",
        help="Enable tag hygiene enforcement (allowlist/blocklist/unknown detection)",
    )
    lint.add_argument(
        "--auto-tag",
        action="store_true",
        help="Enable auto-tagging based on schema rules (requires --enforce-tags)",
    )
    lint.add_argument(
        "--validate-cloze",
        action="store_true",
        help="Enable cloze context quality validation",
    )
    lint.add_argument(
        "--cloze-stopwords",
        default="resources/greek_stopwords.txt",
        help="Path to Greek stop words file (default: resources/greek_stopwords.txt)",
    )
    lint.add_argument(
        "--analyze-context",
        action="store_true",
        help="Enable context quality analysis (identify isolated vocabulary)",
    )
    lint.add_argument(
        "--recommend-cloze",
        action="store_true",
        help="Enable cloze conversion recommendations for suitable cards",
    )
    lint.set_defaults(func=cmd_lint)

    clean = sub.add_parser("clean", help="Generate clean import-ready CSV (remove duplicates, clean tags)")
    clean.add_argument(
        "--input",
        default="input/input-cards.csv",
        help="Path to candidate CSV (default: input/input-cards.csv)",
    )
    clean.add_argument(
        "--out",
        default="output/clean-cards.csv",
        help="Path to clean output CSV (default: output/clean-cards.csv)",
    )
    clean.add_argument(
        "--config",
        default="resources/config.json",
        help="Path to config.json (optional; defaults will be used if missing)",
    )
    clean.add_argument(
        "--tag-schema",
        default="resources/tag_schema.json",
        help="Path to tag schema JSON (default: resources/tag_schema.json)",
    )
    clean.add_argument(
        "--auto-tag",
        action="store_true",
        help="Enable auto-tagging based on schema rules",
    )
    clean.set_defaults(func=cmd_clean)

    lint_deck = sub.add_parser("lint-deck", help="Analyze deck itself for internal duplicates")
    lint_deck.add_argument("--out", required=True, help="Path to output CSV report")
    lint_deck.add_argument(
        "--config",
        default="resources/config.json",
        help="Path to config.json (optional; defaults will be used if missing)",
    )
    lint_deck.add_argument(
        "--min-level",
        choices=["high", "medium", "low"],
        help="Minimum warning level to include (e.g., --min-level high shows only exact duplicates)",
    )
    lint_deck.set_defaults(func=cmd_lint_deck)

    convert = sub.add_parser("convert-tags", help="Convert non-standard tags to schema-compliant format")
    convert.add_argument("--input", required=True, help="Path to candidate CSV (front,back,tags)")
    convert.add_argument("--out", required=True, help="Path to output CSV with converted tags")
    convert.add_argument(
        "--mapping",
        default="resources/tag_conversion_map.json",
        help="Path to tag conversion mapping JSON (default: resources/tag_conversion_map.json)",
    )
    convert.add_argument(
        "--tag-schema",
        default="resources/tag_schema.json",
        help="Path to tag schema JSON for allowlist filtering (default: resources/tag_schema.json)",
    )
    convert.set_defaults(func=cmd_convert_tags)

    setup = sub.add_parser("setup-cltk", help="Download/ensure CLTK Greek models")
    setup.set_defaults(func=lambda _args: (ensure_cltk_grc_models() or 0))

    doctor = sub.add_parser("doctor", help="Verify CLTK setup and lemma-based matching")
    doctor.add_argument(
        "--sample", action="store_true", help="Run sample analysis on εἶπον -> expect Medium"
    )
    def _doctor(args: argparse.Namespace) -> int:
        lem = GreekLemmatizer()
        print(f"Lemmatizer backend: {lem.backend_name()}")
        for w in ["εἶπον", "ἔλυσα", "λύεις", "λέγω"]:
            print(f"best_lemma('{w}') -> '{lem.best_lemma(w)}'")
        if args.sample:
            cfg = load_config("resources/config.json")
            deck = build_from_export(
                cfg.get("export_path", "resources/Unified-Greek.txt"),
                cfg.get("model_field_map", "resources/model_field_map.json"),
                lemmatizer=lem,
            )
            candidates = [
                {"front": "εἶπον", "back": "I said", "tags": ""},
            ]
            from .detect_duplicates import analyze_candidates

            results = analyze_candidates(candidates, deck, lem)
            for r in results:
                print(
                    f"sample front='{r.front}' -> level={r.warning_level}, reason={r.match_reason}, matches={r.matched_note_ids}"
                )
        return 0
    doctor.set_defaults(func=_doctor)

    return p


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
