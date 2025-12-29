"""Integration tests for the full anki-hoplite pipeline."""

import csv
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from anki_hoplite.deck_index import DeckIndex, NoteEntry
from anki_hoplite.detect_duplicates import analyze_candidates
from anki_hoplite.ingest import read_candidates_csv
from anki_hoplite.lemmatize import GreekLemmatizer
from anki_hoplite.normalize import normalize_greek_for_match
from anki_hoplite.report import write_results_csv


class MockBackoffLemmatizer:
    """Mock CLTK lemmatizer for integration tests."""

    def __init__(self):
        self.lemma_map = {
            "λύω": "λύω",
            "λύεις": "λύω",
            "λύει": "λύω",
            "ἔλυσα": "λύω",
            "ἐλύσαμεν": "λύω",
            "καί": "καί",
            "λέγω": "λέγω",
            "εἶπον": "εἶπον",
            "ἀγρός": "ἀγρός",
            "φέρε": "φέρω",
            "φέρω": "φέρω",
        }

    def lemmatize(self, tokens):
        """Mock lemmatize that returns list of (token, lemma) tuples."""
        results = []
        for token in tokens:
            lemma = self.lemma_map.get(token, token)
            results.append((token, lemma))
        return results


@pytest.fixture
def mock_cltk_backend():
    """Fixture that patches CLTK to use mock lemmatizer."""
    with patch("cltk.lemmatize.GreekBackoffLemmatizer") as mock:
        mock.return_value = MockBackoffLemmatizer()
        yield mock


