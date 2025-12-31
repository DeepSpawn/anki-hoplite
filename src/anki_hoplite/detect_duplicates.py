"""Duplicate detection logic for candidates against a deck index.

Levels (per spec):
- High: exact Greek string duplicate
- Medium: same lemma, different inflection
- Low: same English definition (gloss) on a different Greek word
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .normalize import normalize_greek_for_match
from .lemmatize import GreekLemmatizer
from .deck_index import DeckIndex
from .tag_hygiene import TagSchema, analyze_card_tags, format_tags


@dataclass
class DetectionResult:
    note_id: str  # The current card's ID (for deck linting; empty for candidate analysis)
    front: str
    back: str
    tags: str  # ORIGINAL tags (preserved)
    normalized_greek: str
    lemma: str
    warning_level: str
    match_reason: str
    matched_note_ids: str  # comma-separated
    # Tag hygiene fields (Feature B)
    tags_kept: str = ""  # Space-separated kept tags
    tags_deleted: str = ""  # Space-separated blocked tags (deleted)
    tags_unknown: str = ""  # Space-separated unknown tags (need review)
    tags_auto_added: str = ""  # Space-separated auto-added tags
    tags_final: str = ""  # Final tag string (kept + auto-added)
    tags_need_review: bool = False  # Flag for unknown tags
    # Cloze validation fields (Feature C)
    cloze_quality: str = ""  # "excellent" | "good" | "weak" | "poor" | "" (if not cloze)
    cloze_context_tokens: int = 0  # Number of context tokens
    cloze_deletion_ratio: float = 0.0  # Deletion percentage (0.0-1.0)
    cloze_content_density: float = 0.0  # Content word density (0.0-1.0)
    cloze_reasons: str = ""  # Space-separated reason codes
    # Self-duplicate detection fields
    self_duplicate_level: str = "none"  # high/medium/low/none (duplicates within candidates)
    self_duplicate_reason: str = ""  # Match type for self-duplicates
    self_duplicate_ids: str = ""  # CSV row numbers of matching candidates (1-based)
    # Context analysis fields
    context_level: str = ""  # "rich_context" | "minimal_context" | "isolated" | "phrase_fragment"
    context_tokens: int = 0  # Number of Greek tokens
    context_recommendation: str = ""  # "good" | "consider_enhancing" | "needs_context"
    # Cloze recommendation fields
    cloze_recommended: bool = False  # Whether to recommend cloze conversion
    cloze_type: str = ""  # "target_word" | "morphology" | "context_word" | "none"
    cloze_suggestion: str = ""  # Suggested word(s) to cloze
    cloze_confidence: float = 0.0  # Confidence score (0.0-1.0)


def analyze_candidates(
    candidates: List[dict],
    deck: DeckIndex,
    lemmatizer: GreekLemmatizer,
    tag_schema: Optional[TagSchema] = None,
    enable_auto_tag: bool = False,
    enable_cloze_validation: bool = False,
    cloze_stopwords: Optional["GreekStopWords"] = None,
    enable_context_analysis: bool = False,
    enable_cloze_recommendations: bool = False
) -> List[DetectionResult]:
    """Analyze candidate cards for duplicates, tag hygiene, cloze quality, and context.

    Args:
        candidates: List of candidate card dictionaries
        deck: Deck index to check against
        lemmatizer: Lemmatizer for extracting lemmas
        tag_schema: Optional tag schema for tag hygiene enforcement
        enable_auto_tag: Whether to apply auto-tagging (requires tag_schema)
        enable_cloze_validation: Whether to validate cloze context quality
        cloze_stopwords: Stop words for cloze analysis (required if enable_cloze_validation)
        enable_context_analysis: Whether to analyze contextual richness
        enable_cloze_recommendations: Whether to recommend cloze conversion candidates

    Returns:
        List of DetectionResults with duplicate, tag, cloze, context, and recommendation analysis
    """
    # Run self-duplicate detection first
    self_dups = analyze_candidates_self_duplicates(candidates, lemmatizer)

    results: List[DetectionResult] = []
    for idx, row in enumerate(candidates):
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

        # Tag hygiene analysis (if schema provided)
        if tag_schema is not None:
            tag_result = analyze_card_tags(front, back, tags, tag_schema, enable_auto_tag)
            tags_kept = format_tags(tag_result.kept_tags)
            tags_deleted = format_tags(tag_result.deleted_tags)
            tags_unknown = format_tags(tag_result.unknown_tags)
            tags_auto_added = format_tags(tag_result.auto_added_tags)
            tags_final = format_tags(tag_result.final_tags)
            tags_need_review = tag_result.needs_review
        else:
            # No tag hygiene - set default values
            tags_kept = ""
            tags_deleted = ""
            tags_unknown = ""
            tags_auto_added = ""
            tags_final = ""
            tags_need_review = False

        # Cloze validation (if enabled)
        if enable_cloze_validation and cloze_stopwords is not None:
            from .cloze_validator import analyze_cloze_card
            cloze_analysis = analyze_cloze_card(front, cloze_stopwords)

            if cloze_analysis.is_cloze:
                cloze_quality = cloze_analysis.quality_level
                cloze_context_tokens = cloze_analysis.context_tokens
                cloze_deletion_ratio = cloze_analysis.deletion_ratio
                cloze_content_density = cloze_analysis.content_word_density
                cloze_reasons = " ".join(cloze_analysis.quality_reasons)
            else:
                # Not a cloze card - set empty values
                cloze_quality = ""
                cloze_context_tokens = 0
                cloze_deletion_ratio = 0.0
                cloze_content_density = 0.0
                cloze_reasons = ""
        else:
            # Cloze validation disabled - set default values
            cloze_quality = ""
            cloze_context_tokens = 0
            cloze_deletion_ratio = 0.0
            cloze_content_density = 0.0
            cloze_reasons = ""

        # Context analysis (if enabled)
        if enable_context_analysis:
            from .context_analyzer import classify_context
            ctx_analysis = classify_context(front)
            context_level = ctx_analysis.context_level
            context_tokens = ctx_analysis.token_count
            context_recommendation = ctx_analysis.context_recommendation
        else:
            # Context analysis disabled - set default values
            context_level = ""
            context_tokens = 0
            context_recommendation = ""

        # Cloze recommendations (if enabled)
        if enable_cloze_recommendations:
            from .cloze_recommender import recommend_cloze_conversion
            cloze_rec = recommend_cloze_conversion(front, back, tags, level)
            cloze_recommended = cloze_rec.should_cloze
            cloze_type = cloze_rec.cloze_type
            cloze_suggestion = cloze_rec.suggested_deletion
            cloze_confidence = cloze_rec.confidence
        else:
            # Cloze recommendations disabled - set default values
            cloze_recommended = False
            cloze_type = ""
            cloze_suggestion = ""
            cloze_confidence = 0.0

        # Extract self-duplicate info
        if idx in self_dups:
            self_level, self_reason, self_match_rows = self_dups[idx]
            self_duplicate_level = self_level
            self_duplicate_reason = self_reason
            self_duplicate_ids = ",".join(str(r) for r in self_match_rows)
        else:
            self_duplicate_level = "none"
            self_duplicate_reason = ""
            self_duplicate_ids = ""

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
                tags_kept=tags_kept,
                tags_deleted=tags_deleted,
                tags_unknown=tags_unknown,
                tags_auto_added=tags_auto_added,
                tags_final=tags_final,
                tags_need_review=tags_need_review,
                cloze_quality=cloze_quality,
                cloze_context_tokens=cloze_context_tokens,
                cloze_deletion_ratio=cloze_deletion_ratio,
                cloze_content_density=cloze_content_density,
                cloze_reasons=cloze_reasons,
                self_duplicate_level=self_duplicate_level,
                self_duplicate_reason=self_duplicate_reason,
                self_duplicate_ids=self_duplicate_ids,
                context_level=context_level,
                context_tokens=context_tokens,
                context_recommendation=context_recommendation,
                cloze_recommended=cloze_recommended,
                cloze_type=cloze_type,
                cloze_suggestion=cloze_suggestion,
                cloze_confidence=cloze_confidence,
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


def analyze_candidates_self_duplicates(
    candidates: List[dict],
    lemmatizer: GreekLemmatizer
) -> Dict[int, tuple]:
    """Analyze candidates for duplicates within the candidate set itself.

    Args:
        candidates: List of candidate card dictionaries
        lemmatizer: Lemmatizer for extracting lemmas

    Returns:
        Dictionary mapping candidate index to (level, reason, match_indices) tuple
    """
    from collections import defaultdict

    # Build temporary indexes from candidates
    exact_index: Dict[str, List[int]] = defaultdict(list)
    lemma_index: Dict[str, List[int]] = defaultdict(list)
    english_index: Dict[str, List[int]] = defaultdict(list)

    for idx, row in enumerate(candidates):
        front = row.get("front", "")
        back = row.get("back", "")

        # Index normalized Greek
        g_norm = normalize_greek_for_match(front)
        if g_norm:
            exact_index[g_norm].append(idx)

        # Index lemma
        lemma = normalize_greek_for_match(lemmatizer.best_lemma(front)) if front else ""
        if lemma:
            lemma_index[lemma].append(idx)

        # Index English (normalized)
        e_norm = (back or "").strip().lower()
        if e_norm:
            english_index[e_norm].append(idx)

    # Check each candidate against indexes (excluding self)
    self_duplicate_results: Dict[int, tuple] = {}

    for idx, row in enumerate(candidates):
        front = row.get("front", "")
        back = row.get("back", "")
        g_norm = normalize_greek_for_match(front)
        lemma = normalize_greek_for_match(lemmatizer.best_lemma(front)) if front else ""

        level = "none"
        reason = ""
        match_indices: List[int] = []

        # High: exact Greek string (excluding self)
        ids_high = [i for i in exact_index.get(g_norm, []) if i != idx] if g_norm else []
        if ids_high:
            level = "high"
            reason = "exact-greek-match"
            match_indices = ids_high
        else:
            # Medium: lemma (excluding self)
            ids_med = [i for i in lemma_index.get(lemma, []) if i != idx] if lemma else []
            if ids_med:
                level = "medium"
                reason = "lemma-match"
                match_indices = ids_med
            else:
                # Low: English gloss (excluding self)
                e_norm = (back or "").strip().lower()
                ids_low = [i for i in english_index.get(e_norm, []) if i != idx] if e_norm else []
                if ids_low:
                    level = "low"
                    reason = "english-gloss-match"
                    match_indices = ids_low

        if level != "none":
            # Store 1-based row numbers (CSV row = index + 2, accounting for header)
            row_numbers = [i + 2 for i in match_indices]
            self_duplicate_results[idx] = (level, reason, row_numbers)

    return self_duplicate_results

