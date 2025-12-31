"""Tests for cloze context validation functionality."""

import tempfile
from pathlib import Path

import pytest
from anki_hoplite.cloze_validator import (
    GreekStopWords,
    ClozeSegment,
    ClozeParseResult,
    ClozeAnalysis,
    parse_cloze_syntax,
    tokenize_greek,
    count_stop_words,
    classify_quality,
    analyze_cloze_card,
    strip_html_tags,
    strip_sound_tags,
    is_pure_punctuation,
)


class TestHelperFunctions:
    """Test helper functions for text cleaning."""

    def test_strip_html_tags(self):
        """Test HTML tag removal."""
        assert strip_html_tags("<div>λόγος</div>") == "λόγος"
        assert strip_html_tags("<b>test</b> <i>text</i>") == "test text"
        assert strip_html_tags("plain text") == "plain text"
        assert strip_html_tags("") == ""

    def test_strip_sound_tags(self):
        """Test sound tag removal."""
        assert strip_sound_tags("χαῖρε[sound:rec123.mp3]") == "χαῖρε"
        assert strip_sound_tags("[sound:test.mp3]λόγος") == "λόγος"
        assert strip_sound_tags("plain text") == "plain text"
        assert strip_sound_tags("") == ""

    def test_is_pure_punctuation(self):
        """Test punctuation detection."""
        assert is_pure_punctuation(".")
        assert is_pure_punctuation(",")
        assert is_pure_punctuation("...")
        assert is_pure_punctuation("·")
        assert not is_pure_punctuation("λόγος")
        assert not is_pure_punctuation("λ.")
        assert is_pure_punctuation("")


class TestClozeParser:
    """Test cloze syntax parsing functionality."""

    def test_parse_single_deletion(self):
        """Parse simple single deletion."""
        text = "{{c1::λόγος}} ἐστίν"
        result = parse_cloze_syntax(text)
        assert result.is_cloze
        assert len(result.segments) == 1
        assert result.segments[0].number == 1
        assert result.segments[0].content == "λόγος"
        assert result.segments[0].hint == ""
        assert " ἐστίν" in result.context_text

    def test_parse_deletion_with_hint(self):
        """Parse deletion with hint text."""
        text = "ὁ οἶκος {{c1::τοῦ πατρός::gen. of πατήρ}} ἐστίν"
        result = parse_cloze_syntax(text)
        assert result.is_cloze
        assert len(result.segments) == 1
        assert result.segments[0].content == "τοῦ πατρός"
        assert result.segments[0].hint == "gen. of πατήρ"

    def test_parse_multiple_deletions(self):
        """Parse card with multiple cloze deletions."""
        text = "{{c1::πρῶτον}} γράμμα ἐστίν Α, {{c2::δεύτερον}} Β"
        result = parse_cloze_syntax(text)
        assert result.is_cloze
        assert len(result.segments) == 2
        assert result.segments[0].number == 1
        assert result.segments[0].content == "πρῶτον"
        assert result.segments[1].number == 2
        assert result.segments[1].content == "δεύτερον"
        assert " γράμμα ἐστίν Α,  Β" in result.context_text

    def test_parse_non_cloze_card(self):
        """Detect non-cloze cards."""
        text = "λόγος ἐστίν"
        result = parse_cloze_syntax(text)
        assert not result.is_cloze
        assert len(result.segments) == 0
        # Context should be the original text (with HTML/sound stripped)
        assert result.context_text == text

    def test_parse_with_html_tags(self):
        """Parse cloze with HTML tags."""
        text = "<div>{{c1::καθίζει}} οὖν ὑπὸ τῷ δένδρῳ</div>"
        result = parse_cloze_syntax(text)
        assert result.is_cloze
        assert len(result.segments) == 1
        assert result.segments[0].content == "καθίζει"
        # HTML should be stripped from context
        assert "<div>" not in result.context_text
        assert "</div>" not in result.context_text

    def test_parse_with_sound_tags(self):
        """Parse cloze with sound tags."""
        text = "{{c1::χαῖρε}}[sound:rec123.mp3]! τί ἀκούεις;"
        result = parse_cloze_syntax(text)
        assert result.is_cloze
        assert len(result.segments) == 1
        assert result.segments[0].content == "χαῖρε"
        # Sound tags should be stripped from context
        assert "[sound:" not in result.context_text

    def test_parse_empty_text(self):
        """Handle empty input."""
        result = parse_cloze_syntax("")
        assert not result.is_cloze
        assert len(result.segments) == 0
        assert result.context_text == ""

    def test_parse_only_cloze_no_context(self):
        """Parse card with no context (entire field is cloze)."""
        text = "{{c1::λόγος}}"
        result = parse_cloze_syntax(text)
        assert result.is_cloze
        assert len(result.segments) == 1
        assert result.segments[0].content == "λόγος"
        # Context should be empty (just the deletion)
        assert result.context_text.strip() == ""

    def test_parse_cloze_with_punctuation_in_hint(self):
        """Parse cloze with punctuation in hint."""
        text = "{{c1::λύω::I loose, I free}}"
        result = parse_cloze_syntax(text)
        assert result.is_cloze
        assert result.segments[0].hint == "I loose, I free"


