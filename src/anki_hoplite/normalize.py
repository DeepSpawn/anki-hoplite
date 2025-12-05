"""Unicode and Greek-specific normalization utilities.

Policy (per PLAN.md):
- Apply NFC early for consistency.
- For matching: lowercase, strip punctuation, strip accents (combining marks),
  normalize final sigma, collapse whitespace.
"""

from __future__ import annotations

import re
import unicodedata as ud

_WS_RE = re.compile(r"\s+")


def normalize_text_nfc(text: str) -> str:
    """Apply Unicode NFC to input text (safe for None-like inputs)."""
    if text is None:
        return ""
    return ud.normalize("NFC", str(text))


def strip_accents(text: str) -> str:
    """Remove combining marks by NFD decomposition then recompose without marks."""
    text = normalize_text_nfc(text)
    # Decompose first to expose combining marks consistently.
    decomposed = ud.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if ud.category(ch) != "Mn")
    # Recompose to NFC for stable representation.
    return ud.normalize("NFC", stripped)


def _strip_punctuation(text: str) -> str:
    # Remove punctuation by Unicode category: any 'P*' becomes space.
    return "".join(ch if not ud.category(ch).startswith("P") else " " for ch in text)


def _normalize_final_sigma(text: str) -> str:
    # Map Greek sigma variants: medial sigma (σ) vs final sigma (ς) — use medial for matching.
    return text.replace("ς", "σ")


def normalize_greek_for_match(text: str) -> str:
    """Normalize Greek text for matching per project policy.

    Steps: NFC -> lowercase -> strip punctuation -> strip accents -> normalize final sigma ->
    collapse whitespace and trim.
    """
    if not text:
        return ""
    t = normalize_text_nfc(text)
    t = t.lower()
    t = _strip_punctuation(t)
    t = strip_accents(t)
    t = _normalize_final_sigma(t)
    t = _WS_RE.sub(" ", t).strip()
    return t
