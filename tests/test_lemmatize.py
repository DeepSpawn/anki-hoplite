"""Tests for lemmatization functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anki_hoplite.lemmatize import GreekLemmatizer, LemmaResult


class MockBackoffLemmatizer:
    """Mock CLTK BackoffGreekLemmatizer for testing."""

    def __init__(self):
        self.lemma_map = {
            "λύω": "λύω",
            "λύεις": "λύω",
            "λύει": "λύω",
            "ἔλυσα": "λύω",
            "ἐλύσαμεν": "λύω",
            "λέγω": "λέγω",
            "λέγει": "λέγει",  # Intentionally different to test edge cases
            "εἶπον": "εἶπον",
            "καί": "καί",
            "δέ": "δέ",
        }

    def lemmatize(self, tokens):
        """Mock lemmatize method that returns list of (token, lemma) tuples."""
        results = []
        for token in tokens:
            lemma = self.lemma_map.get(token, token)
            results.append((token, lemma))
        return results


class TestGreekLemmatizerInit:
    """Test GreekLemmatizer initialization."""

    def test_init_default_paths(self):
        """Test initialization with default paths."""
        lem = GreekLemmatizer()
        assert lem._cache_path == Path("out/lemma_cache.json")
        assert lem._overrides_path == Path("resources/lemma_overrides.json")

    def test_init_custom_paths(self):
        """Test initialization with custom paths."""
        lem = GreekLemmatizer(
            cache_path="custom/cache.json", overrides_path="custom/overrides.json"
        )
        assert lem._cache_path == Path("custom/cache.json")
        assert lem._overrides_path == Path("custom/overrides.json")

    def test_init_none_paths(self):
        """Test initialization with None paths (disables caching)."""
        lem = GreekLemmatizer(cache_path=None, overrides_path=None)
        assert lem._cache_path is None
        assert lem._overrides_path is None

    def test_load_existing_cache(self):
        """Test that existing cache is loaded on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache_data = {"λυω": "λυω", "και": "και"}
            cache_path.write_text(json.dumps(cache_data), encoding="utf-8")

            lem = GreekLemmatizer(cache_path=str(cache_path), overrides_path=None)
            assert lem._cache == cache_data

    def test_load_existing_overrides(self):
        """Test that existing overrides are loaded on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            overrides_path = Path(tmpdir) / "overrides.json"
            override_data = {"ειπον": "λεγω"}  # εἶπον -> λέγω
            overrides_path.write_text(json.dumps(override_data), encoding="utf-8")

            lem = GreekLemmatizer(cache_path=None, overrides_path=str(overrides_path))
            assert lem._overrides == override_data


class TestGreekLemmatizerBackend:
    """Test CLTK backend initialization."""

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_backend_lazy_initialization(self, mock_lemmatizer_class):
        """Test that backend is initialized lazily."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        lem = GreekLemmatizer(cache_path=None, overrides_path=None)
        assert lem._backend is None  # Not initialized yet

        # Trigger backend initialization
        lem._ensure_backend()
        assert lem._backend is not None
        mock_lemmatizer_class.assert_called_once()

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_backend_initialization_only_once(self, mock_lemmatizer_class):
        """Test that backend is only initialized once."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        lem = GreekLemmatizer(cache_path=None, overrides_path=None)
        lem._ensure_backend()
        lem._ensure_backend()
        lem._ensure_backend()

        # Should only be called once despite multiple _ensure_backend calls
        assert mock_lemmatizer_class.call_count == 1

    def test_backend_name_with_backoff(self):
        """Test backend_name returns correct name for BackoffLemmatizer."""
        with patch(
            "cltk.lemmatize.GreekBackoffLemmatizer"
        ) as mock_lemmatizer_class:
            mock_backend = MockBackoffLemmatizer()
            # Override the class name to match what the backend expects
            mock_backend.__class__.__name__ = "GreekBackoffLemmatizer"
            mock_lemmatizer_class.return_value = mock_backend

            lem = GreekLemmatizer(cache_path=None, overrides_path=None)
            name = lem.backend_name()
            assert name == "cltk-backoff"

    def test_backend_name_fallback(self):
        """Test backend_name returns 'fallback' when backend is None."""
        with patch(
            "cltk.lemmatize.GreekBackoffLemmatizer", side_effect=Exception("No CLTK")
        ):
            with patch("cltk.NLP", side_effect=Exception("No NLP")):
                lem = GreekLemmatizer(cache_path=None, overrides_path=None)
                name = lem.backend_name()
                assert name == "fallback"


class TestLemmatizeToken:
    """Test single token lemmatization."""

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_lemmatize_token_basic(self, mock_lemmatizer_class):
        """Test basic token lemmatization."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        lem = GreekLemmatizer(cache_path=None, overrides_path=None)
        result = lem.lemmatize_token("λύω")
        assert result == "λυω"  # normalized (no accent)

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_lemmatize_inflected_forms(self, mock_lemmatizer_class):
        """Test lemmatization of different inflected forms."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        lem = GreekLemmatizer(cache_path=None, overrides_path=None)

        # All should lemmatize to λυω (normalized)
        assert lem.lemmatize_token("λύω") == "λυω"
        assert lem.lemmatize_token("λύεις") == "λυω"
        assert lem.lemmatize_token("λύει") == "λυω"
        assert lem.lemmatize_token("ἔλυσα") == "λυω"
        assert lem.lemmatize_token("ἐλύσαμεν") == "λυω"

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_lemmatize_empty_token(self, mock_lemmatizer_class):
        """Test lemmatization of empty token."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        lem = GreekLemmatizer(cache_path=None, overrides_path=None)
        result = lem.lemmatize_token("")
        assert result == ""

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_lemmatize_with_cache(self, mock_lemmatizer_class):
        """Test that cache is used for repeated tokens."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        lem = GreekLemmatizer(cache_path=None, overrides_path=None)

        # First call should lemmatize
        result1 = lem.lemmatize_token("λύω")
        assert result1 == "λυω"

        # Second call should use lru_cache and return same result
        result2 = lem.lemmatize_token("λύω")
        assert result2 == "λυω"
        assert result1 == result2

    def test_lemmatize_with_overrides(self):
        """Test that overrides take precedence over backend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            overrides_path = Path(tmpdir) / "overrides.json"
            override_data = {"ειπον": "λεγω"}  # εἶπον should map to λέγω
            overrides_path.write_text(json.dumps(override_data), encoding="utf-8")

            with patch("cltk.lemmatize.GreekBackoffLemmatizer") as mock_class:
                mock_backend = MockBackoffLemmatizer()
                mock_class.return_value = mock_backend

                lem = GreekLemmatizer(cache_path=None, overrides_path=str(overrides_path))
                result = lem.lemmatize_token("εἶπον")
                # Should use override, not backend
                assert result == "λεγω"

    def test_lemmatize_fallback_without_backend(self):
        """Test fallback behavior when CLTK is not available."""
        with patch(
            "cltk.lemmatize.GreekBackoffLemmatizer", side_effect=Exception("No CLTK")
        ):
            with patch("cltk.NLP", side_effect=Exception("No NLP")):
                lem = GreekLemmatizer(cache_path=None, overrides_path=None)
                # Should fall back to returning normalized token
                result = lem.lemmatize_token("λύω")
                assert result == "λυω"  # Just normalized, not lemmatized


