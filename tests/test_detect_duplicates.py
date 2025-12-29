"""Tests for duplicate detection functionality."""

from unittest.mock import MagicMock

import pytest

from anki_hoplite.deck_index import DeckIndex, NoteEntry
from anki_hoplite.detect_duplicates import DetectionResult, analyze_candidates
from anki_hoplite.lemmatize import GreekLemmatizer


class MockLemmatizer:
    """Mock lemmatizer for testing."""

    def __init__(self):
        self.lemma_map = {
            "λύω": "λυω",
            "λύεις": "λυω",
            "ἔλυσα": "λυω",
            "καί": "και",
            "λέγω": "λεγω",
            "εἶπον": "ειπον",
        }

    def best_lemma(self, text):
        """Return lemma for the text."""
        # Simple implementation: return first word's lemma
        first_word = text.split()[0] if text else ""
        return self.lemma_map.get(first_word, first_word.lower())


@pytest.fixture
def mock_lemmatizer():
    """Fixture providing a mock lemmatizer."""
    return MockLemmatizer()


@pytest.fixture
def sample_deck(mock_lemmatizer):
    """Fixture providing a sample deck with some entries."""
    deck = DeckIndex()

    # Add some notes to the deck
    notes = [
        NoteEntry(
            note_id="note1", model="Basic", greek_text="λύω", english_text="I loose"
        ),
        NoteEntry(
            note_id="note2", model="Basic", greek_text="καί", english_text="and"
        ),
        NoteEntry(
            note_id="note3", model="Basic", greek_text="λέγω", english_text="I say"
        ),
        NoteEntry(
            note_id="note4",
            model="Basic",
            greek_text="ἀγρός",
            english_text="field",
        ),
    ]

    for note in notes:
        deck.add_note(note, lemmatizer=mock_lemmatizer)

    return deck


class TestDetectionResult:
    """Test DetectionResult dataclass."""

    def test_detection_result_creation(self):
        """Test creating a DetectionResult."""
        result = DetectionResult(
            front="λύω",
            back="I loose",
            tags="verb",
            normalized_greek="λυω",
            lemma="λυω",
            warning_level="high",
            match_reason="exact-greek-match",
            matched_note_ids="note1,note2",
        )

        assert result.front == "λύω"
        assert result.back == "I loose"
        assert result.tags == "verb"
        assert result.normalized_greek == "λυω"
        assert result.lemma == "λυω"
        assert result.warning_level == "high"
        assert result.match_reason == "exact-greek-match"
        assert result.matched_note_ids == "note1,note2"


