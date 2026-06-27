"""
Case library search module.

Loads the case_library.json and provides search functions to find
calibration examples that match the current query context.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from functools import lru_cache

_LIBRARY_PATH = Path(__file__).parent.parent / "data" / "case_library.json"


@lru_cache(maxsize=1)
def _load_library() -> list[dict]:
    """Load and cache the case library from disk."""
    if _LIBRARY_PATH.exists():
        with _LIBRARY_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return []


def reload_library() -> list[dict]:
    """Force-reload the case library (clears the cache)."""
    _load_library.cache_clear()
    return _load_library()


def _score_case(case: dict, query_type: str, query: str, section: str, keywords: list[str]) -> int:
    """
    Score a calibration case for relevance.
    Higher = more relevant.
    """
    score = 0

    # Exact query type match (most important)
    if case.get("query_type", "").lower() == query_type.lower():
        score += 10

    # Guideline section match
    if case.get("section", "") == section:
        score += 5

    # Keyword matches
    case_text = " ".join([
        case.get("query", ""),
        case.get("result", ""),
        case.get("reasoning", ""),
        " ".join(case.get("conditions", [])),
        " ".join(case.get("keywords", [])),
    ]).lower()

    for kw in keywords:
        if kw.lower() in case_text:
            score += 2

    # Query word overlap
    q_words = set(re.sub(r"[^\w\s]", "", query.lower()).split())
    case_q_words = set(re.sub(r"[^\w\s]", "", case.get("query", "").lower()).split())
    overlap = q_words & case_q_words
    score += len(overlap)

    return score


def search_cases(
    query_type: str = "",
    query: str = "",
    section: str = "",
    keywords: list[str] | None = None,
    max_results: int = 5,
) -> list[dict]:
    """
    Search the case library for matching calibration examples.

    Parameters
    ----------
    query_type : str
        Filter by query type.
    query : str
        The user's query text (used for keyword matching).
    section : str
        Filter by guideline section (e.g. "5.16.1").
    keywords : list[str]
        Additional keywords to match against.
    max_results : int
        Maximum number of results to return.

    Returns
    -------
    list[dict]
        Sorted list of matching cases (most relevant first).
    """
    library = _load_library()
    if not library:
        return []

    kws = keywords or []

    # Add query words as keywords
    if query:
        kws = kws + [w for w in query.lower().split() if len(w) > 3]

    scored = [
        (case, _score_case(case, query_type, query, section, kws))
        for case in library
    ]

    # Sort by score descending, filter out zero-score if we have better matches
    scored.sort(key=lambda x: x[1], reverse=True)

    top_score = scored[0][1] if scored else 0

    results = [case for case, score in scored if score > 0]

    return results[:max_results]


def search_by_section(section: str) -> list[dict]:
    """Return all cases for a given guideline section."""
    library = _load_library()
    return [c for c in library if c.get("section", "") == section]


def search_by_query_type(query_type: str) -> list[dict]:
    """Return all cases for a given query type."""
    library = _load_library()
    return [c for c in library if c.get("query_type", "").lower() == query_type.lower()]


def search_by_keyword(keyword: str) -> list[dict]:
    """Return all cases containing a keyword anywhere in their text."""
    library = _load_library()
    kw = keyword.lower()
    results = []
    for case in library:
        text = " ".join([
            case.get("query", ""),
            case.get("result", ""),
            case.get("reasoning", ""),
            " ".join(case.get("conditions", [])),
            " ".join(case.get("keywords", [])),
        ]).lower()
        if kw in text:
            results.append(case)
    return results


def get_all_cases() -> list[dict]:
    """Return all cases in the library."""
    return list(_load_library())


def add_case(case: dict) -> bool:
    """
    Append a new case to the case library.
    Assigns a new id and saves to disk.
    Returns True on success.
    """
    library = list(_load_library())

    # Assign next id
    existing_ids = [c.get("id", 0) for c in library]
    next_id = max(existing_ids, default=0) + 1
    case["id"] = next_id

    library.append(case)

    try:
        with _LIBRARY_PATH.open("w", encoding="utf-8") as f:
            json.dump(library, f, indent=2, ensure_ascii=False)
        # Clear cache so next load picks up the new case
        _load_library.cache_clear()
        return True
    except OSError:
        return False
