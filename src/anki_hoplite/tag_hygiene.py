"""Tag hygiene enforcement for Anki cards.

Implements Feature B (spec.md): Tag & Label Hygiene
- Allowlist/blocklist enforcement
- Unknown tag flagging for manual review
- Pattern-based auto-tagging for Greek text
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set

from .normalize import normalize_greek_for_match


@dataclass
class AutoTagRule:
    """Auto-tagging rule based on pattern matching.

    Attributes:
        name: Human-readable rule identifier
        pattern: Compiled regex pattern to match
        tags: Tags to add when pattern matches
        match_field: Which field to match against ('front' or 'back')
    """
    name: str
    pattern: re.Pattern
    tags: List[str]
    match_field: str


@dataclass
class TagSchema:
    """Tag schema configuration.

    Attributes:
        allowed_tags: Set of tags that are allowed to be kept
        blocked_tags: Set of tags that should be silently removed
        case_sensitive: Whether tag comparison is case-sensitive
        normalize_tags: Whether to normalize tag spacing/formatting
        auto_tag_rules: List of pattern-based auto-tagging rules
    """
    allowed_tags: Set[str]
    blocked_tags: Set[str]
    case_sensitive: bool
    normalize_tags: bool
    auto_tag_rules: List[AutoTagRule]


@dataclass
class CardTagResult:
    """Complete tag analysis for a single card.

    Attributes:
        original_tags: Original tags string from card
        kept_tags: Tags that passed allowlist check
        deleted_tags: Blocked tags that were removed
        unknown_tags: Tags not in allowlist/blocklist (need review)
        auto_added_tags: Tags added by auto-tagging rules
        final_tags: All kept + auto-added tags combined
        needs_review: True if unknown tags exist
    """
    original_tags: str
    kept_tags: List[str]
    deleted_tags: List[str]
    unknown_tags: List[str]
    auto_added_tags: List[str]
    final_tags: List[str]
    needs_review: bool


def load_tag_schema(path: str | Path) -> TagSchema:
    """Load tag schema from JSON file.

    Args:
        path: Path to tag schema JSON file

    Returns:
        Loaded TagSchema object

    Raises:
        FileNotFoundError: If schema file doesn't exist
        ValueError: If schema JSON is invalid or regex patterns fail to compile
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Tag schema file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in tag schema file: {e}")

    # Parse allowed/blocked tags
    allowed_tags = set(data.get("allowed_tags", []))
    blocked_tags = set(data.get("blocked_tags", []))
    case_sensitive = data.get("case_sensitive", False)
    normalize_tags = data.get("normalize_tags", True)

    # Normalize tag sets if case-insensitive
    if not case_sensitive:
        allowed_tags = {tag.lower() for tag in allowed_tags}
        blocked_tags = {tag.lower() for tag in blocked_tags}

    # Parse auto-tag rules
    auto_tag_rules = []
    for rule_data in data.get("auto_tag_rules", []):
        try:
            pattern = re.compile(rule_data["pattern"])
        except re.error as e:
            raise ValueError(f"Invalid regex in rule '{rule_data.get('name', 'unnamed')}': {e}")

        auto_tag_rules.append(
            AutoTagRule(
                name=rule_data["name"],
                pattern=pattern,
                tags=rule_data["tags"],
                match_field=rule_data.get("match_field", "front")
            )
        )

    return TagSchema(
        allowed_tags=allowed_tags,
        blocked_tags=blocked_tags,
        case_sensitive=case_sensitive,
        normalize_tags=normalize_tags,
        auto_tag_rules=auto_tag_rules
    )


def parse_tags(tags_string: str) -> List[str]:
    """Parse Anki tag string into list of tags.

    Anki uses space-separated tags. This function splits on whitespace
    and strips each tag.

    Args:
        tags_string: Space-separated tag string from Anki

    Returns:
        List of individual tags (empty list if input is empty)
    """
    if not tags_string or not tags_string.strip():
        return []

    # Split on whitespace and filter out empty strings
    tags = [tag.strip() for tag in tags_string.split()]
    return [tag for tag in tags if tag]


