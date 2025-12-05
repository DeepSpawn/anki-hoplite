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

