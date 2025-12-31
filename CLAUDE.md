# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Anki-Hoplite is a middleware "gatekeeper" for Ancient Greek Anki cards. It analyzes candidate cards (CSV), normalizes Greek text, performs lemmatization, and detects duplicates against existing decks before import into Anki. The prototype focuses on smart duplicate detection using three levels: High (exact Greek match), Medium (lemma match), and Low (English gloss match).

### Anki Integration Model

The application uses **deck export files** (not AnkiConnect) to access the reference deck:
- **Export file:** `resources/Unified-Greek.txt` (tab-separated, ~1000 cards)
- **Checked into git:** Allows running in GitHub Codespaces without Anki installed
- **Manual updates:** Periodically re-export and commit when deck grows significantly
- **Format:** Tab-separated with metadata headers (`#separator:tab`, `#html:true`, etc.)

To update the reference deck:
1. Open Anki Desktop and select "Unified Greek" deck
2. File → Export → "Notes in Plain Text (.txt)"
3. Ensure "Include HTML and media references" is checked
4. Save as `resources/Unified-Greek.txt` (overwrite existing)
5. Commit and push the updated export

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
2. **Tag Hygiene** (`tag_hygiene.py`) - Optional: Classify tags, apply auto-tagging (if `--enforce-tags`)
3. **Normalization** (`normalize.py`) - Apply Greek-specific text normalization
4. **Lemmatization** (`lemmatize.py`) - Extract lemmas using CLTK with caching
5. **Index Building** (`deck_index.py`) - Build searchable indexes from deck exports
6. **Detection** (`detect_duplicates.py`) - Match candidates against indexes, merge tag results
7. **Cloze Validation** (`cloze_validator.py`) - Optional: Analyze cloze context quality (if `--validate-cloze`)
8. **Reporting** (`report.py`) - Generate CSV report and summary (with optional tag/cloze statistics)

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

Returns `DetectionResult` dataclass with warning level, reason, and matched note IDs (+ tag hygiene fields if enabled).

#### `tag_hygiene.py` - Tag Hygiene Enforcement (Feature B)
Implements allowlist/blocklist enforcement and pattern-based auto-tagging:
- **Allowlist enforcement** - Only tags in the allowlist are kept
- **Blocklist enforcement** - Tags in the blocklist are silently removed
- **Unknown tag flagging** - Tags not in allowlist/blocklist are flagged for manual review
- **Auto-tagging** - Pattern-based rules automatically add tags based on Greek text

Key components:
- `TagSchema` - Configuration for allowed/blocked tags and auto-tag rules
- `CardTagResult` - Analysis result for a single card's tags
- `analyze_card_tags()` - Main analysis function that classifies tags and applies auto-tagging

Schema file (`resources/tag_schema.json`):
```json
{
  "allowed_tags": ["noun", "verb", "aorist", "masculine", ...],
  "blocked_tags": ["tmp", "ch_1", "import_2023", ...],
  "case_sensitive": false,
  "normalize_tags": true,
  "auto_tag_rules": [
    {
      "name": "masculine_article",
      "pattern": "^ὁ$|^τοῦ$|^τῷ$|^τόν$",
      "tags": ["article", "masculine"],
      "match_field": "front"
    }
  ]
}
```

CLI usage:
```bash
# Enable tag hygiene
uv run ankihoplite lint --input candidates.csv --out results.csv --enforce-tags

# Enable tag hygiene + auto-tagging
uv run ankihoplite lint --input candidates.csv --out results.csv --enforce-tags --auto-tag
```

Tag hygiene results are added to the CSV output with columns:
- `tags` - Original tags (preserved)
- `tags_kept` - Tags that passed allowlist check
- `tags_deleted` - Blocked tags that were removed
- `tags_unknown` - Tags needing manual review
- `tags_auto_added` - Tags added by auto-tagging rules
- `tags_final` - Final tags (kept + auto-added)
- `tags_need_review` - Boolean flag for unknown tags

