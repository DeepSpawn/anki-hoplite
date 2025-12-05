# Anki-Hoplite Prototype Plan

This document captures the current plan, decisions, and step-by-step tasks for building a dry‑run prototype of Anki‑Hoplite. It is designed for handoff across multiple LLM sessions and contributors.

## Project Overview

- Purpose: Middleware “gatekeeper” that ingests candidate Anki cards, normalizes and analyzes Ancient Greek text, and flags potential duplicates before manual import into Anki.
- Prototype scope (Phase 1): Focus on Feature A — Smart Duplicate Detection — with an end‑to‑end flow from CSV input to a lint report CSV output. Read‑only integration with the existing “Unified Greek” deck. Preparation work included for Feature D (Core 500) but not required to finish MVP.
- Output: Dry‑run only. Produce a CSV report with warnings (High/Medium/Low), reasons, and matched note references. No automatic write to Anki.

## Current Decisions & Constraints (Confirmed)

- Priority: Feature A first, then D later.
- End‑to‑end: Prefer a working vertical slice enabling quick iteration.
- Input format: CSV with headers `front,back,tags`.
- Existing deck export: `resources/Unified-Greek.txt` (use as the initial index source).
- Lemmatizer: CLTK (with downloads allowed for required corpora).
- Normalization policy: NFC, strip punctuation, lowercase, and strip accents for matching (retain original for display).
- Stopwords: Use CLTK defaults.
- Duplicate search scope: Specific deck “Unified Greek”.
- English-side matching: Depends on note type; derive via a model/field mapping file.
- Warning levels: Keep High/Medium/Low as specified.
- Cloze syntax: Defer to inspection of deck export (out of MVP scope, but mapping must avoid cloze misclassification).
- Core 500 list: `resources/greek-core-list.xml` (parse later for Feature D).
- AnkiConnect: Available at `localhost:8765`, read‑only for now.
- Platform: Python 3.10+.
- UI: Minimal web UI acceptable but optional for MVP.

## High-Level Architecture (Prototype)

1. Input: Candidate cards CSV (`front,back,tags`).
2. Processing Engine:
   - Normalization utilities (NFC, punctuation strip, lowercase, accent strip, final sigma normalization).
   - Lemmatization wrapper using CLTK with caching.
   - Duplicate detection logic (exact Greek, lemma match, English gloss).
3. Reference Index:
   - Build from `resources/Unified-Greek.txt` initially; optional AnkiConnect backend later.
4. Output: `out/lint_results.csv` with per‑row analysis and summary.

## Directory Layout (Target)

- `src/anki_hoplite/`
  - `ingest.py` — CSV reader for candidate input; export helpers.
  - `normalize.py` — Unicode normalization and Greek matching helpers.
  - `lemmatize.py` — CLTK setup, lemmatization API, caching.
  - `deck_index.py` — Build and query reference indexes from export (and later AnkiConnect).
  - `detect_duplicates.py` — Rule engine for High/Medium/Low warnings.
  - `report.py` — CSV report writer and summary.
  - `cli.py` — CLI entrypoint wiring the pipeline.
- `resources/`
  - `Unified-Greek.txt` — Existing deck export (provided).
  - `greek-core-list.xml` — Core 500 data (provided; later).
  - `model_field_map.json` — Maps note model → greek_field, english_field, tags policy (to be authored).
  - `config.json` — Settings (paths, deck name, normalization flags, dry_run=true).
- `out/`
  - `lint_results.csv` — Analysis output (generated).
- `docs/`
  - `PLAN.md` — This plan document.

## Phased Plan & Tasks

### Progress Update (Dec 05)
- Phase 0 (Project Setup): completed.
- Phase 1 (Input & Config): CSV ingest and base config created; model_field_map.json scaffolded (needs population as more models appear).
- Phase 2 (Normalization Utilities): completed.
- Phase 3 (Lemmatization Wrapper): completed initial wrapper; CLTK setup helper and CLI command added.
- Phase 4 (Existing Deck Index): export parsing implemented; indexes (exact/lemma/English) build from `resources/Unified-Greek.txt`.
- Phase 5–6 (Detection + Reporting): wiring completed; CLI produces CSV and summary; sample validated.
- Phase 7+ (UI, Core 500, etc.): deferred.

Validation: Ran CLI on `samples/candidates_sample.csv` (4 rows). Results -> High:1, Medium:0 (until CLTK corpora fetched), Low:1, None:2. Output at `out/lint_results.csv`.

Dependency mgmt: `pyproject.toml` added; `uv` documented in README; CLI `setup-cltk` added to fetch Greek models when network is available.

Next action: Fetch CLTK corpora locally (`uv run ankihoplite setup-cltk`) to enable lemma-based matching (expect Medium hits), refine tokenization if needed, and expand `resources/model_field_map.json` as additional models are encountered.

### Phase 0: Project Setup
- Scaffold Python package structure under `src/anki_hoplite/`.
- Add dependencies: `cltk`, `unicodedata2` (or stdlib `unicodedata`), `python-dateutil` (if needed), `requests` (AnkiConnect later), `streamlit` (optional), and `ruff/black` if formatters are already configured in repo.
- Create `config.json` with defaults: deck name, paths, normalization flags, dry_run.

