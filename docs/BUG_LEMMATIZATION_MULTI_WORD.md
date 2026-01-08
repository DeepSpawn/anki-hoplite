# Bug Report: Lemmatization Fails for Multi-Word Greek Phrases

**Date**: 2026-01-03
**Severity**: High
**Component**: `anki_hoplite/lemmatize.py`
**Status**: Open

## Summary

The `best_lemma()` function in `lemmatize.py` incorrectly lemmatizes multi-word Greek phrases by returning the lemma of the first token instead of identifying the substantive (main word). This primarily affects recognition cards with articles and causes unreliable duplicate detection.

## Impact

- **Duplicate detection degraded**: Medium-level (lemma) matches fail for cards with articles, forcing reliance on low-level (English) matches
- **Self-duplicate detection unreliable**: Recognition cards with different articles but same noun are not grouped by lemma
- **Affects ~50% of typical vocabulary cards**: Most Greek nouns are learned with articles

## Reproduction

### Input Data
Cards from `resources/input-cards.csv` (2026-01-03 import):

```csv
front,back,tags
ἡ κρήνη,Nom Sg — the spring,grc noun 1stdecl type1 lemma_krene recog nom_sg
τῆς κρήνης,Gen Sg — of the spring,grc noun 1stdecl type1 lemma_krene recog gen_sg
τῇ κρήνῃ,Dat Sg — to or for the spring,grc noun 1stdecl type1 lemma_krene recog dat_sg
ἡ μέλιττα,Nom Sg — the bee,grc noun 1stdecl type3 lemma_melitta recog nom_sg
```

### Actual Behavior

```
ἡ κρήνη      → normalized: "η κρηνη"   → lemma: "η"      (WRONG: article)
τῆς κρήνης   → normalized: "τησ κρηνησ" → lemma: "τησ"    (WRONG: article)
τῇ κρήνῃ     → normalized: "τη κρηνη"   → lemma: "ο"      (WRONG: article, wrong token)
ἡ μέλιττα    → normalized: "η μελιττα"  → lemma: "η"      (WRONG: article)
```

### Expected Behavior

```
ἡ κρήνη      → lemma: "κρηνη"    (noun lemma)
τῆς κρήνης   → lemma: "κρηνη"    (noun lemma)
τῇ κρήνῃ     → lemma: "κρηνη"    (noun lemma)
ἡ μέλιττα    → lemma: "μελιττα"  (noun lemma)
```

## Additional Issues Discovered

### Issue 2: Incorrect Verb Lemma for μέλιττα

Production cards for μέλιττα (bee) are lemmatized to the verb μελίζω instead of the noun:

```
μέλιττα — Nom Sg → lemma: "μελιζω"  (WRONG: verb "to sing", not noun "bee")
```

**Expected**: `μελιττα` (noun lemma)

### Issue 3: Malformed Lemma for ὑδρία

Production cards for ὑδρία (water-jar) produce a hybrid form:

```
ὑδρία — Nom Sg → lemma: "υδριοσ"  (WRONG: appears to be mixing noun + masculine ending)
```

**Expected**: `υδρια` (noun lemma)

## Root Cause Analysis

### Current Implementation

`anki_hoplite/lemmatize.py:42-57` (`best_lemma` function):

```python
def best_lemma(self, text: str) -> str:
    """Extract the best lemma from potentially multi-word text."""
    normalized = normalize_greek_for_match(text)
    tokens = normalized.split()
    if not tokens:
        return normalized
    # Return lemma of first token
    return self.lemmatize_token(tokens[0])
```

**Problem**: Assumes the first token is the substantive, but in Greek with articles, the article comes first.

### Why This Fails

1. **Greek word order**: Articles precede nouns (`ἡ κρήνη` = "the spring")
2. **First-token heuristic**: Returns lemma of `ἡ` (article) instead of `κρήνη` (noun)
3. **No part-of-speech awareness**: Cannot distinguish articles from substantives
4. **No Greek-specific grammar rules**: Doesn't skip known stop words (articles, particles)

## Affected Data

From the 2026-01-03 lint run on 80 candidate cards:

- **40 recognition cards affected**: All cards with format "article + noun → translation"
- **10+ production cards affected**: Incorrect CLTK lemmatization (Issues 2 & 3)
- **Overall**: ~62% of cards (50/80) have degraded lemmatization

### Breakdown by Lemma

| Lemma | Recognition Cards | Production Cards | Total Affected |
|-------|------------------|------------------|----------------|
| κρήνη | 10 (article lemma) | 0 | 10 |
| ὑδρία | 10 (article lemma) | 10 (wrong lemma) | 20 |
| μέλιττα | 10 (article lemma) | 10 (verb lemma) | 20 |
| μάχαιρα | 10 (article lemma) | 0 | 10 |
| **Total** | **40** | **20** | **60** |

## Proposed Solutions

### Option 1: Greek Stop Word Filtering (Recommended)

Skip articles and particles when selecting best lemma:

```python
def best_lemma(self, text: str) -> str:
    """Extract the best lemma from potentially multi-word text."""
    normalized = normalize_greek_for_match(text)
    tokens = normalized.split()
    if not tokens:
        return normalized

    # Load Greek stop words (articles, particles)
    stop_words = self._load_stop_words()  # ο, η, το, και, δε, etc.

    # Find first non-stop-word token
    for token in tokens:
        if token not in stop_words:
            return self.lemmatize_token(token)

    # Fallback: all tokens are stop words
    return self.lemmatize_token(tokens[0])
```

