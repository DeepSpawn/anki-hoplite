"""Helpers to ensure CLTK Greek resources are available.

Provides a callable to fetch Greek corpora/models for lemmatization.
This will attempt to download resources if missing (requires network).
"""

from __future__ import annotations


def ensure_cltk_grc_models() -> None:
    """Fetch CLTK Greek models/corpora if not present.

    Tries multiple APIs for compatibility with CLTK versions.
    """
    # Newer CLTK may auto-fetch via NLP; we attempt explicit fetch where available.
    try:
        # Legacy fetch API
        from cltk.data.fetch import FetchCorpus  # type: ignore

        fetcher = FetchCorpus(language="grc")
        # Main rollup package for Greek models
        fetcher.import_corpus("grc_models_cltk")
        return
    except Exception:
        pass

    try:
        # Trigger pipeline init which may auto-download
        from cltk import NLP  # type: ignore

        NLP(language="grc")
        return
    except Exception:
        pass

    # If we got here, we couldn't ensure downloads with available APIs.
    # The lemmatizer will fallback gracefully, but medium-level matching may be weaker.
    return

