"""English-language detection for trend candidates.

Priority order (title + spoken/content language first; description never alone):
  1. YouTube defaultAudioLanguage / defaultLanguage tags when present
  2. Title script + English vs non-English Latin cue heuristics
  3. AI classification only when signals are ambiguous

Description text may support the AI step but cannot accept a candidate
whose title or spoken-language signals are non-English.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from pydantic import BaseModel, Field

logger = logging.getLogger("creatoros.language")

_ENGLISH_CUES = {
    "the",
    "a",
    "an",
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
    "new",
    "best",
    "vs",
    "tips",
    "guide",
    "ai",
    "video",
    "youtube",
    "short",
    "shorts",
    "make",
    "get",
    "use",
    "using",
    "from",
    "into",
    "about",
    "really",
    "actually",
    "should",
    "could",
    "would",
    "here's",
    "heres",
}

# High-signal function words from common non-English Latin YouTube locales.
# Used only when English cue density is low — avoids rejecting "La Liga tips".
_NON_ENGLISH_LATIN_CUES = {
    # Spanish
    "el",
    "los",
    "las",
    "una",
    "unos",
    "unas",
    "que",
    "por",
    "para",
    "como",
    "está",
    "esta",
    "esto",
    "están",
    "del",
    "al",
    "más",
    "mas",
    "también",
    "tambien",
    "porque",
    "sobre",
    "hacer",
    "hace",
    "hoy",
    "año",
    "anos",
    # Portuguese
    "não",
    "nao",
    "você",
    "voce",
    "uma",
    "pelo",
    "pela",
    "isso",
    "aqui",
    "muito",
    "mais",
    "como",
    "para",
    "com",
    "dos",
    "das",
    # French
    "les",
    "des",
    "une",
    "dans",
    "pour",
    "avec",
    "sur",
    "pas",
    "est",
    "qui",
    "que",
    "cette",
    "ces",
    "mais",
    "aussi",
    # Indonesian / Malay
    "yang",
    "dan",
    "untuk",
    "dari",
    "dengan",
    "ini",
    "itu",
    "tidak",
    "ada",
    "bisa",
    "cara",
    "juga",
    "akan",
    "sudah",
    "kami",
    "kamu",
    "gua",
    # German
    "und",
    "der",
    "die",
    "das",
    "nicht",
    "ich",
    "sie",
    "ein",
    "eine",
    "mit",
    "auf",
    "für",
    "fur",
    "auch",
    "wie",
    # Italian
    "che",
    "per",
    "una",
    "con",
    "non",
    "sono",
    "questo",
    "come",
    "più",
    "piu",
}

_WORD_RE = re.compile(r"[A-Za-z']+")
_HASHTAG_RE = re.compile(r"#\w+", re.UNICODE)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def content_title_text(title: str) -> str:
    """Title text used for language checks — hashtags/URLs don't count as English."""
    if not title:
        return ""
    cleaned = _HASHTAG_RE.sub(" ", title)
    cleaned = _URL_RE.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


class LanguageClassification(BaseModel):
    is_english: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=300)


@dataclass(frozen=True)
class LanguageDecision:
    language: str  # "en" | "und"
    is_english: bool
    method: str  # metadata | heuristic | ai | rejected
    confidence: float
    reason: str


def _script_name(char: str) -> str:
    try:
        return unicodedata.name(char).split()[0]
    except ValueError:
        return ""


def _english_lang_tag(tag: str | None) -> bool | None:
    """Return True/False when a BCP-47-ish tag is decisive, else None."""
    if not tag or not str(tag).strip():
        return None
    primary = str(tag).strip().lower().replace("_", "-").split("-", 1)[0]
    if primary in {"zxx", "und", "mul"}:
        return None
    if primary == "en":
        return True
    return False


