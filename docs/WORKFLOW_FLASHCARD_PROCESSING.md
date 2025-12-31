# Flashcard Processing Workflow Documentation

## Session Goal
Process 118 Athenaze Chapter 3 flashcards (sentence-mined from reading) to minimize redundancy, ensure contextual learning, and support morphology pattern recognition for Ancient Greek study with a daily limit of 30 new cards.

## Final Output
103 polished cards ready for Anki import with:
- Clean, standardized tags (morphological only)
- 13 cloze conversions applied
- 10 redundant isolated vocabulary removed
- 2 exact duplicates removed
- Self-duplicates identified for review

---

## Workflow Phases

### Phase 1: Initial Planning & Requirements Gathering

**User Request:**
> "Run a lint and edit pass over CSV file of potential flashcards... minimize redundancy, ensure new vocabulary has a sentence fragment with it to help it be learned in context, and for the cards to allow me to learn the patterns and morphology"

**Requirements Clarified Through Questions:**
1. **Isolated vocabulary cards (23 found)** - User wants to flag for manual review to add context
2. **Tag cleanup** - Auto-convert non-standard tags (3pl → third_person plural, acc → accusative)
3. **Self-duplicates** - Check within candidate set, not just against reference deck
4. **Cloze recommendations** - Suggest which cards to convert to cloze format

**Key Insight:** User selected all 4 options (flag no-context, auto-convert tags, check self-duplicates, suggest cloze). This indicates a comprehensive approach is desired.

---

### Phase 2: Implementation (4 Phases)

#### Phase 1: Tag Conversion System
**Files Created:**
- `src/anki_hoplite/tag_converter.py`
- `resources/tag_conversion_map.json`
- Added `convert-tags` CLI command

**Purpose:** Convert non-standard tags to schema-compliant format

**Initial Implementation:**
```bash
uv run ankihoplite convert-tags \
  --input resources/input-cards.csv \
  --out out/input-cards-normalized.csv
```

**Problem Encountered:** Output had 220 unknown tags across 114 cards - too much noise!

**User Feedback:**
> "That has 115 output rows for 118 input rows - if I review that I may as well have done the edit pass by hand. Let's cut down the noise - let's strip all tags that are not in the allow list after normalization"

**Root Cause:** Organizational tags (ch3, athenaze1, reading, wb3a) were being flagged as unknown instead of being filtered out.

**Solution - Iteration 1:**
- Modified `tag_converter.py` to accept `tag_schema` parameter
- Added `is_organizational_tag()` method to identify chapter/section markers
- Extract organizational tags to metadata columns (chapter, source, section)
- Filter converted tags against allowlist before returning
- Only keep morphological tags

**Result After Fix:**
- 0 unknown tags (down from 220)
- 0 cards needing review (down from 114)
- 263 total allowlist tags across 109 cards
- Noise eliminated!

**Lesson Learned:** Tag conversion must include aggressive filtering. Organizational metadata belongs in separate columns, not in the tags field.

---

#### Phase 2: Self-Duplicate Detection
**Files Modified:**
- `src/anki_hoplite/detect_duplicates.py`

**Purpose:** Find duplicates within candidate set (not just vs. reference deck)

**Implementation:**
- Added `analyze_candidates_self_duplicates()` function
- Extended `DetectionResult` dataclass with 3 new fields
- Integrated automatically into `analyze_candidates()` (no flag needed)

**Results:**
- 78 self-duplicates found (2 exact, 76 lemma matches)
- Exact duplicates provided row numbers for easy deletion

**No iteration needed** - worked correctly first time.

---

#### Phase 3: Context Analysis
**Files Created:**
- `src/anki_hoplite/context_analyzer.py`

**Purpose:** Classify cards by contextual richness and flag isolated vocabulary

**Implementation:**
- Token-based classification (rich ≥5, minimal 3-4, phrase 2-3, isolated 1)
- Greek-aware tokenization (handles cloze syntax, punctuation, accents)
- CLI flag: `--analyze-context`