### Phase 1: Input & Config
- Implement robust CSV ingest for `front,back,tags` (UTF‑8, quoted fields, empty tag support).
- Parse `resources/Unified-Greek.txt` to enumerate note types and fields.
- Author `resources/model_field_map.json` mapping each note model to:
  - `greek_field`: primary Greek field for matching (front for vocab models).
  - `english_field`: gloss/translation field for low‑level matches.
  - `ignore`: boolean for models we skip (e.g., cloze if not handled yet).

### Phase 2: Normalization Utilities
- Implement `normalize_text_nfc(text)` — apply NFC early.
- Implement `strip_accents(text)` — NFD + remove combining marks.
- Implement `normalize_greek_for_match(text)` — NFC → lowercase → punctuation strip (Greek & ASCII) → accent strip → final sigma normalization.
- Provide helpers for punctuation tables and a deterministic pipeline.

### Phase 3: Lemmatization Wrapper
- Initialize CLTK for Ancient Greek; download required corpora on first run.
- Implement `lemmatize(text)` returning best lemma for single‑word inputs; return list for multi‑word.
- Add in‑memory and optional JSON cache (e.g., `out/lemma_cache.json`).

### Phase 4: Existing Deck Index (Read‑Only)
- From `Unified-Greek.txt`, extract per‑note:
  - `model` → resolve fields via `model_field_map.json`.
  - `greek_text`, `english_text`, note id.
- Build indexes:
  - Exact Greek index: normalized string → {note_ids}.
  - Lemma index: normalized lemma (accentless) → {note_ids}.
  - English index: normalized English (lower/punct‑stripped) → {note_ids} (optional but recommended).
- Provide a backend abstraction that could later swap to AnkiConnect (`findNotes` + `notesInfo`) limited to the “Unified Greek” deck.

### Phase 5: Duplicate Detection Logic
- For each candidate row (`front, back, tags`):
  - Produce normalized Greek `g_norm` and lemma `g_lemma_norm`.
  - Check indexes in order:
    - High: exact Greek match → High warning.
    - Medium: lemma match (no exact match) → Medium warning.
    - Low: English gloss match (no exact/lemma) → Low warning.
  - Attach `match_reason`, `matched_note_ids`, and the resolved `warning_level`.

### Phase 6: Reporting & Export
- Emit `out/lint_results.csv` with columns:
  - `front`, `back`, `tags`, `normalized_greek`, `lemma`, `warning_level`, `match_reason`, `matched_note_ids`.
- Print console summary counts by High/Medium/Low/None.
- Include suggested action field derived from level: `likely-duplicate` (High), `review` (Medium/Low), `keep` (None).

### Phase 7: Minimal UI (Optional)
- Streamlit app with:
  - File uploader for candidate CSV.
  - Source selector: Export vs AnkiConnect (export only for MVP).
  - Run button to execute pipeline; filter table by `warning_level`.
  - Download button for the results CSV.

### Phase 8: Core 500 Prep (Next Iteration)
- Parse `resources/greek-core-list.xml` into a lemma set.
- Normalize lemmas with the same pipeline; tag result rows with `is_core_vocab`.
- Provide coverage summary and “new vs mastered” flags.

### Phase 9: Validation & Examples
- Create small sample CSV to trigger High/Medium/Low paths.
- Test edge cases: multi‑word fronts, enclitics, punctuation, sigma variants, accent variants.
- Verify performance against full `Unified-Greek.txt` export.

## Data & Matching Policies

- Greek normalization pipeline for matching: NFC → lowercase → punctuation strip → accent strip → final sigma normalization → collapse whitespace.
- Punctuation: include ASCII and Greek punctuation; retain apostrophe policy as needed (e.g., elision) — decision: strip for matching initially.
- Lemma selection: prefer head lemma; if multiple, pick the most frequent or first from CLTK; record alternatives for debugging if helpful.
- English normalization for match: lowercase + punctuation strip + collapse whitespace.

## Open Questions / Assumptions to Revisit

- Are CSV tags space‑separated (Anki style) acceptable for the prototype? (Assume yes.)
- Model mapping reliably identifies gloss fields for all relevant models? (Create initial map; revise as needed.)
- Handling cloze models: skip for MVP or map carefully to avoid false positives?
- English matching robustness: should we remove parentheticals like “(accusative)”? (Defer; start simple.)
- Core 500 matching policy: lemma‑only or include headword variants? (Decide in Feature D.)

## Handoff Notes (For Future Sessions)

- Primary entrypoint to build next: `src/anki_hoplite/cli.py` with a command like `ankihoplite lint --input candidate.csv --out out/lint_results.csv`.
- Implement modules in this order for momentum:
  1) `normalize.py`, 2) `lemmatize.py`, 3) `deck_index.py`, 4) `ingest.py`, 5) `detect_duplicates.py`, 6) `report.py`, 7) `cli.py`.
- Use `resources/Unified-Greek.txt` to draft `resources/model_field_map.json` by inspecting common models and fields.
- Prefer pure‑Python, no global state; use simple `dataclasses` for row/result records.
- Add a lightweight lemma cache at `out/lemma_cache.json` to speed iteration.

## Definition of Done (Prototype A)

- CLI runs locally on Python 3.10+ against a candidate CSV and produces `out/lint_results.csv`.
- High/Medium/Low duplicate detection works using the export index.
- Summary counts are printed and match expectations on sample cases.
- No writes to Anki; all operations are read‑only.

## Quick Start (Planned)

- Create a virtualenv, install deps, and run: `python -m anki_hoplite.cli lint --input path/to/candidates.csv --out out/lint_results.csv`.
- Optional: `streamlit run streamlit_app.py` for a minimal UI once CLI is working.
