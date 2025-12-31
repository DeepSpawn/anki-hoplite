"""Context analysis module for identifying cards with insufficient contextual learning support.

This module classifies flashcards based on the richness of contextual information:
- Isolated vocabulary lacks sentence fragments for anchored learning
- Rich context provides multiple words for pattern recognition
- Minimal context provides some surrounding words but may be insufficient
"""

from dataclasses import dataclass
from typing import List
import re

from .normalize import normalize_text_nfc


@dataclass
class ContextAnalysis:
    """Result of context quality analysis for a single card."""
    context_level: str  # "rich_context" | "minimal_context" | "isolated" | "phrase_fragment"
    token_count: int  # Number of Greek words/tokens
    context_recommendation: str  # "good" | "consider_enhancing" | "needs_context"


def tokenize_greek(text: str) -> List[str]:
    """Tokenize Greek text into words.

    Args:
        text: Greek text to tokenize

    Returns:
        List of tokens (words)
    """
    # Normalize first
    normalized = normalize_text_nfc(text)

    # Remove cloze deletion syntax {{c1::...}}
    no_cloze = re.sub(r'\{\{c\d+::([^}]+)\}\}', r'\1', normalized)

    # Split on whitespace and filter empty tokens
    tokens = [t.strip() for t in no_cloze.split() if t.strip()]

    # Filter out purely punctuation tokens
    greek_tokens = []
    for token in tokens:
        # Remove punctuation from token
        clean_token = re.sub(r'[^\w\s]', '', token, flags=re.UNICODE)
        if clean_token:
            greek_tokens.append(clean_token)

    return greek_tokens


def has_sentence_markers(text: str) -> bool:
    """Check if text contains sentence-level punctuation.

    Args:
        text: Greek text to check

    Returns:
        True if text appears to be a sentence or sentence fragment
    """
    # Greek question mark: ; (semicolon)
    # Period, comma, Greek ano teleia (·), etc.
    sentence_markers = ['.', ',', ';', '·', ':', '!', '?']
    return any(marker in text for marker in sentence_markers)


def classify_context(greek_text: str) -> ContextAnalysis:
    """Classify the contextual richness of a flashcard.

    Args:
        greek_text: Front side Greek text

    Returns:
        ContextAnalysis with classification and recommendation
    """
    tokens = tokenize_greek(greek_text)
    token_count = len(tokens)
    has_punct = has_sentence_markers(greek_text)

    # Classification thresholds
    if token_count >= 5:
        # Rich context: full sentence or substantial phrase
        context_level = "rich_context"
        recommendation = "good"
    elif token_count >= 3:
        # Minimal context: short phrase
        if has_punct:
            # Likely a sentence fragment - acceptable
            context_level = "minimal_context"
            recommendation = "good"
        else:
            # Short phrase without punctuation - may need enhancement
            context_level = "phrase_fragment"
            recommendation = "consider_enhancing"
    elif token_count == 2:
        # Two words - could be article+noun, preposition+noun, etc.
        context_level = "phrase_fragment"
        recommendation = "consider_enhancing"
    elif token_count == 1:
        # Isolated word - needs context
        context_level = "isolated"
        recommendation = "needs_context"
    else:
        # Empty or no valid tokens
        context_level = "isolated"
        recommendation = "needs_context"

    return ContextAnalysis(
        context_level=context_level,
        token_count=token_count,
        context_recommendation=recommendation
    )


def analyze_candidates_context(candidates: List[dict]) -> List[ContextAnalysis]:
    """Analyze context quality for a list of candidate cards.

    Args:
        candidates: List of candidate card dictionaries

    Returns:
        List of ContextAnalysis results (one per candidate)
    """
    results = []
    for row in candidates:
        front = row.get("front", "")
        analysis = classify_context(front)
        results.append(analysis)

    return results
