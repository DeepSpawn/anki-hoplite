# Duplicate Detection Issues

## Summary

The current duplicate detection system has a **high false positive rate** for MEDIUM-level warnings (lemma matches) when analyzing multi-word Greek phrases. This is particularly problematic for internal duplicate detection within candidate card batches.

**Status**: Critical for self-linting candidates; affects user trust in MEDIUM warnings

## Problem 1: First-Word-Only Lemmatization for Multi-Word Phrases

### Issue
The `GreekLemmatizer.best_lemma()` function only lemmatizes the **first token** of multi-word phrases, ignoring the semantic content of the entire phrase.

### Impact
When checking for lemma-based duplicates, cards with completely different meanings get flagged as duplicates simply because they start with the same common Greek word.

### Examples from Real Data

#### Example 1: Articles (οἱ)
All phrases starting with the article "οἱ" (the) are flagged as duplicates:

- Line 2: `οἱ δὲ βόες ἕλκουσι` → "but the oxen are dragging"
- Line 6: `οἱ βόες οὐκέτι μένουσιν` → "the oxen no longer stay"
- Line 55: `οἱ αὐτουργοὶ τοὺς φίλους μένουσι` → "the farmers wait for their friends"

**Result**: All flagged as MEDIUM duplicates with lemma `οι`
**Reality**: Completely different sentences with different verbs and meanings

#### Example 2: Negations (οὐ/οὐκέτι)
All phrases starting with "οὐ" (not) are grouped together:

- Line 17: `οὐ δυνατὸν ἐστὶν αἴρειν` → "it's not possible to lift"
- Line 18: `οὐ δυνατὸν ἐστὶν αἴρειν αὐτόν` → "it's not possible to lift it"
- Line 20: `οὐ δυνατὸν ἐστὶν φέρειν` → "it's not possible to carry"
- Line 21: `οὐ δυνατὸν ἐστὐν φέρειν αὐτόν` → "it's not possible to carry it"

**Result**: All 4 flagged as duplicates with lemma `ου`
**Reality**: Lines 17-18 differ only by pronoun (pedagogically intentional); lines 20-21 same pattern. But 17/18 vs 20/21 are genuinely different (lift vs carry).

#### Example 3: Conjunctions (ἀλλὰ)
- Line 7: `ἀλλὰ αὖθις ἕλκουσι` → "but they drag again"
- Line 15: `ἀλλὰ σπεύδετε, ὦ βόες` → "but hurry, O oxen!"

**Result**: Flagged as duplicates with lemma `αλλα`
**Reality**: Completely different sentences (drag vs hurry)

### Why This Happens

Looking at `lemmatize.py:best_lemma()`:
```python
def best_lemma(self, text: str) -> str:
    """Extract the 'best' lemma from potentially multi-word text."""
    tokens = self._tokenize(text)
    if not tokens:
        return text
    # Return lemma of first token
    return self.lemmatize_token(tokens[0])
```

The function **explicitly only lemmatizes the first token**, with the comment "Return lemma of first token". This design decision appears to assume that:
1. Most cards are single-word vocabulary items, OR
2. The first word is the most semantically important

For textbook reading passages (like Athenaze), this assumption breaks down completely.

## Problem 2: Pedagogically Intentional Variations Flagged as Duplicates

### Issue
Language learning materials intentionally create minimal pairs and progressive phrases to teach grammatical contrasts. The current system flags these as problematic duplicates.

### Examples