class TestAnalyzeCandidates:
    """Test candidate analysis functionality."""

    def test_exact_greek_match(self, sample_deck, mock_lemmatizer):
        """Test detection of exact Greek string match (high level)."""
        candidates = [{"front": "λύω", "back": "I loose", "tags": ""}]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        assert result.warning_level == "high"
        assert result.match_reason == "exact-greek-match"
        assert "note1" in result.matched_note_ids

    def test_lemma_match(self, sample_deck, mock_lemmatizer):
        """Test detection of lemma match (medium level)."""
        candidates = [
            {"front": "λύεις", "back": "you loose", "tags": ""}  # Different form of λύω
        ]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        assert result.warning_level == "medium"
        assert result.match_reason == "lemma-match"
        assert "note1" in result.matched_note_ids

    def test_english_gloss_match(self, sample_deck, mock_lemmatizer):
        """Test detection of English gloss match (low level)."""
        candidates = [
            {"front": "πεδίον", "back": "field", "tags": ""}  # Different Greek word
        ]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        assert result.warning_level == "low"
        assert result.match_reason == "english-gloss-match"
        assert "note4" in result.matched_note_ids

    def test_no_match(self, sample_deck, mock_lemmatizer):
        """Test case where there's no match."""
        candidates = [{"front": "νέος", "back": "new", "tags": ""}]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        assert result.warning_level == "none"
        assert result.match_reason == "no-match"
        assert result.matched_note_ids == ""

    def test_priority_exact_over_lemma(self, sample_deck, mock_lemmatizer):
        """Test that exact match takes priority over lemma match."""
        # καί exists as exact match in deck
        candidates = [{"front": "καί", "back": "and", "tags": ""}]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        # Should be high (exact), not medium (lemma)
        assert result.warning_level == "high"
        assert result.match_reason == "exact-greek-match"

    def test_priority_lemma_over_english(self, sample_deck, mock_lemmatizer):
        """Test that lemma match takes priority over English match."""
        # Add a note with same English but different lemma
        deck = DeckIndex()
        deck.add_note(
            NoteEntry(
                note_id="note1", model="Basic", greek_text="λύω", english_text="I loose"
            ),
            lemmatizer=mock_lemmatizer,
        )

        # Different inflection of λύω with same English
        candidates = [{"front": "λύεις", "back": "I loose", "tags": ""}]

        results = analyze_candidates(candidates, deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        # Should be medium (lemma), not low (English)
        assert result.warning_level == "medium"
        assert result.match_reason == "lemma-match"

    def test_multiple_candidates(self, sample_deck, mock_lemmatizer):
        """Test analyzing multiple candidates."""
        candidates = [
            {"front": "λύω", "back": "I loose", "tags": ""},  # high
            {"front": "λύεις", "back": "you loose", "tags": ""},  # medium
            {"front": "πεδίον", "back": "field", "tags": ""},  # low
            {"front": "νέος", "back": "new", "tags": ""},  # none
        ]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 4
        assert results[0].warning_level == "high"
        assert results[1].warning_level == "medium"
        assert results[2].warning_level == "low"
        assert results[3].warning_level == "none"

    def test_empty_candidates(self, sample_deck, mock_lemmatizer):
        """Test analyzing empty candidate list."""
        candidates = []
        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)
        assert results == []

    def test_empty_front_field(self, sample_deck, mock_lemmatizer):
        """Test candidate with empty front field."""
        candidates = [{"front": "", "back": "I loose", "tags": ""}]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        assert result.normalized_greek == ""
        assert result.lemma == ""
        # Should only check English since Greek is empty
        assert result.warning_level == "low"
        assert result.match_reason == "english-gloss-match"

    def test_empty_back_field(self, sample_deck, mock_lemmatizer):
        """Test candidate with empty back field."""
        candidates = [{"front": "λύω", "back": "", "tags": ""}]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        # Should still match on Greek
        assert result.warning_level == "high"
        assert result.match_reason == "exact-greek-match"

    def test_normalized_greek_in_result(self, sample_deck, mock_lemmatizer):
        """Test that normalized Greek is included in result."""
        candidates = [{"front": "Λύω", "back": "I loose", "tags": ""}]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        # Should be normalized (lowercase, no accents)
        assert result.normalized_greek == "λυω"

    def test_lemma_in_result(self, sample_deck, mock_lemmatizer):
        """Test that lemma is included in result."""
        candidates = [{"front": "λύεις", "back": "you loose", "tags": ""}]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        # Should have the lemma of λύεις
        assert result.lemma == "λυω"

    def test_tags_preserved(self, sample_deck, mock_lemmatizer):
        """Test that tags are preserved in result."""
        candidates = [{"front": "λύω", "back": "I loose", "tags": "verb aorist"}]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        assert result.tags == "verb aorist"

    def test_multiple_matches(self, sample_deck, mock_lemmatizer):
        """Test that multiple matching note IDs are returned."""
        deck = DeckIndex()

        # Add multiple notes with same Greek text
        deck.add_note(
            NoteEntry(
                note_id="note1", model="Basic", greek_text="λύω", english_text="I loose"
            ),
            lemmatizer=mock_lemmatizer,
        )
        deck.add_note(
            NoteEntry(
                note_id="note2",
                model="Basic",
                greek_text="λύω",
                english_text="I release",
            ),
            lemmatizer=mock_lemmatizer,
        )

        candidates = [{"front": "λύω", "back": "I loose", "tags": ""}]

        results = analyze_candidates(candidates, deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        assert result.warning_level == "high"
        # Should contain both note IDs
        assert "note1" in result.matched_note_ids
        assert "note2" in result.matched_note_ids

    def test_case_insensitive_english_match(self, sample_deck, mock_lemmatizer):
        """Test that English matching is case-insensitive."""
        candidates = [
            {"front": "πεδίον", "back": "FIELD", "tags": ""}  # Uppercase
        ]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        assert result.warning_level == "low"
        assert result.match_reason == "english-gloss-match"

    def test_whitespace_handling_english(self, sample_deck, mock_lemmatizer):
        """Test that English whitespace is handled correctly."""
        candidates = [
            {"front": "πεδίον", "back": "  field  ", "tags": ""}  # Extra whitespace
        ]

        results = analyze_candidates(candidates, sample_deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        assert result.warning_level == "low"
        assert result.match_reason == "english-gloss-match"


class TestDeckIndexIntegration:
    """Test integration between detect_duplicates and DeckIndex."""

    def test_empty_deck(self, mock_lemmatizer):
        """Test analysis against empty deck."""
        deck = DeckIndex()
        candidates = [{"front": "λύω", "back": "I loose", "tags": ""}]

        results = analyze_candidates(candidates, deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        assert result.warning_level == "none"
        assert result.match_reason == "no-match"

    def test_deck_with_lemma_variations(self, mock_lemmatizer):
        """Test deck containing multiple forms of the same lemma."""
        deck = DeckIndex()

        # Add multiple inflected forms
        deck.add_note(
            NoteEntry(
                note_id="note1", model="Basic", greek_text="λύω", english_text="I loose"
            ),
            lemmatizer=mock_lemmatizer,
        )
        deck.add_note(
            NoteEntry(
                note_id="note2",
                model="Basic",
                greek_text="λύεις",
                english_text="you loose",
            ),
            lemmatizer=mock_lemmatizer,
        )

        # Try to add another form
        candidates = [{"front": "ἔλυσα", "back": "I loosed", "tags": ""}]

        results = analyze_candidates(candidates, deck, mock_lemmatizer)

        assert len(results) == 1
        result = results[0]
        # Should match via lemma
        assert result.warning_level == "medium"
        assert result.match_reason == "lemma-match"
        # Should match both existing notes
        assert "note1" in result.matched_note_ids or "note2" in result.matched_note_ids
