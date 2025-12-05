"""Reference deck index builder (export-backed; AnkiConnect later).

Scaffold: builds empty indexes and provides interfaces. Implement parsing of
resources/Unified-Greek.txt in a later pass once format details are confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple
import json
import re
import html as html_lib

from .normalize import normalize_greek_for_match
from .lemmatize import GreekLemmatizer


@dataclass
class NoteEntry:
    note_id: str
    model: str
    greek_text: str
    english_text: str


@dataclass
class DeckIndex:
    exact_greek: Dict[str, Set[str]] = field(default_factory=dict)
    lemma_index: Dict[str, Set[str]] = field(default_factory=dict)
    english_index: Dict[str, Set[str]] = field(default_factory=dict)
    notes: List[NoteEntry] = field(default_factory=list)

    def add_note(self, note: NoteEntry, lemmatizer: GreekLemmatizer | None = None) -> None:
        self.notes.append(note)
        g_norm = normalize_greek_for_match(note.greek_text)
        if g_norm:
            self.exact_greek.setdefault(g_norm, set()).add(note.note_id)
        if lemmatizer and note.greek_text:
            lemma = normalize_greek_for_match(lemmatizer.best_lemma(note.greek_text))
            if lemma:
                self.lemma_index.setdefault(lemma, set()).add(note.note_id)
        e_norm = (note.english_text or "").strip().lower()
        if e_norm:
            self.english_index.setdefault(e_norm, set()).add(note.note_id)

_SOUND_RE = re.compile(r"\[sound:[^\]]+\]")
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_field_text(text: str) -> str:
    if not text:
        return ""
    t = _SOUND_RE.sub(" ", text)
    t = _TAG_RE.sub(" ", t)
    t = html_lib.unescape(t)
    return " ".join(t.split())


def _load_model_map(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"defaults": {"greek_index": 0, "english_index": 1, "ignore": False}, "models": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def build_from_export(
    export_path: str | Path,
    model_map_path: str | Path | None = None,
    lemmatizer: GreekLemmatizer | None = None,
) -> DeckIndex:
    """Parse a tab-separated Anki export with header comments and build index.

    Expected header hints:
      - #separator:tab
      - #guid column:1
      - #notetype column:2
      - #deck column:3
      - #tags column:N
    Fields are assumed to be all columns after deck and before the tags column.
    """
    export_path = Path(export_path)
    di = DeckIndex()
    if not export_path.exists():
        return di

    model_map = _load_model_map(model_map_path) if model_map_path else {"defaults": {"greek_index": 0, "english_index": 1, "ignore": False}, "models": {}}
    defaults = model_map.get("defaults", {})
    models = model_map.get("models", {})

    tags_col = None
    lem = lemmatizer or GreekLemmatizer()
    with export_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                if line.lower().startswith("#tags column:"):
                    try:
                        tags_col = int(line.split(":", 1)[1].strip())
                    except Exception:
                        tags_col = None
                continue
            # Data line
            parts = line.rstrip("\n").split("\t")
            if not parts or len(parts) < 4:
                continue
            guid = parts[0].strip().strip('"')
            model = parts[1].strip()
            deck = parts[2].strip()
            # Determine columns
            if tags_col and 0 < tags_col <= len(parts):
                tags_idx0 = tags_col - 1
            else:
                tags_idx0 = len(parts) - 1
            field_values = parts[3:tags_idx0]
            # Map model to field indexes
            mconf = models.get(model, {})
            ignore = mconf.get("ignore", defaults.get("ignore", False))
            if ignore:
                continue
            g_idx = mconf.get("greek_index", defaults.get("greek_index", 0))
            e_idx = mconf.get("english_index", defaults.get("english_index", 1))
            greek_text = _clean_field_text(field_values[g_idx]) if g_idx < len(field_values) else ""
            english_text = _clean_field_text(field_values[e_idx]) if e_idx < len(field_values) else ""
            note = NoteEntry(note_id=guid or "", model=model, greek_text=greek_text, english_text=english_text)
            # Use a shared lemmatizer to populate lemma index
            di.add_note(note, lemmatizer=lem)

    return di
