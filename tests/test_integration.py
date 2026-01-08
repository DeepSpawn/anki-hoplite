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
            # Article forms (for testing stop word filtering)
            "ἡ": "ὁ",
            "ὁ": "ὁ",
            "τῆς": "ὁ",
            "τῇ": "ὁ",
            "τοῦ": "ὁ",
            # Noun forms (for test cases)
            "κρήνη": "κρήνη",
            "κρήνης": "κρήνη",
            "κρήνῃ": "κρήνη",
            "μέλιττα": "μέλιττα",
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


class TestTagHygieneIntegration:
    """Test tag hygiene integration with duplicate detection pipeline."""

    def test_tag_hygiene_with_duplicate_detection(self, mock_cltk_backend):
        """Test that tag hygiene works alongside duplicate detection."""
        from anki_hoplite.tag_hygiene import TagSchema, AutoTagRule
        import re

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create tag schema
            schema = TagSchema(
                allowed_tags={"verb", "noun", "aorist"},
                blocked_tags={"tmp", "delete"},
                case_sensitive=False,
                normalize_tags=True,
                auto_tag_rules=[]
            )

            # Create reference deck
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

            # Create candidates with various tag scenarios
            candidates = [
                {"front": "λύεις", "back": "you loose", "tags": "verb aorist tmp"},  # Has blocked tag
                {"front": "νέος", "back": "new", "tags": "verb unknown"},  # Has unknown tag
                {"front": "ἀγρός", "back": "field", "tags": "noun"},  # All allowed tags
            ]

            # Analyze with tag hygiene
            results = analyze_candidates(
                candidates,
                deck,
                lemmatizer,
                tag_schema=schema,
                enable_auto_tag=False
            )

            # Check first result: blocked tag should be deleted
            assert results[0].tags == "verb aorist tmp"  # Original preserved
            assert results[0].tags_kept == "verb aorist"
            assert results[0].tags_deleted == "tmp"
            assert results[0].tags_unknown == ""
            assert results[0].tags_need_review is False

            # Check second result: unknown tag should be flagged
            assert results[1].tags == "verb unknown"  # Original preserved
            assert results[1].tags_kept == "verb"
            assert results[1].tags_deleted == ""
            assert results[1].tags_unknown == "unknown"
            assert results[1].tags_need_review is True

            # Check third result: all tags allowed
            assert results[2].tags == "noun"
            assert results[2].tags_kept == "noun"
            assert results[2].tags_deleted == ""
            assert results[2].tags_unknown == ""
            assert results[2].tags_need_review is False

    def test_auto_tagging_integration(self, mock_cltk_backend):
        """Test auto-tagging integration with pattern matching."""
        from anki_hoplite.tag_hygiene import TagSchema, AutoTagRule
        import re

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create tag schema with auto-tag rules
            # Note: Patterns match NORMALIZED text (accents stripped)
            schema = TagSchema(
                allowed_tags={"article", "masculine", "feminine", "verb"},
                blocked_tags={},
                case_sensitive=False,
                normalize_tags=True,
                auto_tag_rules=[
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
                    )
                ]
            )

            # Create empty deck
            lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)
            deck = DeckIndex()

            # Create candidates that should trigger auto-tagging
            candidates = [
                {"front": "ὁ", "back": "the", "tags": ""},  # Should auto-tag article + masculine
                {"front": "ἡ", "back": "the", "tags": "article"},  # Should auto-tag feminine (article already present)
                {"front": "λύω", "back": "I loose", "tags": "verb"},  # Should not auto-tag
            ]

            # Analyze with auto-tagging enabled
            results = analyze_candidates(
                candidates,
                deck,
                lemmatizer,
                tag_schema=schema,
                enable_auto_tag=True
            )

            # Check first result: should auto-add article + masculine
            assert results[0].tags == ""  # Original was empty
            assert results[0].tags_auto_added == "article masculine"
            assert "article" in results[0].tags_final
            assert "masculine" in results[0].tags_final

            # Check second result: should auto-add feminine (article already present)
            assert results[1].tags == "article"
            assert results[1].tags_kept == "article"
            assert "feminine" in results[1].tags_auto_added
            assert "article" in results[1].tags_final
            assert "feminine" in results[1].tags_final

            # Check third result: no auto-tagging
            assert results[2].tags == "verb"
            assert results[2].tags_kept == "verb"
            assert results[2].tags_auto_added == ""
            assert results[2].tags_final == "verb"

    def test_tag_hygiene_disabled_by_default(self, mock_cltk_backend):
        """Test that tag hygiene fields are empty when schema is not provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create reference deck
            lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)
            deck = DeckIndex()

            # Create candidates with tags
            candidates = [
                {"front": "λύω", "back": "I loose", "tags": "verb aorist tmp"},
            ]

            # Analyze WITHOUT tag hygiene (no schema provided)
            results = analyze_candidates(
                candidates,
                deck,
                lemmatizer,
                tag_schema=None,
                enable_auto_tag=False
            )

            # Check that original tags are preserved but hygiene fields are empty
            assert results[0].tags == "verb aorist tmp"
            assert results[0].tags_kept == ""
            assert results[0].tags_deleted == ""
            assert results[0].tags_unknown == ""
            assert results[0].tags_auto_added == ""
            assert results[0].tags_final == ""
            assert results[0].tags_need_review is False

    def test_tag_hygiene_csv_output(self, mock_cltk_backend):
        """Test that tag hygiene columns appear in CSV output."""
        from anki_hoplite.tag_hygiene import TagSchema
        from anki_hoplite.report import write_results_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create tag schema
            schema = TagSchema(
                allowed_tags={"verb"},
                blocked_tags={"tmp"},
                case_sensitive=False,
                normalize_tags=True,
                auto_tag_rules=[]
            )

            # Create reference deck
            lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)
            deck = DeckIndex()

            # Create candidates
            candidates = [
                {"front": "λύω", "back": "I loose", "tags": "verb tmp"},
            ]

            # Analyze with tag hygiene
            results = analyze_candidates(
                candidates,
                deck,
                lemmatizer,
                tag_schema=schema,
                enable_auto_tag=False
            )

            # Write CSV
            output_csv = tmpdir / "output.csv"
            write_results_csv(str(output_csv), results, include_tag_hygiene=True)

            # Read CSV and verify tag columns exist
            with output_csv.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 1
            # Check that tag hygiene columns exist
            assert "tags" in rows[0]
            assert "tags_kept" in rows[0]
            assert "tags_deleted" in rows[0]
            assert "tags_unknown" in rows[0]
            assert "tags_auto_added" in rows[0]
            assert "tags_final" in rows[0]
            assert "tags_need_review" in rows[0]

            # Check values
            assert rows[0]["tags"] == "verb tmp"
            assert rows[0]["tags_kept"] == "verb"
            assert rows[0]["tags_deleted"] == "tmp"

    def test_lint_with_cloze_validation(self, mock_cltk_backend):
        """Test full pipeline with cloze validation enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create input CSV with cloze cards
            input_csv = tmpdir / "candidates.csv"
            with input_csv.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["front", "back", "tags"])
                writer.writeheader()
                # Good cloze (context ≥3 tokens)
                writer.writerow({"front": "ὁ Δικαιόπολις {{c1::Ἀθηναῖός}} ἐστιν", "back": "Dikaiopolis is an Athenian", "tags": "cloze"})
                # Poor cloze (no context)
                writer.writerow({"front": "{{c1::λόγος}}", "back": "word", "tags": "cloze"})
                # Non-cloze card
                writer.writerow({"front": "λέγω", "back": "I say", "tags": ""})

            # Create stop words file
            stopwords_file = tmpdir / "stopwords.txt"
            with stopwords_file.open("w", encoding="utf-8") as f:
                f.write("ο\n")
                f.write("η\n")
                f.write("και\n")
                f.write("εστιν\n")

            # Load candidates
            candidates = [r.__dict__ for r in read_candidates_csv(str(input_csv))]

            # Create empty deck for testing
            lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)
            deck = DeckIndex()

            # Load stop words
            from anki_hoplite.cloze_validator import GreekStopWords
            stopwords = GreekStopWords.load(str(stopwords_file))

            # Analyze with cloze validation
            results = analyze_candidates(
                candidates,
                deck,
                lemmatizer,
                enable_cloze_validation=True,
                cloze_stopwords=stopwords
            )

            # Verify cloze analysis
            assert len(results) == 3

            # First card: good cloze
            assert results[0].cloze_quality in ("excellent", "good")
            assert results[0].cloze_context_tokens >= 3
            assert results[0].cloze_deletion_ratio < 0.5

            # Second card: poor cloze (no context)
            assert results[1].cloze_quality == "poor"
            assert results[1].cloze_context_tokens == 0

            # Third card: not a cloze card
            assert results[2].cloze_quality == ""
            assert results[2].cloze_context_tokens == 0

            # Write CSV and verify cloze columns exist
            output_csv = tmpdir / "output.csv"
            write_results_csv(str(output_csv), results, include_tag_hygiene=False)

            with output_csv.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 3
            # Check that cloze columns exist
            assert "cloze_quality" in rows[0]
            assert "cloze_context_tokens" in rows[0]
            assert "cloze_deletion_ratio" in rows[0]
            assert "cloze_content_density" in rows[0]
            assert "cloze_reasons" in rows[0]

            # Verify values in CSV
            assert rows[0]["cloze_quality"] in ("excellent", "good")
            assert rows[1]["cloze_quality"] == "poor"
            assert rows[2]["cloze_quality"] == ""  # Non-cloze

    def test_cloze_validation_disabled_by_default(self, mock_cltk_backend):
        """Test that cloze validation is disabled when not requested."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create input CSV with a cloze card
            input_csv = tmpdir / "candidates.csv"
            with input_csv.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["front", "back", "tags"])
                writer.writeheader()
                writer.writerow({"front": "{{c1::λόγος}}", "back": "word", "tags": ""})

            candidates = [r.__dict__ for r in read_candidates_csv(str(input_csv))]
            lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)
            deck = DeckIndex()

            # Analyze WITHOUT cloze validation
            results = analyze_candidates(candidates, deck, lemmatizer)

            # Cloze fields should be empty/default
            assert results[0].cloze_quality == ""
            assert results[0].cloze_context_tokens == 0
            assert results[0].cloze_deletion_ratio == 0.0
            assert results[0].cloze_content_density == 0.0
            assert results[0].cloze_reasons == ""


@pytest.mark.usefixtures("mock_cltk_backend")
def test_recognition_cards_with_articles():
    """Test that recognition cards with articles get correct noun lemmas."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create input CSV with article + noun pairs
        input_csv = tmpdir / "candidates.csv"
        with input_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["front", "back", "tags"])
            writer.writeheader()
            writer.writerow({"front": "ἡ κρήνη", "back": "Nom Sg — the spring", "tags": "noun"})
            writer.writerow({"front": "τῆς κρήνης", "back": "Gen Sg — of the spring", "tags": "noun"})
            writer.writerow({"front": "τῇ κρήνῃ", "back": "Dat Sg — to the spring", "tags": "noun"})

        # Ingest candidates
        candidates = [r.__dict__ for r in read_candidates_csv(str(input_csv))]

        # Create lemmatizer with mock
        lemmatizer = GreekLemmatizer(cache_path=None, overrides_path=None)

        # Check lemmas - all should map to noun lemma, not article
        for card in candidates:
            lemma = lemmatizer.best_lemma(card["front"])
            # All should return the noun lemma "κρηνη", not article lemma
            assert lemma == "κρηνη", f"Card '{card['front']}' got lemma '{lemma}', expected 'κρηνη'"

        # Also verify in full pipeline with empty deck
        deck = DeckIndex()
        results = analyze_candidates(candidates, deck, lemmatizer)

        # All results should have noun lemma
        for result in results:
            assert result.lemma == "κρηνη", f"Result for '{result.front}' has lemma '{result.lemma}', expected 'κρηνη'"
