"""Duplicate detection logic for candidates against a deck index.

Levels (per spec):
- High: exact Greek string duplicate
- Medium: same lemma, different inflection
- Low: same English definition (gloss) on a different Greek word
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .normalize import normalize_greek_for_match
from .lemmatize import GreekLemmatizer
from .deck_index import DeckIndex


@dataclass
class DetectionResult:
    note_id: str  # The current card's ID (for deck linting; empty for candidate analysis)
    front: str
    back: str
    tags: str
    normalized_greek: str
    lemma: str
    warning_level: str
    match_reason: str
    matched_note_ids: str  # comma-separated


def analyze_candidates(
    candidates: List[dict], deck: DeckIndex, lemmatizer: GreekLemmatizer
) -> List[DetectionResult]:
    results: List[DetectionResult] = []
    for row in candidates:
        front = row.get("front", "")
        back = row.get("back", "")
        tags = row.get("tags", "")
        g_norm = normalize_greek_for_match(front)
        lemma = normalize_greek_for_match(lemmatizer.best_lemma(front)) if front else ""

        level = "none"
        reason = "no-match"
        match_ids: List[str] = []

        # High: exact Greek string
        ids_high = list(deck.exact_greek.get(g_norm, [])) if g_norm else []
        if ids_high:
            level = "high"
            reason = "exact-greek-match"
            match_ids = ids_high
        else:
            # Medium: lemma
            ids_med = list(deck.lemma_index.get(lemma, [])) if lemma else []
            if ids_med:
                level = "medium"
                reason = "lemma-match"
                match_ids = ids_med
            else:
                # Low: English gloss
                e_norm = (back or "").strip().lower()
                ids_low = list(deck.english_index.get(e_norm, [])) if e_norm else []
                if ids_low:
                    level = "low"
                    reason = "english-gloss-match"
                    match_ids = ids_low

        results.append(
            DetectionResult(
                note_id="",  # Candidates don't have IDs yet
                front=front,
                back=back,
                tags=tags,
                normalized_greek=g_norm,
                lemma=lemma,
                warning_level=level,
                match_reason=reason,
                matched_note_ids=",".join(match_ids),
            )
        )
    return results


def analyze_deck_internal(deck: DeckIndex, lemmatizer: GreekLemmatizer) -> List[DetectionResult]:
    """Analyze the deck for internal duplicates (cards that duplicate other cards in the same deck).

    This checks each card in the deck against the deck's indexes to find duplicates.
    Unlike analyze_candidates(), this excludes the card itself from matches.

    Args:
        deck: The DeckIndex to analyze
        lemmatizer: Lemmatizer for extracting lemmas

    Returns:
        List of DetectionResults for cards that have duplicates, excluding "none" results
    """
    results: List[DetectionResult] = []

    for note in deck.notes:
        g_norm = normalize_greek_for_match(note.greek_text)
        lemma = normalize_greek_for_match(lemmatizer.best_lemma(note.greek_text)) if note.greek_text else ""

        level = "none"
        reason = "no-match"
        match_ids: List[str] = []

        # High: exact Greek string (excluding self)
        ids_high = list(deck.exact_greek.get(g_norm, [])) if g_norm else []
        ids_high = [id for id in ids_high if id != note.note_id]
        if ids_high:
            level = "high"
            reason = "exact-greek-match"
            match_ids = ids_high
        else:
            # Medium: lemma (excluding self)
            ids_med = list(deck.lemma_index.get(lemma, [])) if lemma else []
            ids_med = [id for id in ids_med if id != note.note_id]
            if ids_med:
                level = "medium"
                reason = "lemma-match"
                match_ids = ids_med
            else:
                # Low: English gloss (excluding self)
                e_norm = (note.english_text or "").strip().lower()
                ids_low = list(deck.english_index.get(e_norm, [])) if e_norm else []
                ids_low = [id for id in ids_low if id != note.note_id]
                if ids_low:
                    level = "low"
                    reason = "english-gloss-match"
                    match_ids = ids_low

        # Only include results with duplicates found
        if level != "none":
            results.append(
                DetectionResult(
                    note_id=note.note_id,
                    front=note.greek_text,
                    back=note.english_text,
                    tags="",  # Tags not stored in NoteEntry
                    normalized_greek=g_norm,
                    lemma=lemma,
                    warning_level=level,
                    match_reason=reason,
                    matched_note_ids=",".join(match_ids),
                )
            )

    return results

