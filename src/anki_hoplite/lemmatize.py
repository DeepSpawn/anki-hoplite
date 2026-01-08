"""CLTK-backed lemmatization wrapper with graceful fallback.

The real implementation will use CLTK for Ancient Greek and cache results.
For scaffolding, we implement a lazy import and a simple fallback that returns
the normalized token itself when CLTK is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional
import json
from pathlib import Path
import unicodedata as ud

from .normalize import normalize_greek_for_match
from .cltk_setup import ensure_cltk_grc_models
from .cloze_validator import GreekStopWords


@dataclass
class LemmaResult:
    token: str
    lemma: str


class GreekLemmatizer:
    def __init__(
        self,
        cache_path: Optional[str] = "out/lemma_cache.json",
        overrides_path: Optional[str] = "resources/lemma_overrides.json",
        stopwords_path: Optional[str] = "resources/greek_stopwords.txt",
    ) -> None:
        self._backend = None  # lazy init
        self._cache_path = Path(cache_path) if cache_path else None
        self._cache: dict[str, str] = {}
        self._overrides_path = Path(overrides_path) if overrides_path else None
        self._overrides: dict[str, str] = {}
        self._stopwords_path = Path(stopwords_path) if stopwords_path else None
        self._stopwords: Optional[GreekStopWords] = None  # lazy load
        # Load cache if present
        try:
            if self._cache_path and self._cache_path.exists():
                self._cache = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except Exception:
            self._cache = {}
        # Load overrides if present
        try:
            if self._overrides_path and self._overrides_path.exists():
                self._overrides = json.loads(self._overrides_path.read_text(encoding="utf-8"))
        except Exception:
            self._overrides = {}

    def _ensure_backend(self):
        if self._backend is not None:
            return
        try:
            # Try GreekBackoffLemmatizer from CLTK 1.5+ API
            from cltk.lemmatize import GreekBackoffLemmatizer  # type: ignore

            self._backend = GreekBackoffLemmatizer()
        except Exception:
            # Try generic NLP pipeline fallback
            try:
                from cltk import NLP  # type: ignore

                ensure_cltk_grc_models()
                self._backend = NLP(language="grc", suppress_banner=True)
            except Exception:
                self._backend = None

    def _ensure_stopwords(self) -> GreekStopWords:
        """Lazy load stop words on first use."""
        if self._stopwords is None:
            try:
                if self._stopwords_path and self._stopwords_path.exists():
                    self._stopwords = GreekStopWords.load(self._stopwords_path)
                else:
                    # Default path
                    self._stopwords = GreekStopWords.load()
            except FileNotFoundError:
                # Fallback: empty stop word set if file missing
                self._stopwords = GreekStopWords(words=set())
        return self._stopwords

    @lru_cache(maxsize=4096)
    def lemmatize_token(self, token: str) -> str:
        self._ensure_backend()
        if not token:
            return ""
        key = normalize_greek_for_match(token)
        if key in self._overrides:
            lemma = normalize_greek_for_match(self._overrides[key])
            self._cache[key] = lemma
            return lemma
        if key in self._cache:
            return self._cache[key]
        if self._backend is None:
            # Fallback: return normalized token itself
            lemma = key
            if key:
                self._cache[key] = lemma
            return lemma
        try:
            # BackoffGreekLemmatizer API: .lemmatize -> list[(form, lemma)]
            if hasattr(self._backend, "lemmatize") and not hasattr(self._backend, "analyze"):
                pairs = self._backend.lemmatize([token])  # Must pass a list of tokens
                if pairs:
                    lemma = pairs[0][1]
                    lemma = normalize_greek_for_match(lemma)
                    if key:
                        self._cache[key] = lemma
                    return lemma
            # NLP pipeline API: .analyze(text) -> doc; pick first token's lemma
            if hasattr(self._backend, "analyze"):
                doc = self._backend.analyze(token)
                for s in getattr(doc, "sentences", []):
                    for w in getattr(s, "words", []):
                        lemma = getattr(w, "lemma", None)
                        if lemma:
                            lemma = normalize_greek_for_match(lemma)
                            if key:
                                self._cache[key] = lemma
                            return lemma
        except Exception:
            pass
        lemma = key
        if key:
            self._cache[key] = lemma
        return lemma

    def lemmatize(self, text: str) -> List[LemmaResult]:
        # Simple whitespace tokenization for scaffold; refine later.
        tokens = [t for t in (text or "").split() if t]
        results: List[LemmaResult] = []
        for t in tokens:
            lemma = self.lemmatize_token(t)
            results.append(LemmaResult(token=t, lemma=lemma))
        return results

    def best_lemma(self, text: str) -> str:
        """Extract the best lemma from potentially multi-word text.

        For multi-word phrases, skips stop words (articles, particles) and
        returns the lemma of the first substantive token.

        Args:
            text: Greek text (may contain multiple words)

        Returns:
            Lemma of the substantive token, or first token if all are stop words
        """
        stopwords = self._ensure_stopwords()

        # Iterate through tokens, skip stop words
        for raw in (text or "").split():
            tok = raw.strip()
            # Remove surrounding punctuation by Unicode category
            tok = "".join(ch for ch in tok if not ud.category(ch).startswith("P")) or tok

            # Check if token contains Greek characters
            if any(0x0370 <= ord(ch) <= 0x03FF or 0x1F00 <= ord(ch) <= 0x1FFF for ch in tok):
                # Normalize token for stop word check
                normalized = normalize_greek_for_match(tok)

                # Skip stop words
                if not stopwords.is_stop_word(normalized):
                    return self.lemmatize_token(tok)

        # Fallback: all tokens are stop words or no Greek tokens found
        # Return first token's lemma
        results = self.lemmatize(text)
        return results[0].lemma if results else ""

    def save_cache(self) -> None:
        if not self._cache_path:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def backend_name(self) -> str:
        self._ensure_backend()
        b = self._backend
        if b is None:
            return "fallback"
        name = type(b).__name__
        # Normalize known CLTK classes
        if name in ("GreekBackoffLemmatizer", "BackoffGreekLemmatizer"):
            return "cltk-backoff"
        if name == "NLP":
            return "cltk-nlp"
        return name