#### Pronoun Addition
- `οὐ δυνατὸν ἐστὶν αἴρειν` (it's not possible to lift)
- `οὐ δυνατὸν ἐστὶν αἴρειν αὐτόν` (it's not possible to lift **it**)

**Purpose**: Teaching pronoun usage
**Current behavior**: Flagged as MEDIUM duplicate
**Desired behavior**: Recognize these serve different pedagogical purposes

#### Progressive Phrase Building
- `ἕλκουσι τὸ ἄροτρον` (they drag the plow)
- `οὐκέτι ἕλκουσι τὸ ἄροτρον` (they no longer drag the plow)
- `οὐκέτι ἕλκουσι` (they no longer drag)

**Purpose**: Teaching negation and progressive sentence building
**Current behavior**: All flagged as duplicates
**Desired behavior**: Recognize incremental learning patterns

## Problem 3: Scale of False Positives

### Test Case: Athenaze Chapter 3 Cards
**Dataset**: 58 candidate cards from a single textbook chapter
**Results**:
- Total cards analyzed: 58
- Cards flagged with MEDIUM warnings: 39 (67%)
- Actual problematic duplicates: ~5-10 estimated

**False positive rate**: Approximately 75-80% of MEDIUM warnings are false positives

### User Impact
With a 75%+ false positive rate, users will:
1. Lose trust in the MEDIUM warning system
2. Stop reviewing MEDIUM warnings (alarm fatigue)
3. Miss actual duplicates buried in noise
4. Waste time manually reviewing obvious non-duplicates

## Problem 4: No Context-Aware Lemmatization

### Issue
The system doesn't consider:
- **Semantic heads**: In `τὸν λίθον αἴρουσι` (they lift the stone), the verb `αἴρουσι` is more semantically important than the article `τὸν`
- **Phrase types**: Prepositional phrases, verb phrases, full sentences need different strategies
- **Stop words**: Common particles, articles, and conjunctions shouldn't drive duplicate detection

### Example
- Line 13: `ἐκ τοῦ ἀγροῦ φέρουσιν` → lemma: `εκ` (preposition "from")
- Line 27: `ἐκ τοῦ ἀγροῦ` → lemma: `εκ` (same preposition)

**Issue**: Lemmatizing the preposition instead of recognizing one is a phrase and one is a fragment

## Recommendations

### Short-term Solutions

1. **Multi-word Lemmatization**
   - Lemmatize ALL content words, not just the first token
   - Compare sets of lemmas instead of single lemma
   - Weight lemmas by part of speech (verbs > nouns > articles)

2. **Stop Word Filtering**
   - Don't use articles, particles, or common conjunctions as primary lemmas
   - Skip to first content word for lemmatization
   - Use existing `resources/greek_stopwords.txt` for filtering

3. **Phrase-Level Similarity**
   - Calculate similarity score based on:
     - Percentage of shared lemmas
     - Shared content word count
     - Edit distance
   - Only flag as duplicate if similarity > 80%

4. **Internal vs External Duplicate Detection**
   - Different thresholds for checking candidates against deck vs checking candidates against themselves
   - More permissive for external (existing deck has more diverse content)
   - Stricter for internal (same source = more likely true duplicates)

### Long-term Solutions

1. **Semantic Similarity**
   - Use embeddings or semantic vectors for Ancient Greek
   - Compare meaning rather than form
   - Would catch actual semantic duplicates regardless of wording

2. **Configurable Sensitivity**
   - Allow users to set duplicate detection sensitivity
   - Separate settings for exact/lemma/English matching
   - Per-source configuration (Athenaze vs Homer vs Plato)

3. **Machine Learning**
   - Train classifier on user-labeled duplicate pairs
   - Learn what constitutes a pedagogically meaningful duplicate
   - Adapt to user's study patterns

## Testing Recommendations

### Test Suite Additions

1. **Multi-word phrase tests**
   ```python
   def test_multiword_phrase_lemmatization():
       """Phrases with same first word but different verbs shouldn't match"""
       phrase1 = "οἱ βόες ἕλκουσι"  # the oxen drag
       phrase2 = "οἱ βόες μένουσι"  # the oxen stay
       # Should NOT be flagged as lemma duplicates
   ```

2. **Stop word filtering tests**
   ```python
   def test_stop_word_skip():
       """Lemmatization should skip stop words"""
       phrase1 = "ἀλλὰ ἕλκουσι"  # but they drag
       phrase2 = "ἀλλὰ σπεύδουσι"  # but they hurry
       # Should extract ἕλκω vs σπεύδω, not ἀλλά
   ```

3. **Pedagogical variation tests**
   ```python
   def test_pronoun_addition():
       """Adding pronouns creates meaningful distinction"""
       base = "οὐ δυνατὸν ἐστὶν αἴρειν"
       with_pronoun = "οὐ δυνατὸν ἐστὶν αἴρειν αὐτόν"
       # Should recognize as pedagogically distinct
   ```

## Related Files

- `src/anki_hoplite/lemmatize.py` - `best_lemma()` implementation
- `src/anki_hoplite/detect_duplicates.py` - Duplicate detection logic
- `resources/greek_stopwords.txt` - Stop word list (112 words)
- `tests/test_lemmatize.py` - Current lemmatization tests

## Impact Assessment

**Severity**: High
**Frequency**: Very High (affects 67% of cards in test case)
**User Impact**: Critical (reduces trust in tool, increases manual review burden)
**Priority**: High (should be addressed before Feature D implementation)

## Conclusion

The current duplicate detection works well for:
- ✅ Single-word vocabulary cards
- ✅ Exact duplicate detection (HIGH warnings)
- ✅ English gloss matching (LOW warnings)

But fails for:
- ❌ Multi-word phrases (most reading material)
- ❌ Textbook progressive learning patterns
- ❌ Sentences and full clauses
- ❌ Any content where first word is a stop word

**Recommended Priority**: Address before expanding to other features. The false positive rate undermines the core value proposition of the tool.
