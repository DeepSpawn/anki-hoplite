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

    # Analyze (with optional tag hygiene)
    results = analyze_candidates(
        candidates,
        deck,
        lemmatizer,
        tag_schema=tag_schema,
        enable_auto_tag=args.auto_tag
    )

    # Report
    write_results_csv(args.out, results, include_tag_hygiene=args.enforce_tags)
    print_summary(results, include_tag_hygiene=args.enforce_tags)
    print(f"Wrote report: {args.out}")
    # Persist lemma cache for faster subsequent runs
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
    lint.set_defaults(func=cmd_lint)

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