**Results:**
- 13 rich context, 12 minimal, 66 phrase fragments, 23 isolated
- Recommendations: 25 good, 66 consider enhancing, 23 needs context

**No iteration needed** - worked correctly first time.

---

#### Phase 4: Cloze Recommendations
**Files Created:**
- `src/anki_hoplite/cloze_recommender.py`

**Purpose:** Suggest cards to convert to cloze deletion format

**Implementation:**
- Multi-factor scoring (context quality, duplicate status, target word identification)
- Confidence scores (0.0-1.0)
- Suggested cloze syntax generation
- CLI flag: `--recommend-cloze`

**Results:**
- 75 total recommendations, 13 high confidence (≥0.75)

**User Request:**
> "Please make the suggested Cloze format changes to the input-cards.csv"

**Automated Application:**
Applied all 13 high-confidence cloze conversions automatically to input file.

**No iteration needed** - worked correctly first time.

---

### Phase 3: Redundancy Cleanup

**User Request:**
> "For each of the isolated vocabulary cards, can you check to see if that vocab is covered already in the primary deck, eg I know καλεῖ is but some like λύει are new words"

**Problem:** The lint was reporting all 23 isolated cards as "new" but user knew some existed in deck.

**Root Cause:** Duplicate detection matches ENTIRE Greek field:
- Deck has: `τὸν δοῦλον καλεῖ` (καλεῖ in context)
- Candidate has: `καλεῖ` (isolated)
- No match because strings differ

**Solution:** Built word-in-context checker to search for isolated word appearing anywhere in deck cards.

**Results:**
- 7 isolated cards already covered in deck (εἶ, καλεῖ, λάμβανε, καθεύδεις, ἐλαύνω, πάρεστι(ν), εἰσί(ν))
- 16 truly new words

**User Request:**
> "Remove the 7 redundant isolated cards, and any that already have contextual examples in the input file"

**Automated Removal:**
- 7 redundant (in deck)
- 3 with contextual examples in file (λύουσι(ν), προσχωροῦσι(ν), μένουσι(ν))
- Total removed: 10 isolated cards

**Final isolated count:** 13 cards (truly new vocabulary with no context available)

---

### Phase 4: Final Cleanup

**User Question:**
> "Have you cleaned up the tags in the input file yet?"

**Issue:** Tags were cleaned in `out/input-cards-normalized.csv` but original `resources/input-cards.csv` still had raw tags.

**Solution:** Applied tag conversion directly to input file in-place.

**Before:**
```csv
οἱ δὲ βόες ἕλκουσι,but the oxen are dragging,athenaze1 ch3 reading 3pl
```

**After:**
```csv
οἱ δὲ βόες ἕλκουσι,but the oxen are dragging,plural third_person
```

**User Request:**
> "Perfect, this session has been going for a while - please review the current changes and then commit and push"

**Committed:** All changes with comprehensive commit message.

---

## Workflow Summary (Actual Steps Taken)

1. **Initial lint** (with all features enabled)
   - Result: 220 unknown tags, too much noise

2. **Tag conversion fix** (add allowlist filtering)
   - Result: 0 unknown tags, noise eliminated

3. **Apply cloze recommendations** (13 high-confidence)
   - Result: Cards converted to cloze format

4. **Identify redundant isolated cards**
   - Check against deck (7 found)
   - Check against input file (3 found)
   - Result: 10 removed

5. **Clean tags in input file**
   - Apply conversion in-place
   - Result: Ready for import

6. **Commit and push**
   - Clean repository state

---

## Pain Points & Manual Steps

### Manual Interventions Required

1. **Initial noise from unknown tags**
   - Had to iterate on tag conversion to add filtering
   - Required understanding of what tags were organizational vs. morphological

2. **Cloze application required explicit request**
   - System identified 13 candidates but didn't auto-apply
   - User had to ask for application