class TestGreekTokenizer:
    """Test Greek tokenization."""

    def test_tokenize_simple_text(self):
        """Tokenize simple Greek text."""
        text = "ὁ λόγος ἐστίν"
        tokens = tokenize_greek(text)
        assert tokens == ["ὁ", "λόγος", "ἐστίν"]

    def test_tokenize_with_punctuation(self):
        """Filter pure punctuation tokens."""
        text = "λόγος, ἐστίν."
        tokens = tokenize_greek(text)
        # Commas/periods should be filtered as pure punctuation
        assert "," not in tokens
        assert "." not in tokens
        # Words should remain (may have punctuation attached initially, but filtered)
        # Actually, after split, "λόγος," becomes "λόγος," which is not pure punct
        # Let's check what actually happens
        assert "λόγος," in tokens or "λόγος" in tokens

    def test_tokenize_empty_text(self):
        """Handle empty input."""
        assert tokenize_greek("") == []
        assert tokenize_greek("   ") == []

    def test_tokenize_with_html(self):
        """Strip HTML but keep text."""
        text = "<div>ὁ λόγος</div>"
        tokens = tokenize_greek(text)
        assert "ὁ" in tokens
        assert "λόγος" in tokens
        assert "<div>" not in tokens

    def test_tokenize_with_sound_tags(self):
        """Strip sound tags."""
        text = "λόγος[sound:test.mp3]"
        tokens = tokenize_greek(text)
        assert "λόγος" in tokens
        assert "[sound:test.mp3]" not in tokens

    def test_tokenize_filters_standalone_punctuation(self):
        """Standalone punctuation tokens are filtered."""
        text = "λόγος . ἐστίν"
        tokens = tokenize_greek(text)
        assert "." not in tokens
        assert "λόγος" in tokens
        assert "ἐστίν" in tokens

    def test_tokenize_multiple_spaces(self):
        """Handle multiple spaces."""
        text = "λόγος    ἐστίν"
        tokens = tokenize_greek(text)
        assert tokens == ["λόγος", "ἐστίν"]