def format_tags(tags_list: List[str]) -> str:
    """Format tag list back to Anki string format.

    Args:
        tags_list: List of tags

    Returns:
        Space-separated tag string (empty string if list is empty)
    """
    if not tags_list:
        return ""
    return " ".join(tags_list)


def normalize_tag(tag: str, normalize: bool = True, case_sensitive: bool = False) -> str:
    """Normalize a tag for comparison.

    Args:
        tag: Tag to normalize
        normalize: Whether to apply normalization (strip whitespace)
        case_sensitive: Whether to preserve case

    Returns:
        Normalized tag
    """
    if normalize:
        tag = tag.strip()
    if not case_sensitive:
        tag = tag.lower()
    return tag


def _apply_auto_tagging(
    front: str,
    back: str,
    schema: TagSchema,
    existing_tags: Set[str]
) -> List[str]:
    """Apply auto-tagging rules to card fields.

    Args:
        front: Front field text (Greek)
        back: Back field text (English)
        schema: Tag schema with auto-tag rules
        existing_tags: Set of tags already on the card (normalized)

    Returns:
        List of tags to auto-add
    """
    auto_added = []

    # Normalize Greek text for pattern matching
    normalized_front = normalize_greek_for_match(front)
    normalized_back = back.strip().lower() if back else ""

    for rule in schema.auto_tag_rules:
        # Choose field to match against
        if rule.match_field == "front":
            text_to_match = normalized_front
        elif rule.match_field == "back":
            text_to_match = normalized_back
        else:
            continue  # Unknown field, skip

        # Check if pattern matches
        if rule.pattern.search(text_to_match):
            # Add tags from this rule
            for tag in rule.tags:
                # Normalize tag for comparison
                norm_tag = normalize_tag(tag, schema.normalize_tags, schema.case_sensitive)

                # Only add if:
                # 1. Tag is in allowlist
                # 2. Tag is not in blocklist
                # 3. Tag is not already present
                if (norm_tag in schema.allowed_tags and
                    norm_tag not in schema.blocked_tags and
                    norm_tag not in existing_tags):
                    auto_added.append(norm_tag)

    # De-duplicate auto-added tags
    seen = set()
    unique_auto_added = []
    for tag in auto_added:
        if tag not in seen:
            seen.add(tag)
            unique_auto_added.append(tag)

    return unique_auto_added


def analyze_card_tags(
    front: str,
    back: str,
    tags: str,
    schema: TagSchema,
    enable_auto_tag: bool = False
) -> CardTagResult:
    """Analyze tags for a single card with optional auto-tagging.

    Args:
        front: Front field text (Greek)
        back: Back field text (English)
        tags: Original tags string from card
        schema: Tag schema for validation and auto-tagging
        enable_auto_tag: Whether to apply auto-tagging rules

    Returns:
        CardTagResult with tag analysis
    """
    original_tags = tags
    parsed_tags = parse_tags(tags)

    kept_tags = []
    deleted_tags = []
    unknown_tags = []

    # Classify each tag
    for tag in parsed_tags:
        norm_tag = normalize_tag(tag, schema.normalize_tags, schema.case_sensitive)

        if norm_tag in schema.allowed_tags:
            kept_tags.append(norm_tag)
        elif norm_tag in schema.blocked_tags:
            deleted_tags.append(norm_tag)
        else:
            unknown_tags.append(norm_tag)

    # De-duplicate tags
    kept_tags = list(dict.fromkeys(kept_tags))  # Preserve order
    deleted_tags = list(dict.fromkeys(deleted_tags))
    unknown_tags = list(dict.fromkeys(unknown_tags))

    # Apply auto-tagging if enabled
    auto_added_tags = []
    if enable_auto_tag:
        existing_tags = set(kept_tags)
        auto_added_tags = _apply_auto_tagging(front, back, schema, existing_tags)

    # Combine kept + auto-added for final tags
    final_tags = kept_tags + auto_added_tags

    return CardTagResult(
        original_tags=original_tags,
        kept_tags=kept_tags,
        deleted_tags=deleted_tags,
        unknown_tags=unknown_tags,
        auto_added_tags=auto_added_tags,
        final_tags=final_tags,
        needs_review=len(unknown_tags) > 0
    )
