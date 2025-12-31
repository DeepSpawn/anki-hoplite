"""Cloze recommendation engine for suggesting cards that would benefit from cloze deletion format.

This module analyzes flashcards to identify good candidates for cloze conversion:
- Cards with rich context (3+ tokens) that could benefit from active recall
- Cards with clear target vocabulary for cloze deletion
- Generation of suggested cloze syntax with confidence scores
"""

from dataclasses import dataclass
from typing import List, Optional
import re

from .context_analyzer import tokenize_greek, classify_context
from .normalize import normalize_text_nfc


@dataclass
class ClozeRecommendation:
    """Recommendation for converting a card to cloze deletion format."""
    should_cloze: bool  # Whether to recommend cloze conversion
    cloze_type: str  # "target_word" | "morphology" | "context_word" | "none"
    suggested_deletion: str  # The word(s) to cloze
    cloze_hint: str  # Suggested hint text
    confidence: float  # 0.0-1.0 confidence score
    reason: str  # Why this recommendation


def is_already_cloze(text: str) -> bool:
    """Check if text already contains cloze deletion syntax.

    Args:
        text: Text to check

    Returns:
        True if text contains {{c1::...}} or similar cloze syntax
    """
    return bool(re.search(r'\{\{c\d+::', text))


def identify_target_word(tokens: List[str], tags: str) -> Optional[str]:
    """Identify the most likely target vocabulary word for cloze deletion.

    Args:
        tokens: List of Greek tokens
        tags: Space-separated tags from the card

    Returns:
        Target word to cloze, or None if no clear target
    """
    if not tokens:
        return None

    # If there's only one non-article token, use that
    article_patterns = [
        r'^[οὁ]$',  # masculine nominative singular
        r'^[ηἡ]$',  # feminine nominative singular
        r'^[τὸτό]$',  # neuter nominative/accusative singular
        r'^τ[οόηἡ]ν$',  # accusative singular
        r'^το[ῦυ]$',  # genitive singular
        r'^τ[ῷω]$',  # dative singular
        r'^ο[ιί]$',  # masculine nominative plural
        r'^α[ιί]$',  # feminine nominative plural
        r'^τ[αά]$',  # neuter nominative/accusative plural
        r'^το[υύ]ς$',  # masculine accusative plural
        r'^τ[αά]ς$',  # feminine accusative plural
        r'^των$',  # genitive plural
        r'^το[ιί]ς$',  # dative plural
    ]

    non_article_tokens = []
    article_indices = []

    for idx, token in enumerate(tokens):
        is_article = any(re.match(pattern, token.lower(), re.UNICODE) for pattern in article_patterns)
        if not is_article:
            non_article_tokens.append(token)
        else:
            article_indices.append(idx)

    # If there's exactly one non-article token, that's likely the target
    if len(non_article_tokens) == 1:
        return non_article_tokens[0]

    # If there are multiple tokens, use heuristics:
    # - Last token is often the main word (e.g., "πρὸς τὸν ἀγρόν" → "ἀγρόν")
    # - Unless it's a verb, which is often first or second (e.g., "ἕλκουσι τὸ ἄροτρον" → "ἕλκουσι")

    # Check if tags indicate this is a verb-focused card
    if 'verb' in tags.lower():
        # Verb is likely early in the sentence
        for token in tokens[:2]:  # Check first two tokens
            if token.lower() not in ['οὁ', 'ηἡ', 'τὸτό', 'το', 'τον', 'την', 'τα']:
                return token

    # Default: return last non-article token
    if non_article_tokens:
        return non_article_tokens[-1]

    # Fallback: return last token overall
    return tokens[-1] if tokens else None


def recommend_cloze_conversion(
    front: str,
    back: str,
    tags: str,
    warning_level: str
) -> ClozeRecommendation:
    """Recommend whether to convert a card to cloze format.

    Args:
        front: Greek text (front of card)
        back: English translation (back of card)
        tags: Space-separated tags
        warning_level: Duplicate warning level (high/medium/low/none)

    Returns:
        ClozeRecommendation with suggestion and confidence
    """
    # Don't recommend cloze for cards that are already cloze
    if is_already_cloze(front):
        return ClozeRecommendation(
            should_cloze=False,
            cloze_type="none",
            suggested_deletion="",
            cloze_hint="",
            confidence=0.0,
            reason="already_cloze"
        )

    # Analyze context
    context = classify_context(front)
    tokens = tokenize_greek(front)

    # Poor candidates for cloze:
    # - Isolated vocabulary (1 token) - needs context first
    # - Two-word phrases (often just article+noun - better as basic card)
    if context.token_count < 3:
        return ClozeRecommendation(
            should_cloze=False,
            cloze_type="none",
            suggested_deletion="",
            cloze_hint="",
            confidence=0.0,
            reason="insufficient_context"
        )

    # Good candidates for cloze:
    # - Rich context (5+ tokens) - full sentences
    # - Minimal context (3-4 tokens) - meaningful phrases
    # - No exact duplicates (warning_level != "high")

    confidence = 0.5  # Base confidence

    # Boost confidence for rich context
    if context.context_level == "rich_context":
        confidence += 0.3
    elif context.context_level == "minimal_context":
        confidence += 0.1

    # Reduce confidence if card already exists in deck
    if warning_level == "high":
        # Exact duplicate - don't recommend cloze (would create another duplicate)
        return ClozeRecommendation(
            should_cloze=False,
            cloze_type="none",
            suggested_deletion="",
            cloze_hint="",
            confidence=0.0,
            reason="exact_duplicate"
        )
    elif warning_level == "medium":
        # Lemma match - reduce confidence (might be redundant)
        confidence -= 0.2

    # Identify target word for cloze
    target_word = identify_target_word(tokens, tags)
    if not target_word:
        return ClozeRecommendation(
            should_cloze=False,
            cloze_type="none",
            suggested_deletion="",
            cloze_hint="",
            confidence=0.0,
            reason="no_clear_target"
        )

    # Determine cloze type based on tags
    if 'verb' in tags.lower():
        cloze_type = "morphology"  # Verb form for learning conjugations
        hint = "verb form"
    elif 'noun' in tags.lower() or 'adjective' in tags.lower():
        cloze_type = "target_word"  # Main vocabulary word
        hint = "target word"
    else:
        cloze_type = "target_word"
        hint = ""

    # Generate suggested cloze syntax
    # Replace target word with cloze deletion
    suggested_front = front.replace(target_word, f"{{{{c1::{target_word}}}}}", 1)

    # Final confidence check
    if confidence < 0.3:
        should_cloze = False
    else:
        should_cloze = True

    return ClozeRecommendation(
        should_cloze=should_cloze,
        cloze_type=cloze_type,
        suggested_deletion=target_word,
        cloze_hint=hint,
        confidence=confidence,
        reason=f"context_{context.context_level}_tokens_{context.token_count}"
    )
