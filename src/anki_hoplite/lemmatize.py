"""CLTK-backed lemmatization wrapper with graceful fallback.

The real implementation will use CLTK for Ancient Greek and cache results.
For scaffolding, we implement a lazy import and a simple fallback that returns
the normalized token itself when CLTK is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import List

from .normalize import normalize_greek_for_match
from .cltk_setup import ensure_cltk_grc_models


@dataclass
class LemmaResult:
    token: str
    lemma: str


class GreekLemmatizer:
    def __init__(self) -> None:
        self._backend = None  # lazy init

    def _ensure_backend(self):
        if self._backend is not None:
            return
        try:
            # Attempt to ensure models first (no-op if already present)
            ensure_cltk_grc_models()
            from cltk.lemmatize.grc.backoff import (  # type: ignore
                BackoffGreekLemmatizer,
            )

            self._backend = BackoffGreekLemmatizer()
        except Exception:
            # Try generic NLP pipeline fallback
            try:
                from cltk import NLP  # type: ignore

                ensure_cltk_grc_models()
                self._backend = NLP(language="grc")
            except Exception:
                self._backend = None

    @lru_cache(maxsize=4096)
    def lemmatize_token(self, token: str) -> str:
        self._ensure_backend()
        if not token:
            return ""
        if self._backend is None:
            # Fallback: return normalized token itself
            return normalize_greek_for_match(token)
        try:
            # BackoffGreekLemmatizer API: .lemmatize -> list[(form, lemma)]
            if hasattr(self._backend, "lemmatize") and not hasattr(self._backend, "analyze"):
                pairs = self._backend.lemmatize(token)
                if pairs:
                    return pairs[0][1]
            # NLP pipeline API: .analyze(text) -> doc; pick first token's lemma
            if hasattr(self._backend, "analyze"):
                doc = self._backend.analyze(token)
                for s in getattr(doc, "sentences", []):
                    for w in getattr(s, "words", []):
                        lemma = getattr(w, "lemma", None)
                        if lemma:
                            return lemma
        except Exception:
            pass
        return normalize_greek_for_match(token)

    def lemmatize(self, text: str) -> List[LemmaResult]:
        # Simple whitespace tokenization for scaffold; refine later.
        tokens = [t for t in (text or "").split() if t]
        results: List[LemmaResult] = []
        for t in tokens:
            lemma = self.lemmatize_token(t)
            results.append(LemmaResult(token=t, lemma=lemma))
        return results

    def best_lemma(self, text: str) -> str:
        results = self.lemmatize(text)
        if not results:
            return ""
        # For single-word inputs, return the sole lemma; otherwise first token's lemma.
        return results[0].lemma
