import pytest

from app.services.language import (
    classify_trend_language,
    detect_language,
    is_english_text,
    title_english_score,
)


def test_english_detection_accepts_english_titles() -> None:
    assert is_english_text("How to grow on YouTube Shorts with AI tools")
    assert detect_language("Best AI productivity tips for creators") == "en"


def test_english_detection_rejects_non_latin() -> None:
    assert not is_english_text("인공지능 콘텐츠 자동화 방법")
    assert detect_language("人工知能のトレンド") == "und"


def test_english_detection_rejects_spanish_function_words() -> None:
    assert not is_english_text("Cómo hacer pasta rápida en casa hoy")
    assert title_english_score("Cara membuat konten viral untuk YouTube") < 0.5


@pytest.mark.asyncio
async def test_hashtag_only_titles_are_not_treated_as_english() -> None:
    assert not is_english_text("#viral #fyp #shorts #ai #trending")
    assert title_english_score("#viralvideo #tiktokvideo #youtubeshorts #advice") < 0.5


@pytest.mark.asyncio
async def test_classify_rejects_non_english_audio_even_with_english_description() -> None:
    decision = await classify_trend_language(
        title="Video tip viral",
        description="This is a fully English description about cooking pasta.",
        default_language="es",
        default_audio_language="es-419",
        llm_service=None,
    )
    assert decision.is_english is False
    assert decision.method == "metadata"


@pytest.mark.asyncio
async def test_classify_keeps_english_title_when_default_language_is_non_english() -> None:
    decision = await classify_trend_language(
        title="How to make pasta in 5 minutes",
        description=None,
        default_language="es",
        default_audio_language=None,
        llm_service=None,
    )
    assert decision.is_english is True
    assert decision.language == "en"


@pytest.mark.asyncio
async def test_classify_accepts_english_title_without_ai() -> None:
    decision = await classify_trend_language(
        title="5-minute pasta trend for busy creators",
        description=None,
        llm_service=None,
    )
    assert decision.is_english is True
    assert decision.language == "en"


@pytest.mark.asyncio
async def test_classify_keeps_title_that_claims_english_despite_hindi_audio_tag() -> None:
    decision = await classify_trend_language(
        title="kids shorts | kids stories in English | kids ai videos",
        description=None,
        default_language="hi",
        default_audio_language="hi",
        llm_service=None,
    )
    assert decision.is_english is True
    assert decision.language == "en"


@pytest.mark.asyncio
async def test_classify_still_rejects_hindi_audio_with_english_hashtag_title() -> None:
    decision = await classify_trend_language(
        title="HUMAN BIT THE SNAKE! | Snake Family Comedy | AI Funny Video #shorts",
        description=None,
        default_audio_language="hi",
        llm_service=None,
    )
    assert decision.is_english is False
    assert decision.method == "metadata"


@pytest.mark.asyncio
async def test_classify_uses_ai_when_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeLLM:
        async def generate_structured(self, **kwargs):
            from app.services.llm_service import LLMResult

            return LLMResult(
                data={
                    "is_english": False,
                    "confidence": 0.91,
                    "reason": "Indonesian romanized title",
                },
                raw_text="{}",
                model="fake",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            )

    decision = await classify_trend_language(
        title="Tutorial cara edit video aesthetic",
        description="Learn editing tips in this guide",
        llm_service=_FakeLLM(),
    )
    assert decision.is_english is False
    assert decision.method == "ai"