#### `cloze_validator.py` - Cloze Context Validation (Feature C)
Implements cloze context quality analysis to identify weak/ambiguous cloze cards:
- **Context Token Count** - Number of Greek words outside cloze deletions
- **Deletion Density Ratio** - Percentage of tokens removed by cloze deletions
- **Content Word Density** - Ratio of content words to stop words in context
- **Multi-Factor Quality Scoring** - Combines metrics into graduated levels: excellent/good/weak/poor

Key components:
- `ClozeParseResult` - Parsed cloze syntax (deletions, context, hints)
- `ClozeAnalysis` - Complete analysis with metrics and quality classification
- `GreekStopWords` - Stop word list manager for content analysis
- `analyze_cloze_card()` - Main analysis function

Quality classification thresholds:
- **excellent**: context ≥5 tokens AND deletion ≤50% AND content density ≥0.40
- **good**: context ≥3 tokens AND deletion ≤60% AND content density ≥0.30
- **weak**: context ≥2 tokens OR (context ≥1 AND deletion ≤80%)
- **poor**: all others (0-1 tokens, or >80% deletion)

Stop words file (`resources/greek_stopwords.txt`):
```
# Plain text file, one word per line, normalized (lowercase, no accents)
ο
η
το
και
δε
εστιν
...
```

CLI usage:
```bash
# Validate cloze quality with default stop words
uv run ankihoplite lint --input candidates.csv --out results.csv --validate-cloze

# Use custom stop word list
uv run ankihoplite lint --input candidates.csv --out results.csv \
    --validate-cloze --cloze-stopwords resources/custom_stopwords.txt

# Combine all features
uv run ankihoplite lint --input candidates.csv --out results.csv \
    --enforce-tags --auto-tag --validate-cloze
```

Cloze validation results are added to the CSV output with columns:
- `cloze_quality` - Quality classification (excellent/good/weak/poor or empty if not cloze)
- `cloze_context_tokens` - Number of context tokens
- `cloze_deletion_ratio` - Deletion percentage (0.0-1.0)
- `cloze_content_density` - Content word density (0.0-1.0)
- `cloze_reasons` - Space-separated reason codes (e.g., "low_context high_deletion")

**Why improved over spec.md heuristics:**
1. Token-based metrics (vs character-based) are more semantically meaningful for inflected Greek
2. Multi-factor scoring combines context, deletion, and content metrics
3. Graduated quality levels (excellent/good/weak/poor) vs binary flags
4. Content word density is more informative than "only stop words" check
5. Greek-aware tokenization handles polytonic text correctly

### Configuration

Configuration is loaded from `resources/config.json` with defaults in `cli.py:load_config()`:
- `deck_name` - Target deck name
- `export_path` - Path to deck export file
- `model_field_map` - Path to model-field mapping JSON
- `tag_schema` - Path to tag schema JSON (default: `resources/tag_schema.json`)
- `tag_hygiene` - Tag hygiene settings (enabled, auto_tag)
- `normalization` - Normalization flags (all currently enabled)
- `dry_run` - Always true for prototype

Note: Tag hygiene is controlled via CLI flags (`--enforce-tags`, `--auto-tag`), not config file, to make it explicit.

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

Output CSV (without tag hygiene): `front`, `back`, `tags`, `normalized_greek`, `lemma`, `warning_level`, `match_reason`, `matched_note_ids`

Output CSV (with `--enforce-tags`): Adds tag hygiene columns: `tags_kept`, `tags_deleted`, `tags_unknown`, `tags_auto_added`, `tags_final`, `tags_need_review`

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

### Implemented Features
- **Feature A** - Duplicate detection (High/Medium/Low warning levels)
- **Feature B** - Tag hygiene with allowlist/blocklist and auto-tagging
- **Feature C** - Cloze context validation with multi-factor quality scoring

### Documented but Deferred Features
- **Feature D** - Core 500 Greek vocabulary coverage tracking

See `docs/PLAN.md` for full roadmap and `spec.md` for original feature specifications.
