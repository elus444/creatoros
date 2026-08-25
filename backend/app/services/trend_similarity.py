"""Normalized title / topic similarity for trend dedupe and diversity.

Uses token Jaccard + character n-gram overlap — no embeddings dependency.
Designed to catch near-duplicates ("AI Shorts tips" vs "Tips for AI Shorts")
and same-topic variations without inventing fake uniqueness.
"""

from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "is",
    "are",
    "was",
    "were",
    "be",
    "how",
    "why",
    "what",
    "when",
    "who",
    "this",
    "that",
    "you",
    "your",
    "my",
    "vs",
    "new",
    "best",
    "top",
    "video",
    "youtube",
    "short",
    "shorts",
    "trend",
    "trending",
    "viral",
}


def normalize_title(title: str) -> str:
    """Lowercase, strip accents/punctuation, drop filler words."""
    if not title:
        return ""
    folded = unicodedata.normalize("NFKD", title)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    tokens = [
        tok
        for tok in _WORD_RE.findall(folded.lower())
        if tok not in _STOPWORDS and len(tok) > 1
    ]
    return " ".join(tokens)


def title_tokens(title: str) -> set[str]:
    normalized = normalize_title(title)
    return set(normalized.split()) if normalized else set()


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    compact = text.replace(" ", "")
    if len(compact) < n:
        return {compact} if compact else set()
    return {compact[i : i + n] for i in range(len(compact) - n + 1)}


def title_similarity(a: str, b: str) -> float:
    """Semantic/topic-ish similarity in [0, 1] from tokens + char trigrams."""
    ta, tb = title_tokens(a), title_tokens(b)
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 1.0 if na == nb and na else 0.0

    if na == nb:
        return 1.0

    token_jaccard = 0.0
    overlap = 0.0
    if ta or tb:
        token_jaccard = len(ta & tb) / max(len(ta | tb), 1)
        # Overlap coefficient catches same-topic variants that add/drop words
        # ("air fryer chicken tenders…" vs "…quick recipe").
        overlap = len(ta & tb) / max(min(len(ta), len(tb)), 1)

    ga, gb = _char_ngrams(na), _char_ngrams(nb)
    gram_jaccard = len(ga & gb) / max(len(ga | gb), 1) if ga or gb else 0.0

    blended = (0.45 * token_jaccard) + (0.35 * overlap) + (0.20 * gram_jaccard)
    return round(blended, 4)


def is_similar_to_any(
    title: str,
    others: list[str],
    *,
    threshold: float = 0.5,
) -> bool:
    return any(title_similarity(title, other) >= threshold for other in others)


def select_diverse(
    items: list,
    *,
    title_getter,
    limit: int,
    threshold: float = 0.5,
    seed_titles: list[str] | None = None,
) -> list:
    """Greedy diversity: keep highest-priority items that aren't near-duplicates."""
    kept: list = []
    seen_titles = list(seed_titles or [])
    for item in items:
        title = title_getter(item)
        if is_similar_to_any(title, seen_titles, threshold=threshold):
            continue
        kept.append(item)
        seen_titles.append(title)
        if len(kept) >= limit:
            break
    return kept