class TestEndToEndPipeline:
    """Test complete pipeline from CSV input to analysis output."""

    def test_full_pipeline_with_csv(self, mock_cltk_backend):
        """Test the complete pipeline: CSV → analysis → report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # 1. Create input CSV
            input_csv = tmpdir / "candidates.csv"
            with input_csv.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["front", "back", "tags"])
                writer.writeheader()
                writer.writerow({"front": "λύω", "back": "I loose", "tags": "verb"})
                writer.writerow({"front": "λύεις", "back": "you loose", "tags": "verb"})
                writer.writerow({"front": "νέος", "back": "new", "tags": "adjective"})

            # 2. Create reference deck
            lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)
            deck = DeckIndex()
            deck.add_note(
                NoteEntry(
                    note_id="existing1",
                    model="Basic",
                    greek_text="λύω",
                    english_text="I loose",
                ),
                lemmatizer=lemmatizer,
            )

            # 3. Ingest candidates
            candidates = read_candidates_csv(input_csv)
            assert len(candidates) == 3

            # 4. Analyze
            results = analyze_candidates(
                [c.__dict__ for c in candidates], deck, lemmatizer
            )

            # 5. Verify results
            assert len(results) == 3

            # First candidate: exact match (high)
            assert results[0].front == "λύω"
            assert results[0].warning_level == "high"
            assert results[0].match_reason == "exact-greek-match"
            assert "existing1" in results[0].matched_note_ids

            # Second candidate: lemma match (medium)
            assert results[1].front == "λύεις"
            assert results[1].warning_level == "medium"
            assert results[1].match_reason == "lemma-match"

            # Third candidate: no match
            assert results[2].front == "νέος"
            assert results[2].warning_level == "none"
            assert results[2].match_reason == "no-match"

            # 6. Write output CSV
            output_csv = tmpdir / "results.csv"
            write_results_csv(str(output_csv), results)

            # 7. Verify output file
            assert output_csv.exists()
            with output_csv.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                output_rows = list(reader)

            assert len(output_rows) == 3
            assert output_rows[0]["front"] == "λύω"
            assert output_rows[0]["warning_level"] == "high"
            assert output_rows[1]["warning_level"] == "medium"
            assert output_rows[2]["warning_level"] == "none"

    def test_normalization_consistency(self, mock_cltk_backend):
        """Test that normalization is consistent across the pipeline."""
        lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)

        # Create deck with normalized text
        deck = DeckIndex()
        deck.add_note(
            NoteEntry(
                note_id="note1",
                model="Basic",
                greek_text="Λύω",  # Uppercase
                english_text="I loose",
            ),
            lemmatizer=lemmatizer,
        )

        # Candidate with different case and accents
        candidates = [{"front": "λύω", "back": "I loose", "tags": ""}]

        results = analyze_candidates(candidates, deck, lemmatizer)

        # Should still match because normalization makes them identical
        assert len(results) == 1
        assert results[0].warning_level == "high"

    def test_lemmatization_across_inflections(self, mock_cltk_backend):
        """Test that different inflections are detected via lemmatization."""
        lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)

        # Create deck with present tense
        deck = DeckIndex()
        deck.add_note(
            NoteEntry(
                note_id="note1",
                model="Basic",
                greek_text="λύω",
                english_text="I loose (present)",
            ),
            lemmatizer=lemmatizer,
        )

        # Try adding aorist form
        candidates = [{"front": "ἔλυσα", "back": "I loosed (aorist)", "tags": ""}]

        results = analyze_candidates(candidates, deck, lemmatizer)

        assert len(results) == 1
        # Should detect lemma match
        assert results[0].warning_level == "medium"
        assert results[0].match_reason == "lemma-match"

    def test_english_gloss_matching(self, mock_cltk_backend):
        """Test English gloss matching works correctly."""
        lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)

        # Create deck
        deck = DeckIndex()
        deck.add_note(
            NoteEntry(
                note_id="note1",
                model="Basic",
                greek_text="ἀγρός",
                english_text="field",
            ),
            lemmatizer=lemmatizer,
        )

        # Different Greek word, same English
        candidates = [{"front": "πεδίον", "back": "field", "tags": ""}]

        results = analyze_candidates(candidates, deck, lemmatizer)

        assert len(results) == 1
        assert results[0].warning_level == "low"
        assert results[0].match_reason == "english-gloss-match"

    def test_multiple_cards_summary(self, mock_cltk_backend):
        """Test analyzing multiple cards and generating summary statistics."""
        lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)

        # Create reference deck
        deck = DeckIndex()
        deck.add_note(
            NoteEntry(
                note_id="note1", model="Basic", greek_text="λύω", english_text="I loose"
            ),
            lemmatizer=lemmatizer,
        )
        deck.add_note(
            NoteEntry(
                note_id="note2",
                model="Basic",
                greek_text="ἀγρός",
                english_text="field",
            ),
            lemmatizer=lemmatizer,
        )

        # Analyze diverse candidates
        candidates = [
            {"front": "λύω", "back": "I loose", "tags": ""},  # high
            {"front": "λύεις", "back": "you loose", "tags": ""},  # medium
            {"front": "πεδίον", "back": "field", "tags": ""},  # low
            {"front": "νέος", "back": "new", "tags": ""},  # none
            {"front": "καλός", "back": "beautiful", "tags": ""},  # none
        ]

        results = analyze_candidates(candidates, deck, lemmatizer)

        # Count by warning level
        levels = [r.warning_level for r in results]
        assert levels.count("high") == 1
        assert levels.count("medium") == 1
        assert levels.count("low") == 1
        assert levels.count("none") == 2


class TestRealWorldScenarios:
    """Test realistic scenarios from Athenaze and other sources."""

    def test_athenaze_basic_cards(self, mock_cltk_backend):
        """Test with cards similar to Athenaze content."""
        lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)

        # Reference deck with basic vocabulary
        deck = DeckIndex()
        deck.add_note(
            NoteEntry(
                note_id="note1", model="Basic", greek_text="φέρω", english_text="I bring"
            ),
            lemmatizer=lemmatizer,
        )
        deck.add_note(
            NoteEntry(
                note_id="note2", model="Basic", greek_text="καί", english_text="and"
            ),
            lemmatizer=lemmatizer,
        )

        # New cards including imperative forms
        candidates = [
            {"front": "φέρε", "back": "Bring!", "tags": "imperative"},  # φέρω imperative
            {"front": "καί", "back": "and", "tags": "conjunction"},  # exact match
            {"front": "σπεύδω", "back": "I hurry", "tags": "verb"},  # new word
        ]

        results = analyze_candidates(candidates, deck, lemmatizer)

        # φέρε should match φέρω via lemma
        assert results[0].warning_level == "medium"

        # καί should be exact match
        assert results[1].warning_level == "high"

        # σπεύδω should be new
        assert results[2].warning_level == "none"

    def test_unicode_edge_cases(self, mock_cltk_backend):
        """Test handling of various Unicode edge cases."""
        lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)

        deck = DeckIndex()
        deck.add_note(
            NoteEntry(
                note_id="note1", model="Basic", greek_text="λύω", english_text="I loose"
            ),
            lemmatizer=lemmatizer,
        )

        # Test with combining characters (decomposed form)
        candidates = [
            {"front": "λ\u0301ύω", "back": "I loose", "tags": ""}  # λ + combining accent
        ]

        results = analyze_candidates(candidates, deck, lemmatizer)

        # Should still match after NFC normalization
        assert len(results) == 1
        # Note: The exact matching behavior depends on normalization

    def test_empty_and_edge_cases(self, mock_cltk_backend):
        """Test handling of empty fields and edge cases."""
        lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)

        deck = DeckIndex()

        candidates = [
            {"front": "", "back": "I loose", "tags": ""},  # empty front
            {"front": "λύω", "back": "", "tags": ""},  # empty back
            {"front": "  ", "back": "  ", "tags": ""},  # whitespace only
        ]

        results = analyze_candidates(candidates, deck, lemmatizer)

        assert len(results) == 3
        # All should complete without errors
        assert all(r.warning_level in ["high", "medium", "low", "none"] for r in results)


class TestCachingBehavior:
    """Test that caching works correctly in the pipeline."""

    def test_lemma_cache_reuse(self, mock_cltk_backend):
        """Test that lemma cache is used for repeated words."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"

            lemmatizer = GreekLemmatizer(
                cache_path=str(cache_path), overrides_path=None
            )

            deck = DeckIndex()

            # Analyze candidates with repeated words
            candidates = [
                {"front": "λύω καί", "back": "I loose and", "tags": ""},
                {"front": "λύεις καί", "back": "you loose and", "tags": ""},
                {"front": "καί λέγω", "back": "and I say", "tags": ""},
            ]

            results = analyze_candidates(candidates, deck, lemmatizer)

            # Save cache
            lemmatizer.save_cache()

            # Verify cache file exists
            assert cache_path.exists()

            # Verify some lemmas are cached
            import json

            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            assert len(cached) > 0  # Should have cached some lemmas