def title_english_score(text: str) -> float:
    """Heuristic English confidence for a title in [0, 1]."""
    # Score the content words, not hashtag spam / links.
    text = content_title_text(text)
    if not text or not text.strip():
        return 0.0

    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0

    latin = 0
    non_latin = 0
    for ch in letters:
        name = _script_name(ch)
        if "LATIN" in name or ("a" <= ch.lower() <= "z"):
            latin += 1
        else:
            non_latin += 1

    if non_latin > 0 and non_latin / max(len(letters), 1) > 0.08:
        return 0.0

    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return 0.0

    cue_hits = sum(1 for w in words if w in _ENGLISH_CUES)
    non_en_hits = sum(1 for w in words if w in _NON_ENGLISH_LATIN_CUES)
    ascii_ratio = latin / max(len(letters), 1)
    cue_ratio = cue_hits / max(len(words), 1)
    non_en_ratio = non_en_hits / max(len(words), 1)

    # Latin titles dominated by non-English function words → reject.
    if non_en_ratio >= 0.35 and cue_ratio < 0.2:
        return min(0.35, 0.5 - non_en_ratio)

    score = (0.55 * ascii_ratio) + (0.45 * min(cue_ratio * 2.5, 1.0))
    if non_en_ratio > 0:
        score -= min(0.45, non_en_ratio * 0.9)
    # Latin titles with zero non-English function words are usually English
    # niche phrases ("5-minute pasta trend") even with few cue words.
    if non_en_ratio == 0 and ascii_ratio >= 0.95:
        score = max(score, 0.62 if len(words) <= 6 else 0.58)
    # Very short leftover text after hashtag stripping is unreliable.
    if len(words) < 2:
        score = min(score, 0.45)
    return max(0.0, min(1.0, score))


def is_english_text(text: str, *, min_confidence: float = 0.58) -> bool:
    """Return True when `text` is likely English enough for the trends UI."""
    return title_english_score(text) >= min_confidence


def detect_language(text: str) -> str:
    """Return ISO-ish tag: 'en' or 'und' (undetermined / non-English)."""
    return "en" if is_english_text(text) else "und"


