"""Tests for tag hygiene functionality."""

import re
import tempfile
from pathlib import Path

import pytest
from anki_hoplite.tag_hygiene import (
    AutoTagRule,
    TagSchema,
    CardTagResult,
    load_tag_schema,
    parse_tags,
    format_tags,
    normalize_tag,
    analyze_card_tags,
)


class TestParseTags:
    """Test tag parsing functionality."""

    def test_parse_space_separated_tags(self):
        """Test parsing space-separated tags."""
        tags_str = "verb aorist"
        result = parse_tags(tags_str)
        assert result == ["verb", "aorist"]

    def test_parse_empty_tags(self):
        """Test parsing empty tag string."""
        assert parse_tags("") == []
        assert parse_tags("   ") == []

    def test_parse_tags_with_extra_whitespace(self):
        """Test parsing tags with extra whitespace."""
        tags_str = "  verb   aorist  "
        result = parse_tags(tags_str)
        assert result == ["verb", "aorist"]

    def test_parse_single_tag(self):
        """Test parsing single tag."""
        tags_str = "noun"
        result = parse_tags(tags_str)
        assert result == ["noun"]

    def test_parse_multiple_spaces(self):
        """Test parsing tags separated by multiple spaces."""
        tags_str = "verb  aorist   present"
        result = parse_tags(tags_str)
        assert result == ["verb", "aorist", "present"]


class TestFormatTags:
    """Test tag formatting functionality."""

    def test_format_empty_list(self):
        """Test formatting empty tag list."""
        result = format_tags([])
        assert result == ""

    def test_format_single_tag(self):
        """Test formatting single tag."""
        result = format_tags(["verb"])
        assert result == "verb"

    def test_format_multiple_tags(self):
        """Test formatting multiple tags."""
        result = format_tags(["verb", "aorist", "present"])
        assert result == "verb aorist present"


class TestNormalizeTag:
    """Test tag normalization functionality."""

    def test_normalize_lowercase(self):
        """Test lowercasing tag."""
        result = normalize_tag("VERB", normalize=True, case_sensitive=False)
        assert result == "verb"

    def test_preserve_case_when_sensitive(self):
        """Test preserving case when case_sensitive=True."""
        result = normalize_tag("VERB", normalize=True, case_sensitive=True)
        assert result == "VERB"

    def test_strip_whitespace(self):
        """Test stripping whitespace from tag."""
        result = normalize_tag("  verb  ", normalize=True)
        assert result == "verb"

    def test_no_normalization(self):
        """Test skipping normalization."""
        result = normalize_tag("  VERB  ", normalize=False, case_sensitive=True)
        assert result == "  VERB  "


