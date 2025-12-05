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
from .detect_duplicates import analyze_candidates
from .report import write_results_csv, print_summary
from .cltk_setup import ensure_cltk_grc_models


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

    # Build deck index (export-backed for MVP).
    export_path = cfg.get("export_path", "resources/Unified-Greek.txt")
    model_map_path = cfg.get("model_field_map", "resources/model_field_map.json")
    deck = build_from_export(export_path, model_map_path)

    # Load candidates
    candidates = [r.__dict__ for r in read_candidates_csv(args.input)]

    # Analyze
    lemmatizer = GreekLemmatizer()
    results = analyze_candidates(candidates, deck, lemmatizer)

    # Report
    write_results_csv(args.out, results)
    print_summary(results)
    print(f"Wrote report: {args.out}")
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
    lint.set_defaults(func=cmd_lint)

    setup = sub.add_parser("setup-cltk", help="Download/ensure CLTK Greek models")
    setup.set_defaults(func=lambda _args: (ensure_cltk_grc_models() or 0))

    return p


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