class TestStopWordDetection:
    """Test stop word counting."""

    def create_test_stopwords(self):
        """Create a test stop words instance."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as f:
            f.write("# Test stop words\n")
            f.write("ο\n")
            f.write("και\n")
            f.write("δε\n")
            f.write("εστιν\n")
            stopwords_path = f.name

        try:
            stopwords = GreekStopWords.load(stopwords_path)
            return stopwords
        finally:
            Path(stopwords_path).unlink()

    def test_load_stopwords_from_file(self):
        """Load stop words from file."""
        stopwords = self.create_test_stopwords()
        assert "ο" in stopwords.words
        assert "και" in stopwords.words
        assert "δε" in stopwords.words
        assert "εστιν" in stopwords.words

    def test_load_stopwords_skips_comments(self):
        """Skip comment lines."""
        stopwords = self.create_test_stopwords()
        assert "# Test stop words" not in stopwords.words

    def test_load_stopwords_missing_file(self):
        """Raise error for missing file."""
        with pytest.raises(FileNotFoundError):
            GreekStopWords.load("/nonexistent/stopwords.txt")

    def test_is_stop_word(self):
        """Correctly identify stop words."""
        stopwords = self.create_test_stopwords()
        assert stopwords.is_stop_word("ο")
        assert stopwords.is_stop_word("και")
        assert not stopwords.is_stop_word("λογος")

    def test_count_stop_words(self):
        """Count stop vs content words."""
        stopwords = self.create_test_stopwords()
        # Note: count_stop_words normalizes tokens, so we use unnormalized input
        tokens = ["ὁ", "λόγος", "καί", "ἐστίν"]
        stop_count, content_count = count_stop_words(tokens, stopwords)
        # ὁ → ο (stop), λόγος → λογος (content), καί → και (stop), ἐστίν → εστιν (stop)
        assert stop_count == 3
        assert content_count == 1

    def test_count_stop_words_empty_list(self):
        """Handle empty token list."""
        stopwords = self.create_test_stopwords()
        stop_count, content_count = count_stop_words([], stopwords)
        assert stop_count == 0
        assert content_count == 0


class TestQualityClassification:
    """Test quality level classification."""

    def test_excellent_quality(self):
        """Classify excellent cloze."""
        # 8 context tokens, 20% deletion, 75% content words
        quality, reasons = classify_quality(
            context_tokens=8,
            deletion_ratio=0.20,
            content_density=0.75
        )
        assert quality == "excellent"
        assert len(reasons) == 0

    def test_excellent_quality_boundary(self):
        """Test boundary for excellent classification."""
        quality, reasons = classify_quality(
            context_tokens=5,
            deletion_ratio=0.50,
            content_density=0.40
        )
        assert quality == "excellent"

    def test_good_quality(self):
        """Classify good cloze."""
        # 4 context tokens, 40% deletion, 50% content words
        quality, reasons = classify_quality(
            context_tokens=4,
            deletion_ratio=0.40,
            content_density=0.50
        )
        assert quality == "good"
        assert len(reasons) == 0

    def test_good_quality_boundary(self):
        """Test boundary for good classification."""
        quality, reasons = classify_quality(
            context_tokens=3,
            deletion_ratio=0.60,
            content_density=0.30
        )
        assert quality == "good"

    def test_weak_quality_low_context(self):
        """Classify weak cloze with low context."""
        quality, reasons = classify_quality(
            context_tokens=2,
            deletion_ratio=0.40,
            content_density=0.60
        )
        assert quality == "weak"
        assert "low_context" in reasons

    def test_weak_quality_high_deletion(self):
        """Classify weak cloze with high deletion."""
        quality, reasons = classify_quality(
            context_tokens=3,
            deletion_ratio=0.70,
            content_density=0.40
        )
        assert quality == "weak"
        assert "high_deletion" in reasons

    def test_weak_quality_low_content_density(self):
        """Classify weak cloze with mostly stop words."""
        quality, reasons = classify_quality(
            context_tokens=3,
            deletion_ratio=0.40,
            content_density=0.15
        )
        assert quality == "weak"
        assert "low_content_density" in reasons

    def test_poor_quality_no_context(self):
        """Classify poor cloze with no context."""
        quality, reasons = classify_quality(
            context_tokens=0,
            deletion_ratio=1.0,
            content_density=0.0
        )
        assert quality == "poor"
        assert "no_context" in reasons

    def test_weak_quality_minimal_context(self):
        """Classify weak cloze with minimal context (1 token, deletion ≤80%)."""
        quality, reasons = classify_quality(
            context_tokens=1,
            deletion_ratio=0.75,
            content_density=0.0
        )
        # This is weak, not poor, per classification rules:
        # weak if context ≥1 AND deletion ≤80%
        assert quality == "weak"
        assert "low_context" in reasons

    def test_poor_quality_very_high_deletion(self):
        """Classify poor cloze with very high deletion."""
        quality, reasons = classify_quality(
            context_tokens=1,
            deletion_ratio=0.90,
            content_density=0.0
        )
        assert quality == "poor"
        assert "very_high_deletion" in reasons

    def test_weak_quality_all_stop_words(self):
        """Classify weak cloze with all stop words in context."""
        quality, reasons = classify_quality(
            context_tokens=2,
            deletion_ratio=0.40,
            content_density=0.0  # All stop words
        )
        # This is weak, not poor, per classification rules:
        # weak if context ≥2 tokens
        assert quality == "weak"
        assert "low_content_density" in reasons


class TestClozeAnalysis:
    """Test end-to-end cloze analysis."""

    def create_test_stopwords(self):
        """Create a test stop words instance."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as f:
            # Common Greek stop words (normalized: no accents, lowercase)
            f.write("ο\n")
            f.write("η\n")
            f.write("το\n")
            f.write("και\n")
            f.write("δε\n")
            f.write("εστιν\n")
            f.write("ειμι\n")
            stopwords_path = f.name

        try:
            stopwords = GreekStopWords.load(stopwords_path)
            return stopwords
        finally:
            Path(stopwords_path).unlink()

    def test_analyze_good_cloze(self):
        """Analyze well-designed cloze card."""
        front = "ὁ Δικαιόπολις {{c1::Ἀθηναῖός}} ἐστιν"
        stopwords = self.create_test_stopwords()
        analysis = analyze_cloze_card(front, stopwords)

        assert analysis.is_cloze
        assert analysis.quality_level in ("excellent", "good")
        assert analysis.context_tokens >= 3  # "ὁ Δικαιόπολις ἐστιν"
        assert analysis.cloze_tokens == 1  # "Ἀθηναῖός"
        assert analysis.deletion_ratio < 0.5

    def test_analyze_poor_cloze_no_context(self):
        """Analyze poorly-designed cloze (minimal context)."""
        front = "{{c1::λόγος}}"
        stopwords = self.create_test_stopwords()
        analysis = analyze_cloze_card(front, stopwords)

        assert analysis.is_cloze
        assert analysis.quality_level == "poor"
        assert analysis.context_tokens == 0
        assert "no_context" in analysis.quality_reasons

    def test_analyze_non_cloze(self):
        """Analyze non-cloze card."""
        front = "λόγος"
        stopwords = self.create_test_stopwords()
        analysis = analyze_cloze_card(front, stopwords)

        assert not analysis.is_cloze
        assert analysis.quality_level == "n/a"
        assert analysis.total_tokens == 0
        assert analysis.context_tokens == 0

    def test_analyze_multi_deletion(self):
        """Analyze card with multiple deletions."""
        front = "{{c1::πρῶτον}} γράμμα ἐστίν Α, {{c2::δεύτερον}} Β"
        stopwords = self.create_test_stopwords()
        analysis = analyze_cloze_card(front, stopwords)

        assert analysis.is_cloze
        assert analysis.cloze_tokens == 2  # "πρῶτον", "δεύτερον"
        assert analysis.context_tokens >= 3  # "γράμμα ἐστίν Α Β"

    def test_analyze_cloze_with_html(self):
        """Analyze cloze with HTML tags."""
        front = "<div>ὁ {{c1::λόγος}} ἐστιν</div>"
        stopwords = self.create_test_stopwords()
        analysis = analyze_cloze_card(front, stopwords)

        assert analysis.is_cloze
        # HTML should be stripped, leaving "ὁ ἐστιν" as context
        assert analysis.context_tokens == 2

    def test_analyze_cloze_with_sound_tags(self):
        """Analyze cloze with sound tags."""
        front = "{{c1::χαῖρε}}[sound:test.mp3] φίλε"
        stopwords = self.create_test_stopwords()
        analysis = analyze_cloze_card(front, stopwords)

        assert analysis.is_cloze
        # Sound tag should be stripped
        assert analysis.context_tokens == 1  # "φίλε"

    def test_analyze_cloze_all_stop_words(self):
        """Analyze cloze with only stop words in context."""
        front = "ὁ δέ {{c1::καί}}"
        stopwords = self.create_test_stopwords()
        analysis = analyze_cloze_card(front, stopwords)

        assert analysis.is_cloze
        # All context words are stop words
        assert analysis.context_stop_words == 2
        assert analysis.context_content_words == 0
        assert analysis.content_word_density == 0.0
        # Per classification rules: context ≥2 tokens → weak (not poor)
        assert analysis.quality_level == "weak"
        assert "low_content_density" in analysis.quality_reasons

    def test_analyze_excellent_cloze(self):
        """Analyze excellent quality cloze."""
        # Long sentence with good context
        front = "ὁ Δικαιόπολις πονεῖ ἐν τοῖς ἀγροῖς καὶ {{c1::γεωργεῖ}} τὸν κλῆρον"
        stopwords = self.create_test_stopwords()
        analysis = analyze_cloze_card(front, stopwords)

        assert analysis.is_cloze
        assert analysis.context_tokens >= 7
        assert analysis.deletion_ratio <= 0.50
        # Should have good content words: Δικαιόπολις, πονεῖ, ἀγροῖς, κλῆρον
        assert analysis.context_content_words >= 4
        # Quality should be excellent or good
        assert analysis.quality_level in ("excellent", "good")

    def test_analyze_empty_front(self):
        """Handle empty front field."""
        front = ""
        stopwords = self.create_test_stopwords()
        analysis = analyze_cloze_card(front, stopwords)

        assert not analysis.is_cloze
        assert analysis.quality_level == "n/a"