**Pros**:
- Simple implementation
- Reuses existing stop word infrastructure (`resources/greek_stopwords.txt`)
- Handles most common cases (article + noun)

**Cons**:
- Doesn't handle all edge cases (e.g., "μέγας βασιλεύς" → should return "βασιλεύς", not "μέγας")
- Stop word list needs to be comprehensive

### Option 2: Part-of-Speech Tagging

Use CLTK's POS tagger to identify the substantive:

```python
def best_lemma(self, text: str) -> str:
    """Extract the best lemma from potentially multi-word text."""
    normalized = normalize_greek_for_match(text)
    tokens = normalized.split()
    if not tokens:
        return normalized

    # Get POS tags from CLTK
    pos_tags = self._get_pos_tags(tokens)

    # Priority: NOUN > ADJ > VERB > other
    priority_tags = ['NOUN', 'ADJ', 'VERB']
    for tag_type in priority_tags:
        for token, pos in pos_tags:
            if pos == tag_type:
                return self.lemmatize_token(token)

    # Fallback
    return self.lemmatize_token(tokens[0])
```

**Pros**:
- Linguistically correct
- Handles complex phrases
- More robust

**Cons**:
- Requires CLTK POS tagger (additional dependency)
- Slower performance
- May introduce new failure modes if POS tagger is unreliable

### Option 3: Longest Token Heuristic (Quick Fix)

Assume the substantive is the longest token:

```python
def best_lemma(self, text: str) -> str:
    """Extract the best lemma from potentially multi-word text."""
    normalized = normalize_greek_for_match(text)
    tokens = normalized.split()
    if not tokens:
        return normalized

    # Return lemma of longest token
    longest_token = max(tokens, key=len)
    return self.lemmatize_token(longest_token)
```

**Pros**:
- Zero dependencies
- Fast
- Works for most noun + article cases

**Cons**:
- Fragile heuristic
- Fails for long particles/prepositions
- Not linguistically motivated

## Recommendation

**Implement Option 1** (stop word filtering) as an immediate fix, with Option 2 (POS tagging) as a future enhancement.

### Implementation Steps

1. Add `GreekLemmatizer._load_stop_words()` method (reuse from `cloze_validator.py`)
2. Modify `best_lemma()` to skip stop words
3. Add unit tests for multi-word phrases:
   - `"ἡ κρήνη"` → `"κρηνη"`
   - `"τοῦ ἀνθρώπου"` → `"ανθρωπος"`
   - `"ὦ φίλε"` → `"φιλος"` (vocative particle + noun)
4. Add integration test with real CLTK backend
5. Re-run lint on `input-cards.csv` to verify fix

## Testing Plan

### Unit Tests

```python
def test_best_lemma_with_article(mock_lemmatizer):
    """Test that articles are skipped in multi-word phrases."""
    # Setup: mock stop words
    mock_lemmatizer._stop_words = {'ο', 'η', 'το', 'των', 'τησ', 'τη'}

    # Mock CLTK to return identity lemmas for simplicity
    mock_lemmatizer.lemmatize_token = lambda x: x

    assert mock_lemmatizer.best_lemma("ἡ κρήνη") == "κρηνη"
    assert mock_lemmatizer.best_lemma("τῆς κρήνης") == "κρηνησ"
    assert mock_lemmatizer.best_lemma("τῇ κρήνῃ") == "κρηνη"
```

### Integration Tests

```python
def test_recognition_card_lemmatization_real_cltk():
    """Test with real CLTK backend (requires downloaded models)."""
    lemmatizer = GreekLemmatizer()

    # All should resolve to the noun lemma, not article
    assert lemmatizer.best_lemma("ἡ κρήνη") == "κρηνη"
    assert lemmatizer.best_lemma("τῆς κρήνης") == "κρηνη"
    assert lemmatizer.best_lemma("ἡ μέλιττα") == "μελισσα"  # or μελιττα depending on CLTK
```

### Regression Tests

Re-run linter on affected cards and verify:
- All recognition cards now show correct noun lemmas
- Self-duplicate detection groups all forms of same lemma
- No false positives in duplicate detection

## Workarounds (Until Fixed)

1. **Manual lemma override**: Add entries to `resources/lemma_overrides.json`:
   ```json
   {
     "η κρηνη": "κρηνη",
     "τησ κρηνησ": "κρηνη",
     "τη κρηνη": "κρηνη",
     ...
   }
   ```
   **Issue**: Requires 40+ manual entries for current batch, doesn't scale

2. **Remove articles from input**: Edit `input-cards.csv` to remove articles
   **Issue**: Changes card content, not desirable for learning full phrases

3. **Rely on English-level duplicate detection**: Accept degraded lemma matching
   **Issue**: Increases false negatives (misses legitimate duplicates)

## References

- Affected file: `anki_hoplite/lemmatize.py:42-57`
- Related: `anki_hoplite/cloze_validator.py` (stop word infrastructure)
- Test data: `resources/input-cards.csv` (2026-01-03)
- Lint results: `out/lint_results.csv`

## Related Issues

- See `docs/DUPLICATE_DETECTION_ISSUES.md` for broader duplicate detection challenges
- Greek stop word list completeness (`resources/greek_stopwords.txt`)