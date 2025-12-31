"""Cloze context validation for Ancient Greek Anki cards.

Analyzes cloze cards to identify weak/ambiguous cloze deletions based on:
- Context token count (words outside deletions)
- Deletion density ratio (% of tokens removed)
- Content word density (content vs stop words)
- Multi-factor quality scoring (excellent/good/weak/poor)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Optional

from .normalize import normalize_text_nfc


@dataclass
class ClozeSegment:
    """A single cloze deletion segment.

    Attributes:
        number: Cloze deletion number (1, 2, 3...)
        content: Text inside the deletion (before :: hint)
        hint: Optional hint text (after ::)
        full_match: Full matched string including {{c...::...}}
    """
    number: int
    content: str
    hint: str
    full_match: str


@dataclass
class ClozeParseResult:
    """Result of parsing cloze syntax from a field.

    Attributes:
        is_cloze: Whether any cloze deletions were found
        segments: List of parsed cloze deletions (ordered by appearance)
        context_text: All text outside cloze deletions (original form)
        full_text: Original field text
    """
    is_cloze: bool
    segments: List[ClozeSegment]
    context_text: str
    full_text: str


@dataclass
class ClozeAnalysis:
    """Complete validation analysis for a cloze card.

    Attributes:
        is_cloze: Whether card contains cloze deletions
        total_tokens: Total Greek tokens in field
        context_tokens: Greek tokens outside deletions
        cloze_tokens: Greek tokens inside deletions
        deletion_ratio: Fraction of tokens in deletions (0.0-1.0)
        context_stop_words: Number of stop words in context
        context_content_words: Number of content words in context
        content_word_density: Ratio of content to total words (0.0-1.0)
        quality_level: "excellent" | "good" | "weak" | "poor" | "n/a"
        quality_reasons: List of reason strings (e.g., "low_context_tokens")
        parse_result: Parsed structure (internal)
    """
    is_cloze: bool
    total_tokens: int
    context_tokens: int
    cloze_tokens: int
    deletion_ratio: float
    context_stop_words: int
    context_content_words: int
    content_word_density: float
    quality_level: str
    quality_reasons: List[str]
    parse_result: ClozeParseResult


@dataclass
class GreekStopWords:
    """Greek stop word list manager.

    Attributes:
        words: Set of normalized stop words (lowercase, no accents)
    """
    words: Set[str]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "GreekStopWords":
        """Load stop words from file or use defaults.

        Args:
            path: Path to stop words file (one word per line). If None, uses default path.

        Returns:
            GreekStopWords instance

        Raises:
            FileNotFoundError: If specified file doesn't exist
        """
        if path is None:
            path = Path("resources/greek_stopwords.txt")
        else:
            path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Stop words file not found: {path}")

        words = set()
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith("#"):
                    words.add(line.lower())

        return cls(words=words)

    def is_stop_word(self, token: str) -> bool:
        """Check if normalized token is a stop word.

        Args:
            token: Token to check (should be normalized: lowercase, no accents)

        Returns:
            True if token is a stop word
        """
        return token.lower() in self.words


# Regex pattern for Anki cloze syntax: {{c1::word}} or {{c1::word::hint}}
_CLOZE_PATTERN = re.compile(r'\{\{c(\d+)::([^:}]+?)(?:::([^}]+?))?\}\}')

# HTML tag pattern
_HTML_PATTERN = re.compile(r'<[^>]+>')

# Sound tag pattern: [sound:filename.mp3]
_SOUND_PATTERN = re.compile(r'\[sound:[^\]]+\]')


def strip_html_tags(text: str) -> str:
    """Remove HTML tags but preserve text content.

    Args:
        text: Text potentially containing HTML tags

    Returns:
        Text with HTML tags removed
    """
    return _HTML_PATTERN.sub('', text)


def strip_sound_tags(text: str) -> str:
    """Remove Anki sound tags: [sound:filename.mp3].

    Args:
        text: Text potentially containing sound tags

    Returns:
        Text with sound tags removed
    """
    return _SOUND_PATTERN.sub('', text)


def is_pure_punctuation(token: str) -> bool:
    """Check if token contains only punctuation.

    Args:
        token: Token to check

    Returns:
        True if token is all punctuation
    """
    if not token:
        return True
    return all(unicodedata.category(c).startswith('P') for c in token)


def parse_cloze_syntax(text: str) -> ClozeParseResult:
    """Parse Anki cloze syntax from text field.

    Handles:
    - Standard deletions: {{c1::word}}
    - Deletions with hints: {{c1::word::hint text}}
    - Multiple deletions: {{c1::...}} ... {{c2::...}}
    - Nested HTML/sound tags (removed before analysis)

    Args:
        text: Raw field text (may contain HTML, sound tags, cloze syntax)

    Returns:
        ClozeParseResult with parsed segments and extracted context
    """
    if not text:
        return ClozeParseResult(is_cloze=False, segments=[], context_text="", full_text=text)

    # Strip HTML and sound tags first
    cleaned_text = strip_sound_tags(strip_html_tags(text))

    # Find all cloze deletions
    segments = []
    for match in _CLOZE_PATTERN.finditer(cleaned_text):
        number = int(match.group(1))
        content = match.group(2).strip()
        hint = match.group(3).strip() if match.group(3) else ""
        full_match = match.group(0)

        segments.append(ClozeSegment(
            number=number,
            content=content,
            hint=hint,
            full_match=full_match
        ))

    # Extract context (text outside cloze deletions)
    context_text = _CLOZE_PATTERN.sub('', cleaned_text)

    is_cloze = len(segments) > 0

    return ClozeParseResult(
        is_cloze=is_cloze,
        segments=segments,
        context_text=context_text,
        full_text=text
    )


def tokenize_greek(text: str) -> List[str]:
    """Tokenize Greek text into words.

    Steps:
    1. Apply NFC normalization
    2. Strip HTML tags (preserve text inside)
    3. Strip sound tags: [sound:...]
    4. Split on whitespace
    5. Filter pure punctuation tokens

    Args:
        text: Greek text to tokenize

    Returns:
        List of Greek word tokens
    """
    if not text:
        return []

    # Normalize and clean
    t = normalize_text_nfc(text)
    t = strip_sound_tags(strip_html_tags(t))

    # Split on whitespace
    tokens = t.split()

    # Filter pure punctuation
    tokens = [tok for tok in tokens if not is_pure_punctuation(tok)]

    return tokens


def count_stop_words(tokens: List[str], stopwords: GreekStopWords) -> tuple[int, int]:
    """Count stop words vs content words in token list.

    Note: Tokens should already be normalized for matching (lowercase, no accents).
    This function applies normalization to handle various input forms.

    Args:
        tokens: List of Greek tokens
        stopwords: Stop word set

    Returns:
        (stop_word_count, content_word_count)
    """
    from .normalize import normalize_greek_for_match

    stop_count = 0
    content_count = 0

    for token in tokens:
        # Normalize token for stop word matching (lowercase, no accents)
        normalized = normalize_greek_for_match(token)

        if stopwords.is_stop_word(normalized):
            stop_count += 1
        else:
            content_count += 1

    return (stop_count, content_count)


def classify_quality(
    context_tokens: int,
    deletion_ratio: float,
    content_density: float
) -> tuple[str, List[str]]:
    """Classify cloze quality based on metrics.

    Multi-factor scoring logic:
    - excellent: context ≥5 tokens AND deletion ≤50% AND content density ≥0.40
    - good: context ≥3 tokens AND deletion ≤60% AND content density ≥0.30
    - weak: context ≥2 tokens OR (context ≥1 AND deletion ≤80%)
    - poor: all others (0-1 tokens, or >80% deletion)

    Args:
        context_tokens: Number of tokens outside deletions
        deletion_ratio: Fraction of tokens in deletions (0.0-1.0)
        content_density: Ratio of content words to total (0.0-1.0)

    Returns:
        (quality_level, reasons) where:
        - quality_level: "excellent" | "good" | "weak" | "poor"
        - reasons: List of reason codes (e.g., ["low_context", "high_deletion"])
    """
    reasons = []

    # Check for excellent quality
    if context_tokens >= 5 and deletion_ratio <= 0.50 and content_density >= 0.40:
        return ("excellent", [])

    # Check for good quality
    if context_tokens >= 3 and deletion_ratio <= 0.60 and content_density >= 0.30:
        return ("good", [])

    # Check for weak quality
    if context_tokens >= 2 or (context_tokens >= 1 and deletion_ratio <= 0.80):
        # Identify reasons for weakness
        if context_tokens < 3:
            reasons.append("low_context")
        if deletion_ratio > 0.50:
            reasons.append("high_deletion")
        if content_density < 0.30:
            reasons.append("low_content_density")
        return ("weak", reasons)

    # Poor quality
    if context_tokens == 0:
        reasons.append("no_context")
    elif context_tokens == 1:
        reasons.append("minimal_context")
    if deletion_ratio > 0.80:
        reasons.append("very_high_deletion")
    if content_density == 0.0 and context_tokens > 0:
        reasons.append("all_stop_words")

    return ("poor", reasons)


def analyze_cloze_card(
    front: str,
    stopwords: GreekStopWords
) -> ClozeAnalysis:
    """Analyze a single card's cloze quality.

    Main entry point for cloze validation. Coordinates parsing, tokenization,
    metric calculation, and quality classification.

    Args:
        front: Front field text (may contain cloze syntax)
        stopwords: Loaded stop word set

    Returns:
        Complete ClozeAnalysis with all metrics and quality classification
    """
    # 1. Parse cloze syntax
    parse_result = parse_cloze_syntax(front)

    if not parse_result.is_cloze:
        # Not a cloze card - return N/A analysis
        return ClozeAnalysis(
            is_cloze=False,
            total_tokens=0,
            context_tokens=0,
            cloze_tokens=0,
            deletion_ratio=0.0,
            context_stop_words=0,
            context_content_words=0,
            content_word_density=0.0,
            quality_level="n/a",
            quality_reasons=[],
            parse_result=parse_result
        )

    # 2. Tokenize context and cloze segments
    context_token_list = tokenize_greek(parse_result.context_text)

    cloze_token_list = []
    for segment in parse_result.segments:
        cloze_token_list.extend(tokenize_greek(segment.content))

    context_tokens = len(context_token_list)
    cloze_tokens = len(cloze_token_list)
    total_tokens = context_tokens + cloze_tokens

    # 3. Calculate deletion ratio
    deletion_ratio = cloze_tokens / total_tokens if total_tokens > 0 else 0.0

    # 4. Count stop words in context
    stop_count, content_count = count_stop_words(context_token_list, stopwords)

    # 5. Calculate content word density
    content_word_density = content_count / (stop_count + content_count) if (stop_count + content_count) > 0 else 0.0

    # 6. Classify quality
    quality_level, quality_reasons = classify_quality(context_tokens, deletion_ratio, content_word_density)

    return ClozeAnalysis(
        is_cloze=True,
        total_tokens=total_tokens,
        context_tokens=context_tokens,
        cloze_tokens=cloze_tokens,
        deletion_ratio=deletion_ratio,
        context_stop_words=stop_count,
        context_content_words=content_count,
        content_word_density=content_word_density,
        quality_level=quality_level,
        quality_reasons=quality_reasons,
        parse_result=parse_result
    )
