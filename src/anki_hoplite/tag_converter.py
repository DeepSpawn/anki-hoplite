"""Tag conversion module for normalizing non-standard tags to schema-compliant format.

This module handles conversion of various tag formats used in flashcard imports:
- Morphology abbreviations (3pl, acc, imp-sg) → standardized tags
- Compound tags (verb_present, adverb-ouketi) → base tags
- Chapter/organizational metadata → extracted to separate fields
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .tag_hygiene import TagSchema


@dataclass
class TagConversionResult:
    """Result of tag conversion for a single card."""
    converted_tags: List[str]  # Schema-compliant tags
    chapter: str  # Extracted chapter number (e.g., "3")
    source: str  # Extracted source (e.g., "athenaze")
    section: str  # Extracted section (e.g., "reading", "wb3a")


class TagConverter:
    """Converts non-standard tags to schema-compliant format."""

    def __init__(self, mapping_path: Path):
        """Initialize converter with mapping configuration.

        Args:
            mapping_path: Path to tag conversion mapping JSON file
        """
        with open(mapping_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.morphology_map = self.config.get('morphology_mappings', {})
        self.compound_patterns = self.config.get('compound_tag_patterns', {})
        self.simple_map = self.config.get('simple_tag_mappings', {})
        self.chapter_config = self.config.get('chapter_handling', {})

        # Compile regex patterns for compound tags
        self.compiled_patterns = {
            pattern: re.compile(pattern)
            for pattern in self.compound_patterns.keys()
        }

        # Compile chapter extraction patterns
        self.chapter_patterns = [
            re.compile(pattern)
            for pattern in self.chapter_config.get('extract_patterns', [])
        ]

    def convert_tag(self, tag: str) -> List[str]:
        """Convert a single tag to schema-compliant tag(s).

        Args:
            tag: Original tag string

        Returns:
            List of converted tags (may be empty for metadata tags)
        """
        tag_lower = tag.lower()

        # Check simple mappings first
        if tag_lower in self.simple_map:
            return self.simple_map[tag_lower]

        # Check morphology mappings
        if tag_lower in self.morphology_map:
            return self.morphology_map[tag_lower]

        # Check compound patterns
        for pattern, replacement in self.compound_patterns.items():
            compiled = self.compiled_patterns[pattern]
            match = compiled.match(tag_lower)
            if match:
                # Handle $1 substitutions in replacement
                result = []
                for item in replacement:
                    if item == "$1" and match.groups():
                        # Map captured group to standard tag if possible
                        captured = match.group(1)
                        if captured in self.simple_map:
                            result.extend(self.simple_map[captured])
                        elif captured in self.morphology_map:
                            result.extend(self.morphology_map[captured])
                        # Otherwise skip the captured group
                    else:
                        result.append(item)
                return result

        # Tag doesn't match any pattern - return as-is for tag hygiene to handle
        return [tag]

    def extract_metadata(self, tags: List[str]) -> Tuple[str, str, str]:
        """Extract chapter, source, and section metadata from tags.

        Args:
            tags: List of original tags

        Returns:
            Tuple of (chapter, source, section)
        """
        chapter = ""
        source = self.chapter_config.get('default_source', "")
        section = ""

        for tag in tags:
            tag_lower = tag.lower()

            # Try chapter patterns
            for pattern in self.chapter_patterns:
                match = pattern.match(tag_lower)
                if match:
                    groups = match.groups()
                    if groups:
                        # Extract chapter number from first group
                        chapter = groups[0]

                        # Determine source from pattern match
                        if 'athenaze' in tag_lower:
                            source = "athenaze"
                    else:
                        # Pattern matched but no groups (e.g., athenaze1)
                        if 'athenaze' in tag_lower:
                            source = "athenaze"
                    break

            # Check for section markers
            if tag_lower in ['reading', 'passage']:
                section = tag_lower
            elif re.match(r'^wb\d+[a-z]$', tag_lower):
                section = tag_lower

        return chapter, source, section

    def is_organizational_tag(self, tag: str) -> bool:
        """Check if a tag is organizational (chapter/section) and should be filtered out.

        Args:
            tag: Tag to check

        Returns:
            True if tag matches chapter/section patterns and should be excluded from tags
        """
        tag_lower = tag.lower()

        # Check against chapter extraction patterns
        for pattern in self.chapter_patterns:
            if pattern.match(tag_lower):
                return True

        # Check against known section markers
        if tag_lower in ['reading', 'passage']:
            return True
        if re.match(r'^wb\d+[a-z]$', tag_lower):
            return True

        return False

    def convert_card_tags(self, tags_string: str, tag_schema: Optional["TagSchema"] = None) -> TagConversionResult:
        """Convert all tags for a card and extract metadata.

        Args:
            tags_string: Space-separated tag string from CSV
            tag_schema: Optional TagSchema for allowlist filtering

        Returns:
            TagConversionResult with converted tags and metadata
        """
        # Split tags and filter empty
        original_tags = [t.strip() for t in tags_string.split() if t.strip()]

        # Extract metadata
        chapter, source, section = self.extract_metadata(original_tags)

        # Convert tags
        converted_set: Set[str] = set()
        for tag in original_tags:
            # Skip organizational tags (they're in metadata fields now)
            if self.is_organizational_tag(tag):
                continue

            converted = self.convert_tag(tag)
            converted_set.update(converted)

        # Filter against allowlist if schema provided
        if tag_schema:
            allowed_set = {t.lower() for t in tag_schema.allowed_tags}
            converted_set = {t for t in converted_set if t.lower() in allowed_set}

        # Remove empty strings and sort for consistency
        converted_list = sorted([t for t in converted_set if t])

        return TagConversionResult(
            converted_tags=converted_list,
            chapter=chapter,
            source=source,
            section=section
        )


def load_tag_converter(mapping_path: Optional[Path] = None) -> TagConverter:
    """Load tag converter with default or custom mapping.

    Args:
        mapping_path: Optional path to mapping file (defaults to resources/tag_conversion_map.json)

    Returns:
        Initialized TagConverter instance
    """
    if mapping_path is None:
        # Default to resources/tag_conversion_map.json
        default_path = Path(__file__).parent.parent.parent / "resources" / "tag_conversion_map.json"
        mapping_path = default_path

    return TagConverter(mapping_path)