async def classify_trend_language(
    *,
    title: str,
    description: str | None = None,
    default_language: str | None = None,
    default_audio_language: str | None = None,
    llm_service=None,
) -> LanguageDecision:
    """Decide whether a trend candidate is genuinely English content.

    Spoken/content language tags and the title dominate. Description is only
    used as supporting context for AI — never as the sole accept signal.
    """
    audio_en = _english_lang_tag(default_audio_language)
    default_en = _english_lang_tag(default_language)

    content_title = content_title_text(title)
    title_score = title_english_score(title)

    # Hard reject on spoken-language tags unless the title clearly claims
    # English. Kids/AI farms often tag Hindi audio on English-hashtag clips;
    # only ignore the tag when the title itself says it is English.
    title_claims_english = "english" in (content_title or "").lower()
    if audio_en is False:
        if title_claims_english and title_score >= 0.62:
            audio_en = None
        else:
            return LanguageDecision(
                language="und",
                is_english=False,
                method="metadata",
                confidence=0.95,
                reason=f"defaultAudioLanguage={default_audio_language}",
            )
    if default_en is False and audio_en is not True and title_score < 0.58:
        return LanguageDecision(
            language="und",
            is_english=False,
            method="metadata",
            confidence=0.9,
            reason=f"defaultLanguage={default_language}",
        )
    # Channel UI locale is not spoken language — ignore it when the title
    # is clearly English and YouTube did not tag audio.
    if default_en is False and audio_en is None and title_score >= 0.58:
        default_en = None
    words = [w.lower() for w in _WORD_RE.findall(content_title or "")]
    non_en_ratio = (
        sum(1 for w in words if w in _NON_ENGLISH_LATIN_CUES) / max(len(words), 1)
        if words
        else 1.0
    )
    original_hashtag_heavy = bool(title) and (
        len(_HASHTAG_RE.findall(title)) >= 3
        and len(words) <= 4
    )

    if title_score < 0.4 or not content_title:
        return LanguageDecision(
            language="und",
            is_english=False,
            method="heuristic",
            confidence=1.0 - title_score,
            reason="title_not_english",
        )

    metadata_english = audio_en is True or default_en is True
    metadata_unknown = audio_en is None and default_en is None

    # Strong accept: English YouTube tags + acceptable English title.
    if metadata_english and title_score >= 0.55 and non_en_ratio < 0.35:
        return LanguageDecision(
            language="en",
            is_english=True,
            method="metadata",
            confidence=max(title_score, 0.8),
            reason="youtube_language_tags_english",
        )

    # Clear Latin-English title with no non-English function-word dominance.
    # When spoken-language metadata is missing, demand a stronger title signal.
    if (
        title_score >= (0.7 if metadata_unknown else 0.65)
        and non_en_ratio < 0.2
        and not original_hashtag_heavy
        and (metadata_unknown or metadata_english)
    ):
        return LanguageDecision(
            language="en",
            is_english=True,
            method="heuristic",
            confidence=title_score,
            reason="title_english_clear",
        )

    # Ambiguous / hashtag-heavy / missing audio tags — AI when available.
    needs_ai = (
        non_en_ratio >= 0.15
        or original_hashtag_heavy
        or (metadata_unknown and title_score < 0.78)
        or (0.4 <= title_score < 0.62)
    )
    if (
        not needs_ai
        and title_score >= 0.58
        and non_en_ratio < 0.2
        and not original_hashtag_heavy
    ):
        return LanguageDecision(
            language="en",
            is_english=True,
            method="heuristic",
            confidence=title_score,
            reason="title_english_sufficient",
        )

    if llm_service is None:
        accepted = (
            title_score >= (0.7 if metadata_unknown else 0.58)
            and non_en_ratio < 0.2
            and not original_hashtag_heavy
        )
        return LanguageDecision(
            language="en" if accepted else "und",
            is_english=accepted,
            method="heuristic",
            confidence=title_score,
            reason="ambiguous_without_ai",
        )

    try:
        desc = (description or "").strip()
        if len(desc) > 400:
            desc = desc[:400] + "…"
        system = (
            "You classify whether a short-form video trend is genuinely English "
            "spoken/content language. Prioritize the TITLE and spoken/content "
            "language signals over the description. "
            "Do NOT accept a video just because the description is English. "
            "Hashtag-only or romanized non-English titles are not English. "
            "Reply with the schema only."
        )
        prompt = (
            f"Title: {title}\n"
            f"Title without hashtags: {content_title or '(empty)'}\n"
            f"defaultLanguage: {default_language or 'unknown'}\n"
            f"defaultAudioLanguage: {default_audio_language or 'unknown'}\n"
            f"Description (supporting only): {desc or '(none)'}\n\n"
            "Is this video's primary spoken/content language English?"
        )
        result = await llm_service.generate_structured(
            prompt=prompt,
            response_model=LanguageClassification,
            system_instruction=system,
            temperature=0.0,
        )
        parsed = LanguageClassification.model_validate(result.data)
        # Even if AI says English, refuse when title heuristic is very weak.
        if parsed.is_english and title_score < 0.45:
            return LanguageDecision(
                language="und",
                is_english=False,
                method="ai",
                confidence=parsed.confidence,
                reason="ai_english_but_title_weak",
            )
        return LanguageDecision(
            language="en" if parsed.is_english else "und",
            is_english=parsed.is_english,
            method="ai",
            confidence=parsed.confidence,
            reason=parsed.reason[:300],
        )
    except Exception as exc:  # noqa: BLE001 — language gate must never crash collect
        logger.info("AI language classification unavailable: %s", exc)
        accepted = (
            title_score >= (0.7 if metadata_unknown else 0.58)
            and non_en_ratio < 0.2
            and not original_hashtag_heavy
        )
        return LanguageDecision(
            language="en" if accepted else "und",
            is_english=accepted,
            method="heuristic",
            confidence=title_score,
            reason=f"ai_unavailable:{type(exc).__name__}",
        )