3. **Redundancy check required two passes**
   - First: lint showed "new" but user knew some existed
   - Second: built custom checker to search within deck cards
   - Third: user requested removal

4. **Tag cleanup happened in wrong file**
   - Cleaned output file but not input file
   - Required explicit question from user to notice

5. **Manual duplicate removal**
   - User said "I have manually removed the duplicate" (2 exact duplicates)
   - System identified them but user had to edit file

### Questions That Required User Input

1. **How to handle isolated vocabulary?** (flag, leave, or find examples)
2. **How to handle tag cleanup?** (auto-convert, flag, or keep custom)
3. **Check self-duplicates?** (yes/no)
4. **Recommend cloze conversions?** (yes/no)

---

## Ideal Automated Pipeline (Future Goal)

### Input
Raw LLM-generated candidate Anki cards CSV with messy tags and potential issues.

### Desired Output
Polished CSV ready for Anki import with:
- Clean, standardized tags
- No redundant cards
- Contextual learning support
- Optimal format (cloze where appropriate)

### Proposed Automated Workflow

```bash
# Single command that does everything
python -m anki_hoplite.cli process-cards \
  --input raw-llm-cards.csv \
  --deck-export resources/Unified-Greek.txt \
  --out polished-cards.csv \
  --auto-apply-cloze \              # NEW: Auto-apply high-confidence cloze
  --remove-redundant \              # NEW: Auto-remove cards in deck
  --remove-exact-duplicates \       # NEW: Auto-remove self-duplicates
  --min-context-tokens 2 \          # NEW: Flag or remove isolated vocab
  --cloze-confidence-threshold 0.75 # NEW: Only apply high-confidence cloze
```

### Required Enhancements

#### 1. Auto-Apply Cloze Conversions (Currently Manual)
**Current:** Recommendations generated, user must apply
**Desired:** Auto-apply recommendations above confidence threshold

**Implementation:**
```python
def cmd_process_cards(args):
    # ... existing analysis ...

    if args.auto_apply_cloze:
        for idx, result in enumerate(results):
            if result.cloze_recommended and result.cloze_confidence >= args.cloze_confidence_threshold:
                # Apply cloze transformation in-place
                candidates[idx]['front'] = apply_cloze(
                    candidates[idx]['front'],
                    result.cloze_suggestion
                )
```

**Config needed:**
- Confidence threshold (default: 0.75)
- Override flag to review before applying

---

#### 2. Auto-Remove Redundant Cards (Currently Manual)
**Current:** Self-duplicates identified, user must remove
**Desired:** Auto-remove exact duplicates and cards already in deck

**Implementation:**
```python
def cmd_process_cards(args):
    # ... existing analysis ...

    if args.remove_redundant:
        # Remove exact self-duplicates (keep first occurrence)
        candidates = remove_exact_duplicates(candidates, results)

        # Remove isolated cards already in deck
        if args.remove_deck_duplicates:
            candidates = remove_cards_in_deck(candidates, deck, lemmatizer)
```

**Config needed:**
- `remove_exact_duplicates` (bool) - Remove high-level self-duplicates
- `remove_deck_duplicates` (bool) - Remove isolated vocab in deck
- `remove_contextual_duplicates` (bool) - Remove if contextual version exists in input

---

#### 3. Smart Context Requirement (Currently Flag-Only)
**Current:** Flags isolated vocabulary, user must add context
**Desired:** Multiple options for handling

**Options:**
1. **Flag only** (current behavior) - user adds context manually
2. **Remove isolated** - auto-remove cards with < N tokens
3. **Find context** - search input file for contextual examples and merge
4. **Require context** - fail if isolated vocab found (strict mode)

**Implementation:**
```python
def cmd_process_cards(args):
    if args.context_mode == 'remove':
        # Remove cards below token threshold
        candidates = [c for c in candidates if token_count(c) >= args.min_context_tokens]
    elif args.context_mode == 'merge':
        # Find contextual examples and merge isolated vocab
        candidates = merge_isolated_with_context(candidates)
    elif args.context_mode == 'strict':
        # Fail if any isolated vocab found
        isolated = [c for c in candidates if token_count(c) < args.min_context_tokens]
        if isolated:
            raise ValueError(f"Found {len(isolated)} isolated vocab cards (strict mode)")
```