class TestLemmatizeText:
    """Test full text lemmatization."""

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_lemmatize_multiple_tokens(self, mock_lemmatizer_class):
        """Test lemmatization of text with multiple tokens."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        lem = GreekLemmatizer(cache_path=None, overrides_path=None)
        results = lem.lemmatize("λύω καί")

        assert len(results) == 2
        assert isinstance(results[0], LemmaResult)
        assert results[0].token == "λύω"
        assert results[0].lemma == "λυω"
        assert results[1].token == "καί"
        assert results[1].lemma == "και"

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_lemmatize_empty_text(self, mock_lemmatizer_class):
        """Test lemmatization of empty text."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        lem = GreekLemmatizer(cache_path=None, overrides_path=None)
        results = lem.lemmatize("")
        assert results == []

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_best_lemma_picks_first_greek_token(self, mock_lemmatizer_class):
        """Test that best_lemma picks the first Greek token."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        lem = GreekLemmatizer(cache_path=None, overrides_path=None)
        result = lem.best_lemma("λύω καί δέ")
        # Should pick first token's lemma
        assert result == "λυω"

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_best_lemma_with_punctuation(self, mock_lemmatizer_class):
        """Test best_lemma strips punctuation from tokens."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        lem = GreekLemmatizer(cache_path=None, overrides_path=None)
        result = lem.best_lemma("λύω, καί")
        # Should strip comma and return lemma of λύω
        assert result == "λυω"


class TestCachePersistence:
    """Test cache saving and loading."""

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_save_cache(self, mock_lemmatizer_class):
        """Test that cache is saved correctly."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"

            lem = GreekLemmatizer(cache_path=str(cache_path), overrides_path=None)

            # Lemmatize some tokens to populate cache
            lem.lemmatize_token("λύω")
            lem.lemmatize_token("καί")

            # Save cache
            lem.save_cache()

            # Verify cache file was created
            assert cache_path.exists()

            # Verify contents
            saved_data = json.loads(cache_path.read_text(encoding="utf-8"))
            assert "λυω" in saved_data
            assert "και" in saved_data

    def test_save_cache_with_none_path(self):
        """Test that save_cache does nothing when cache_path is None."""
        lem = GreekLemmatizer(cache_path=None, overrides_path=None)
        # Should not raise an error
        lem.save_cache()

    @patch("cltk.lemmatize.GreekBackoffLemmatizer")
    def test_cache_persistence_across_instances(self, mock_lemmatizer_class):
        """Test that cache persists across GreekLemmatizer instances."""
        mock_backend = MockBackoffLemmatizer()
        mock_lemmatizer_class.return_value = mock_backend

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"

            # First instance: populate and save cache
            lem1 = GreekLemmatizer(cache_path=str(cache_path), overrides_path=None)
            lem1.lemmatize_token("λύω")
            lem1.save_cache()

            # Second instance: should load existing cache
            lem2 = GreekLemmatizer(cache_path=str(cache_path), overrides_path=None)
            assert "λυω" in lem2._cache
            assert lem2._cache["λυω"] == "λυω"