class TestLoadTagSchema:
    """Test tag schema loading functionality."""

    def test_load_valid_schema(self):
        """Test loading valid tag schema."""
        schema_data = {
            "allowed_tags": ["noun", "verb", "adjective"],
            "blocked_tags": ["tmp", "test"],
            "case_sensitive": False,
            "normalize_tags": True,
            "auto_tag_rules": [
                {
                    "name": "test_rule",
                    "pattern": "^test$",
                    "tags": ["test_tag"],
                    "match_field": "front"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            import json
            json.dump(schema_data, f)
            schema_path = f.name

        try:
            schema = load_tag_schema(schema_path)
            assert schema.allowed_tags == {"noun", "verb", "adjective"}
            assert schema.blocked_tags == {"tmp", "test"}
            assert schema.case_sensitive is False
            assert schema.normalize_tags is True
            assert len(schema.auto_tag_rules) == 1
            assert schema.auto_tag_rules[0].name == "test_rule"
        finally:
            Path(schema_path).unlink()

    def test_load_missing_schema_raises_error(self):
        """Test that loading non-existent schema raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_tag_schema("/nonexistent/path/schema.json")

    def test_invalid_json_raises_error(self):
        """Test that invalid JSON raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            f.write("{invalid json}")
            schema_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid JSON"):
                load_tag_schema(schema_path)
        finally:
            Path(schema_path).unlink()

    def test_invalid_regex_raises_error(self):
        """Test that invalid regex pattern raises ValueError."""
        schema_data = {
            "allowed_tags": ["test"],
            "blocked_tags": [],
            "auto_tag_rules": [
                {
                    "name": "bad_rule",
                    "pattern": "[invalid(regex",
                    "tags": ["test"],
                    "match_field": "front"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            import json
            json.dump(schema_data, f)
            schema_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid regex"):
                load_tag_schema(schema_path)
        finally:
            Path(schema_path).unlink()

    def test_case_insensitive_normalizes_tags(self):
        """Test that case_sensitive=False normalizes tag sets."""
        schema_data = {
            "allowed_tags": ["Noun", "VERB", "Adjective"],
            "blocked_tags": ["TMP", "Test"],
            "case_sensitive": False,
            "normalize_tags": True,
            "auto_tag_rules": []
        }

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            import json
            json.dump(schema_data, f)
            schema_path = f.name

        try:
            schema = load_tag_schema(schema_path)
            assert schema.allowed_tags == {"noun", "verb", "adjective"}
            assert schema.blocked_tags == {"tmp", "test"}
        finally:
            Path(schema_path).unlink()


class TestTagClassification:
    """Test tag classification (allowed/blocked/unknown)."""

    def create_simple_schema(self):
        """Create a simple schema for testing."""
        return TagSchema(
            allowed_tags={"noun", "verb", "adjective"},
            blocked_tags={"tmp", "test", "delete"},
            case_sensitive=False,
            normalize_tags=True,
            auto_tag_rules=[]
        )

    def test_allowed_tag_kept(self):
        """Test that allowed tags are kept."""
        schema = self.create_simple_schema()
        result = analyze_card_tags("text", "back", "verb noun", schema)
        assert result.kept_tags == ["verb", "noun"]
        assert result.deleted_tags == []
        assert result.unknown_tags == []
        assert result.needs_review is False

    def test_blocked_tag_deleted(self):
        """Test that blocked tags are deleted."""
        schema = self.create_simple_schema()
        result = analyze_card_tags("text", "back", "verb tmp", schema)
        assert result.kept_tags == ["verb"]
        assert result.deleted_tags == ["tmp"]
        assert result.unknown_tags == []

    def test_unknown_tag_flagged(self):
        """Test that unknown tags are flagged."""
        schema = self.create_simple_schema()
        result = analyze_card_tags("text", "back", "verb unknown", schema)
        assert result.kept_tags == ["verb"]
        assert result.deleted_tags == []
        assert result.unknown_tags == ["unknown"]
        assert result.needs_review is True

    def test_mixed_tags(self):
        """Test classification with mixed allowed/blocked/unknown tags."""
        schema = self.create_simple_schema()
        result = analyze_card_tags("text", "back", "verb tmp unknown noun delete strange", schema)
        assert result.kept_tags == ["verb", "noun"]
        assert result.deleted_tags == ["tmp", "delete"]
        assert result.unknown_tags == ["unknown", "strange"]
        assert result.needs_review is True

    def test_case_insensitive_matching(self):
        """Test that tags match case-insensitively."""
        schema = self.create_simple_schema()
        result = analyze_card_tags("text", "back", "VERB Noun TMP", schema)
        assert result.kept_tags == ["verb", "noun"]
        assert result.deleted_tags == ["tmp"]

    def test_duplicate_tags_deduplicated(self):
        """Test that duplicate tags are removed."""
        schema = self.create_simple_schema()
        result = analyze_card_tags("text", "back", "verb verb noun", schema)
        assert result.kept_tags == ["verb", "noun"]

    def test_empty_tags(self):
        """Test handling of empty tags field."""
        schema = self.create_simple_schema()
        result = analyze_card_tags("text", "back", "", schema)
        assert result.kept_tags == []
        assert result.deleted_tags == []
        assert result.unknown_tags == []
        assert result.needs_review is False


class TestAutoTagging:
    """Test auto-tagging functionality."""

    def create_schema_with_rules(self):
        """Create schema with auto-tag rules.

        Note: Patterns match NORMALIZED text (accents stripped, lowercase).
        So ὁ becomes ο, ἡ becomes η, etc.
        """
        rules = [
            AutoTagRule(
                name="masculine_article",
                pattern=re.compile(r"^ο$"),  # ὁ normalized
                tags=["article", "masculine"],
                match_field="front"
            ),
            AutoTagRule(
                name="feminine_article",
                pattern=re.compile(r"^η$"),  # ἡ normalized
                tags=["article", "feminine"],
                match_field="front"
            ),
            AutoTagRule(
                name="aorist_marker",
                pattern=re.compile(r"^ε[^\s]+σα"),  # ἐλυσα normalized
                tags=["aorist"],
                match_field="front"
            )
        ]
        return TagSchema(
            allowed_tags={"article", "masculine", "feminine", "aorist", "verb"},
            blocked_tags={"tmp"},
            case_sensitive=False,
            normalize_tags=True,
            auto_tag_rules=rules
        )

    def test_auto_tag_masculine_article(self):
        """Test auto-tagging masculine article."""
        schema = self.create_schema_with_rules()
        result = analyze_card_tags("ὁ", "the", "", schema, enable_auto_tag=True)
        assert "article" in result.auto_added_tags
        assert "masculine" in result.auto_added_tags
        assert "article" in result.final_tags
        assert "masculine" in result.final_tags

    def test_auto_tag_feminine_article(self):
        """Test auto-tagging feminine article."""
        schema = self.create_schema_with_rules()
        result = analyze_card_tags("ἡ", "the", "", schema, enable_auto_tag=True)
        assert "article" in result.auto_added_tags
        assert "feminine" in result.auto_added_tags

    def test_auto_tag_aorist(self):
        """Test auto-tagging aorist verb."""
        schema = self.create_schema_with_rules()
        result = analyze_card_tags("ἐλυσα", "I loosed", "", schema, enable_auto_tag=True)
        assert "aorist" in result.auto_added_tags

    def test_multiple_rules_match(self):
        """Test that multiple rules can match."""
        # Create a contrived example where multiple patterns match
        rules = [
            AutoTagRule(
                name="rule1",
                pattern=re.compile(r"test"),
                tags=["tag1"],
                match_field="front"
            ),
            AutoTagRule(
                name="rule2",
                pattern=re.compile(r"test"),
                tags=["tag2"],
                match_field="front"
            )
        ]
        schema = TagSchema(
            allowed_tags={"tag1", "tag2"},
            blocked_tags={},
            case_sensitive=False,
            normalize_tags=True,
            auto_tag_rules=rules
        )
        result = analyze_card_tags("test", "back", "", schema, enable_auto_tag=True)
        assert "tag1" in result.auto_added_tags
        assert "tag2" in result.auto_added_tags

    def test_no_duplicate_auto_tags(self):
        """Test that duplicate auto-tags are removed."""
        rules = [
            AutoTagRule(
                name="rule1",
                pattern=re.compile(r"test"),
                tags=["tag1", "tag1"],  # Duplicate in rule
                match_field="front"
            )
        ]
        schema = TagSchema(
            allowed_tags={"tag1"},
            blocked_tags={},
            case_sensitive=False,
            normalize_tags=True,
            auto_tag_rules=rules
        )
        result = analyze_card_tags("test", "back", "", schema, enable_auto_tag=True)
        assert result.auto_added_tags.count("tag1") == 1

    def test_only_allowed_tags_added(self):
        """Test that only allowed tags are auto-added."""
        rules = [
            AutoTagRule(
                name="rule1",
                pattern=re.compile(r"test"),
                tags=["allowed", "notallowed"],
                match_field="front"
            )
        ]
        schema = TagSchema(
            allowed_tags={"allowed"},  # Only "allowed" is in allowlist
            blocked_tags={},
            case_sensitive=False,
            normalize_tags=True,
            auto_tag_rules=rules
        )
        result = analyze_card_tags("test", "back", "", schema, enable_auto_tag=True)
        assert "allowed" in result.auto_added_tags
        assert "notallowed" not in result.auto_added_tags

    def test_blocked_tags_not_auto_added(self):
        """Test that blocked tags are not auto-added."""
        rules = [
            AutoTagRule(
                name="rule1",
                pattern=re.compile(r"test"),
                tags=["blocked"],
                match_field="front"
            )
        ]
        schema = TagSchema(
            allowed_tags={"blocked"},
            blocked_tags={"blocked"},  # In both allowed and blocked
            case_sensitive=False,
            normalize_tags=True,
            auto_tag_rules=rules
        )
        result = analyze_card_tags("test", "back", "", schema, enable_auto_tag=True)
        assert "blocked" not in result.auto_added_tags

    def test_auto_tag_disabled_by_default(self):
        """Test that auto-tagging is disabled when enable_auto_tag=False."""
        schema = self.create_schema_with_rules()
        result = analyze_card_tags("ὁ", "the", "", schema, enable_auto_tag=False)
        assert result.auto_added_tags == []

    def test_existing_tags_not_duplicated(self):
        """Test that auto-tagging doesn't duplicate existing tags."""
        schema = self.create_schema_with_rules()
        # "article" already exists in tags
        result = analyze_card_tags("ὁ", "the", "article", schema, enable_auto_tag=True)
        assert result.kept_tags == ["article"]
        # "masculine" should be auto-added, but not "article" (already present)
        assert "masculine" in result.auto_added_tags
        assert "article" not in result.auto_added_tags

    def test_match_back_field(self):
        """Test auto-tagging based on back field."""
        rules = [
            AutoTagRule(
                name="english_verb",
                pattern=re.compile(r"^i .+"),
                tags=["verb"],
                match_field="back"
            )
        ]
        schema = TagSchema(
            allowed_tags={"verb"},
            blocked_tags={},
            case_sensitive=False,
            normalize_tags=True,
            auto_tag_rules=rules
        )
        result = analyze_card_tags("λύω", "I loose", "", schema, enable_auto_tag=True)
        assert "verb" in result.auto_added_tags


class TestCardTagResult:
    """Test CardTagResult integration."""

    def test_final_tags_combines_kept_and_auto(self):
        """Test that final_tags combines kept and auto-added tags."""
        schema = TagSchema(
            allowed_tags={"noun", "masculine"},
            blocked_tags={},
            case_sensitive=False,
            normalize_tags=True,
            auto_tag_rules=[
                AutoTagRule(
                    name="auto_rule",
                    pattern=re.compile(r"test"),
                    tags=["masculine"],
                    match_field="front"
                )
            ]
        )
        result = analyze_card_tags("test", "back", "noun", schema, enable_auto_tag=True)
        assert result.kept_tags == ["noun"]
        assert "masculine" in result.auto_added_tags
        assert "noun" in result.final_tags
        assert "masculine" in result.final_tags

    def test_original_tags_preserved(self):
        """Test that original tags are preserved in result."""
        schema = TagSchema(
            allowed_tags={"verb"},
            blocked_tags={"tmp"},
            case_sensitive=False,
            normalize_tags=True,
            auto_tag_rules=[]
        )
        result = analyze_card_tags("text", "back", "verb tmp unknown", schema)
        assert result.original_tags == "verb tmp unknown"