---

#### 4. In-Place Tag Cleaning (Currently Two-Step)
**Current:** `convert-tags` creates new file, then user manually applies to input
**Desired:** Tags cleaned automatically during processing

**Implementation:**
Already working - just make it the default behavior in `process-cards` command.

---

#### 5. Lemma Duplicate Handling (Currently Review-Only)
**Current:** 76 lemma duplicates flagged for manual review
**Desired:** Smart handling based on user intent

**Options:**
1. **Keep all** - User learning different forms separately (current)
2. **Consolidate** - Merge different forms into single card with multiple examples
3. **Flag for review** - Keep but mark for manual decision

**Implementation:**
```python
def cmd_process_cards(args):
    if args.lemma_duplicate_mode == 'consolidate':
        # Merge cards with same lemma but different forms
        candidates = consolidate_lemma_duplicates(candidates, results)
    elif args.lemma_duplicate_mode == 'flag':
        # Add warning tag to cards with lemma duplicates
        candidates = flag_lemma_duplicates(candidates, results)
```

---

### Proposed CLI Interface

```python
parser.add_argument('--auto-apply-cloze', action='store_true',
    help='Automatically apply high-confidence cloze conversions')
parser.add_argument('--cloze-confidence-threshold', type=float, default=0.75,
    help='Minimum confidence to auto-apply cloze (default: 0.75)')

parser.add_argument('--remove-exact-duplicates', action='store_true',
    help='Automatically remove exact self-duplicates (keeps first occurrence)')
parser.add_argument('--remove-deck-duplicates', action='store_true',
    help='Remove isolated vocabulary already covered in deck')
parser.add_argument('--remove-contextual-duplicates', action='store_true',
    help='Remove isolated vocab if contextual example exists in input')

parser.add_argument('--context-mode', choices=['flag', 'remove', 'merge', 'strict'],
    default='flag', help='How to handle isolated vocabulary')
parser.add_argument('--min-context-tokens', type=int, default=2,
    help='Minimum tokens required for context (default: 2)')

parser.add_argument('--lemma-duplicate-mode', choices=['keep', 'consolidate', 'flag'],
    default='keep', help='How to handle lemma duplicates')
```

---

### Example: Fully Automated Pipeline

```bash
# Process raw LLM cards with aggressive automation
python -m anki_hoplite.cli process-cards \
  --input llm-generated-cards.csv \
  --deck-export resources/Unified-Greek.txt \
  --out ready-for-import.csv \
  --auto-apply-cloze \
  --cloze-confidence-threshold 0.75 \
  --remove-exact-duplicates \
  --remove-deck-duplicates \
  --remove-contextual-duplicates \
  --context-mode remove \
  --min-context-tokens 2 \
  --lemma-duplicate-mode flag \
  --enforce-tags \
  --auto-tag

# Output:
# ✓ Removed 2 exact duplicates
# ✓ Removed 7 cards already in deck
# ✓ Removed 3 isolated cards with contextual examples
# ✓ Removed 5 cards below context threshold
# ✓ Applied 13 cloze conversions (confidence ≥0.75)
# ✓ Cleaned tags: 0 unknown, 263 allowlist tags
# ✓ Flagged 76 lemma duplicates for review
#
# Final: 86 cards ready for import (was 118)
# Wrote: ready-for-import.csv
```

---

## Configuration File for User Preferences

Instead of long CLI flags, allow user to define preferences in `resources/processing_config.json`:

```json
{
  "cloze": {
    "auto_apply": true,
    "confidence_threshold": 0.75,
    "prefer_target_word": true
  },
  "duplicates": {
    "remove_exact": true,
    "remove_deck_duplicates": true,
    "remove_contextual_duplicates": true,
    "lemma_mode": "flag"
  },
  "context": {
    "mode": "remove",
    "min_tokens": 2,
    "require_sentence_markers": false
  },
  "tags": {
    "auto_convert": true,
    "enforce_allowlist": true,
    "auto_tag": true
  }
}
```

Then simple command:
```bash
python -m anki_hoplite.cli process-cards \
  --input raw-cards.csv \
  --out polished-cards.csv \
  --config resources/processing_config.json
```

---

## Lessons Learned

### What Worked Well

1. **Modular implementation** - Each phase (tag conversion, self-duplicates, context, cloze) is independent
2. **Clear feedback** - Summary statistics show exactly what was found/changed
3. **Conservative defaults** - Features are opt-in, don't auto-apply without user consent
4. **Comprehensive output** - 30-column CSV provides full audit trail

### What Needs Improvement

1. **Too many manual steps** - User had to request cloze application, redundancy removal, tag cleanup
2. **Two-file workflow** - Cleaned tags went to output file, not input file
3. **No auto-removal** - System identifies issues but doesn't fix them automatically
4. **Lemma duplicates unclear** - 76 flagged but no guidance on what to do with them
5. **Context handling basic** - Just flags isolated cards, doesn't suggest context from existing examples

### User Experience Issues

1. **Initial noise problem** - 220 unknown tags made output unusable until fixed
2. **Unclear what to review** - With 115 rows, user didn't know where to start
3. **Manual redundancy check** - User had to ask about specific cards (καλεῖ)
4. **Explicit requests needed** - "Apply cloze", "remove redundant", "clean tags in input file"

---

## Metrics from This Session

**Input:** 118 cards (Athenaze Ch3)

**Output:** 103 cards ready for import

**Removed:**
- 2 exact duplicates (manual by user)
- 10 redundant isolated vocabulary (7 in deck, 3 with context)
- 3 empty rows

**Applied:**
- 13 cloze conversions (high confidence)
- 263 tag normalizations (all cards)

**Flagged for Review:**
- 13 isolated vocabulary (truly new, no context available)
- 76 lemma duplicates (different forms of same word)

**Processing Time:**
- Tag conversion: ~1 second
- Full lint (all features): ~5 seconds
- Total workflow: Multiple iterations over ~2 hours (due to manual steps)

**Ideal Automated Time:** <10 seconds for entire pipeline

---

## Next Steps for Full Automation

### Priority 1: Auto-Apply Features (High Impact)
- [ ] Auto-apply high-confidence cloze conversions
- [ ] Auto-remove exact duplicates (keep first occurrence)
- [ ] Auto-remove redundant isolated vocabulary
- [ ] In-place tag cleaning (default behavior)

### Priority 2: Smart Defaults (Medium Impact)
- [ ] Configuration file for user preferences
- [ ] Sensible defaults (e.g., remove exact duplicates = yes)
- [ ] `process-cards` command that combines all steps

### Priority 3: Enhanced Intelligence (Lower Impact)
- [ ] Context finder (search input for examples of isolated vocab)
- [ ] Lemma duplicate consolidation
- [ ] Multi-word cloze suggestions
- [ ] Tag inference from context (auto-tag improvements)

### Priority 4: User Experience (Nice to Have)
- [ ] Preview mode (show what would be changed without applying)
- [ ] Interactive mode (ask for confirmation on each change)
- [ ] Detailed changelog report (what was changed and why)
- [ ] Rollback capability (undo processing)

---

## Conclusion

This session successfully implemented a comprehensive flashcard enhancement system that reduced 118 raw cards to 103 polished cards ready for import. However, the workflow required multiple iterations and manual steps.

**Key Insight:** The tools are powerful but need better defaults and automation to achieve the "raw in, polished out" pipeline goal.

**Recommended Next Implementation:** Create a `process-cards` command that combines all phases with smart defaults and minimal user intervention, controlled by a configuration file for user preferences.
