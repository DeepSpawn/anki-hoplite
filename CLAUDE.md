# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Anki-Hoplite is a middleware "gatekeeper" for Ancient Greek Anki cards. It analyzes candidate cards (CSV), normalizes Greek text, performs lemmatization, and detects duplicates against existing decks before import into Anki. The prototype focuses on smart duplicate detection using three levels: High (exact Greek match), Medium (lemma match), and Low (English gloss match).

## Development Commands

### Environment Setup
```bash
# Install dependencies (using uv for fast dependency management)
uv sync

# Install CLTK Greek corpora (requires network)
uv run ankihoplite setup-cltk
```

### Running the Application
```bash
# Run the linter on candidate CSV
uv run ankihoplite lint --input samples/candidates_sample.csv --out out/lint_results.csv

# Verify CLTK setup and test lemmatization
uv run ankihoplite doctor

# Run doctor with sample analysis
uv run ankihoplite doctor --sample
```

### Testing
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=anki_hoplite

# Run specific test file
uv run pytest tests/test_normalize.py

# Run specific test
uv run pytest tests/test_lemmatize.py::test_best_lemma_extraction -v
```

### Running as Module
```bash
# Alternative way to run CLI
python -m anki_hoplite.cli lint --input <input.csv> --out <output.csv>
```

## Architecture

### Core Pipeline
The application follows a sequential pipeline:
1. **Input** (`ingest.py`) - Read candidate CSV with `front,back,tags` format
2. **Normalization** (`normalize.py`) - Apply Greek-specific text normalization
3. **Lemmatization** (`lemmatize.py`) - Extract lemmas using CLTK with caching
4. **Index Building** (`deck_index.py`) - Build searchable indexes from deck exports
5. **Detection** (`detect_duplicates.py`) - Match candidates against indexes
6. **Reporting** (`report.py`) - Generate CSV report and summary

### Key Modules

#### `normalize.py` - Greek Text Normalization
Implements the normalization policy for Ancient Greek matching:
- **NFC normalization** - Unicode consistency
- **Lowercase** - Case-insensitive matching
- **Punctuation stripping** - Remove all Unicode punctuation
- **Accent stripping** - Remove combining marks via NFD decomposition
- **Final sigma normalization** - Normalize ς to σ
- **Whitespace collapse** - Normalize and trim whitespace

This pipeline is critical for reliable duplicate detection despite variations in polytonic Greek input.

#### `lemmatize.py` - CLTK Integration
Wraps CLTK (Classical Language Toolkit) for Ancient Greek lemmatization:
- **Lazy initialization** - CLTK backend loaded on first use
- **Multiple backend support** - Tries `GreekBackoffLemmatizer` (CLTK 1.5+), then falls back to `NLP` pipeline
- **Persistent caching** - Saves lemmas to `out/lemma_cache.json` to speed subsequent runs
- **Override support** - Manual corrections via `resources/lemma_overrides.json`
- **Graceful degradation** - Falls back to normalized token if CLTK unavailable

Key methods:
- `lemmatize_token(token)` - Lemmatize single token with caching
- `best_lemma(text)` - Extract best lemma from potentially multi-word text
- `save_cache()` - Persist cache to disk

#### `deck_index.py` - Reference Deck Indexing
Builds searchable indexes from Anki deck exports:
- **Three indexes** - `exact_greek`, `lemma_index`, `english_index`
- **Export parsing** - Reads tab-separated Anki exports with header metadata
- **Model mapping** - Uses `resources/model_field_map.json` to map note types to Greek/English field positions
- **HTML cleaning** - Strips sound tags, HTML tags, and unescapes entities
- **Shared lemmatizer** - Uses provided `GreekLemmatizer` instance for consistency

Export format expectations:
- Tab-separated with header comments (`#separator:tab`, `#guid column:1`, etc.)
- Columns: `guid`, `notetype`, `deck`, `fields...`, `tags`

#### `detect_duplicates.py` - Duplicate Detection Logic
Implements three-tier warning system:
- **High** - Exact Greek string match (after normalization)
- **Medium** - Lemma match without exact match (different inflections)
- **Low** - English gloss match without Greek match (potentially different words)
- **None** - No match found

Returns `DetectionResult` dataclass with warning level, reason, and matched note IDs.

### Configuration

Configuration is loaded from `resources/config.json` with defaults in `cli.py:load_config()`:
- `deck_name` - Target deck name
- `export_path` - Path to deck export file
- `model_field_map` - Path to model-field mapping JSON
- `normalization` - Normalization flags (all currently enabled)
- `dry_run` - Always true for prototype

### CLTK Integration Notes

CLTK requires downloading Ancient Greek corpora on first use. The app handles this gracefully:
- Run `setup-cltk` command to download models proactively
- Backend auto-detection tries modern API first, falls back to legacy
- Without CLTK, lemmatization returns the normalized token (limited functionality)

**macOS Intel (x86_64) Users**: PyTorch (CLTK dependency) has no PyPI wheels for x86_64 macOS. Use the Conda environment instead:
```bash
micromamba create -f environment.yml
micromamba activate anki-hoplite
python -m anki_hoplite.cli doctor --sample
```

### Data Flow Example

Input CSV (`front,back,tags`):
```
εἶπον,I said,
λύεις,you loose,verb
```

Processing:
1. Normalize: `εἶπον` → `ειπον` (exact), lemmatize → `ειπον` (lemma)
2. Normalize: `λύεις` → `λυεις` (exact), lemmatize → `λυω` (lemma)
3. Check against deck indexes (exact → lemma → English)
4. Generate warnings and matched note IDs

Output CSV includes: `front`, `back`, `tags`, `normalized_greek`, `lemma`, `warning_level`, `match_reason`, `matched_note_ids`

## Testing Strategy

The test suite uses mocked CLTK lemmatizers to avoid dependency on downloaded models:
- `test_integration.py` - End-to-end pipeline tests with `MockBackoffLemmatizer`
- `test_normalize.py` - Unicode normalization edge cases
- `test_lemmatize.py` - Lemmatization with mocked backends
- `test_detect_duplicates.py` - Detection logic with known inputs

When writing tests, use the `mock_cltk_backend` fixture to provide deterministic lemmatization.

## Important Implementation Details

### Unicode Normalization is Critical
Ancient Greek text can have precomposed characters (`ά`) or combining characters (`α` + `´`). Always use NFC normalization via `normalize_text_nfc()` before any string operations. The `normalize_greek_for_match()` function applies the full normalization pipeline.

### Shared Lemmatizer Instance
Pass the same `GreekLemmatizer` instance through the pipeline to leverage caching:
```python
lemmatizer = GreekLemmatizer()
deck = build_from_export(export_path, model_map_path, lemmatizer=lemmatizer)
results = analyze_candidates(candidates, deck, lemmatizer)
lemmatizer.save_cache()  # Persist for next run
```

### Model Field Mapping
The `resources/model_field_map.json` maps Anki note types to field positions:
```json
{
  "defaults": {"greek_index": 0, "english_index": 1, "ignore": false},
  "models": {
    "Cloze Model": {"ignore": true},
    "Custom Vocab": {"greek_index": 1, "english_index": 0}
  }
}
```

Extend this as new note types are encountered in exports.

## Future Development

The prototype is scoped to Feature A (duplicate detection). Documented but deferred features:
- **Feature B** - Tag hygiene with allowlist/blocklist
- **Feature C** - Cloze context validation
- **Feature D** - Core 500 Greek vocabulary coverage tracking

See `docs/PLAN.md` for full roadmap and `spec.md` for original feature specifications.
