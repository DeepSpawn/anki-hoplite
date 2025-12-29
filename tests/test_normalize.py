"""Tests for normalization functionality."""

import pytest
from anki_hoplite.normalize import (
    normalize_text_nfc,
    strip_accents,
    normalize_greek_for_match,
)


class TestNormalizeTextNFC:
    """Test Unicode NFC normalization."""

    def test_precomposed_characters(self):
        """Test that precomposed characters remain stable."""
        text = "λύω"  # Precomposed characters
        result = normalize_text_nfc(text)
        assert result == "λύω"

    def test_combining_characters(self):
        """Test that combining characters are normalized to NFC."""
        # λ + combining acute accent + ύ + ω
        text = "λ\u0301ύω"
        result = normalize_text_nfc(text)
        # Should normalize to precomposed form
        assert result == "λ́ύω"

    def test_none_input(self):
        """Test that None input returns empty string."""
        result = normalize_text_nfc(None)
        assert result == ""

    def test_empty_string(self):
        """Test that empty string remains empty."""
        result = normalize_text_nfc("")
        assert result == ""


class TestStripAccents:
    """Test accent stripping functionality."""

    def test_strip_acute_accent(self):
        """Test stripping acute accent from Greek vowels."""
        text = "λύω"
        result = strip_accents(text)
        assert result == "λυω"

    def test_strip_grave_accent(self):
        """Test stripping grave accent."""
        text = "ὰ"
        result = strip_accents(text)
        assert result == "α"

    def test_strip_circumflex(self):
        """Test stripping circumflex accent."""
        text = "ῶ"
        result = strip_accents(text)
        assert result == "ω"

    def test_strip_breathing_marks(self):
        """Test stripping breathing marks (rough and smooth)."""
        text = "ἀ"  # smooth breathing
        result = strip_accents(text)
        assert result == "α"

        text = "ἁ"  # rough breathing
        result = strip_accents(text)
        assert result == "α"

    def test_multiple_accents(self):
        """Test stripping multiple types of accents."""
        text = "εἶπον"  # epsilon with circumflex and breathing
        result = strip_accents(text)
        assert result == "ειπον"

    def test_preserve_base_letters(self):
        """Test that base letters are preserved."""
        text = "αβγδεζηθικλμνξοπρστυφχψω"
        result = strip_accents(text)
        assert result == "αβγδεζηθικλμνξοπρστυφχψω"


class TestNormalizeGreekForMatch:
    """Test complete Greek normalization for matching."""

    def test_full_normalization_pipeline(self):
        """Test that all normalization steps are applied."""
        text = "λύω"  # with accent
        result = normalize_greek_for_match(text)
        assert result == "λυω"  # lowercase, no accent

    def test_case_normalization(self):
        """Test lowercase conversion."""
        text = "ΛΥΟΩ"
        result = normalize_greek_for_match(text)
        assert result == "λυοω"

    def test_punctuation_removal(self):
        """Test that punctuation is removed."""
        text = "λύω."
        result = normalize_greek_for_match(text)
        assert result == "λυω"

        text = "λύω, καί"
        result = normalize_greek_for_match(text)
        assert result == "λυω και"

    def test_final_sigma_normalization(self):
        """Test that final sigma (ς) is normalized to medial sigma (σ)."""
        text = "λόγος"
        result = normalize_greek_for_match(text)
        assert result == "λογοσ"

    def test_whitespace_collapse(self):
        """Test that multiple whitespaces are collapsed to single space."""
        text = "λύω   καί"
        result = normalize_greek_for_match(text)
        assert result == "λυω και"

    def test_whitespace_trim(self):
        """Test that leading/trailing whitespace is removed."""
        text = "  λύω  "
        result = normalize_greek_for_match(text)
        assert result == "λυω"

    def test_complex_example(self):
        """Test normalization of complex Greek text."""
        text = "Εἶπον, ὦ Ξανθία"
        result = normalize_greek_for_match(text)
        # Should be: lowercase, no accents, no punctuation, no breathing
        assert result == "ειπον ω ξανθια"

    def test_empty_input(self):
        """Test that empty input returns empty string."""
        result = normalize_greek_for_match("")
        assert result == ""

    def test_none_input(self):
        """Test that None input returns empty string."""
        result = normalize_greek_for_match(None)
        assert result == ""

    def test_article_forms(self):
        """Test normalization of various article forms."""
        articles = ["ὁ", "ἡ", "τό", "τοῦ", "τῆς", "τῷ", "τήν"]
        results = [normalize_greek_for_match(a) for a in articles]

        # All should be normalized (no accents, lowercase)
        assert results[0] == "ο"
        assert results[1] == "η"
        assert results[2] == "το"
        assert results[3] == "του"
        assert results[4] == "τησ"  # final sigma
        assert results[5] == "τω"
        assert results[6] == "την"

    def test_verb_forms_normalize_to_same_stem(self):
        """Test that different forms of the same verb normalize similarly."""
        present = "λύω"
        second_person = "λύεις"
        aorist = "ἔλυσα"

        # All should have the same stem after normalization
        present_norm = normalize_greek_for_match(present)
        second_norm = normalize_greek_for_match(second_person)
        aorist_norm = normalize_greek_for_match(aorist)

        assert present_norm == "λυω"
        assert second_norm == "λυεισ"  # final sigma
        assert aorist_norm == "ελυσα"

        # While not identical, they all start with λυ stem (accents removed)
        assert present_norm.startswith("λυ")
        assert second_norm.startswith("λυ")
        assert aorist_norm.endswith("λυσα")
