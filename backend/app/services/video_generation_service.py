"""Video generation provider abstraction.

No fake videos. If no provider credentials are configured, generation fails
clearly with VideoProviderNotConfiguredError so the API can surface a useful
message instead of pretending a file exists.

Supported provider keys (env):
  VIDEO_GENERATION_PROVIDER=none|json2video|replicate|http
  JSON2VIDEO_API_KEY=         # free-tier narrated Shorts + Azure TTS (backend only)
  REPLICATE_API_TOKEN=        # silent diffusion clips (backend only)
  VIDEO_GENERATION_API_KEY=   # http provider
  VIDEO_GENERATION_API_URL=   # http provider
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import struct
import zlib
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.services.agents.kids_shorts_craft import backdrop_color, normalize_spoken_narration
from app.services.storage_service import StorageService

logger = logging.getLogger("creatoros.video")

REPLICATE_MODEL = "minimax/video-01"
REPLICATE_VERSION = (
    "5aa835260ff7f40f4069c41185f72036accf99e29957bb4a3b3a911f3b6c1912"
)
REPLICATE_API_BASE = "https://api.replicate.com/v1"

JSON2VIDEO_API_BASE = "https://api.json2video.com/v2"
# 9:16 Shorts canvas (JSON2Video preset).
JSON2VIDEO_RESOLUTION = "instagram-story"

# minimax/video-01 has no width/height fields. Aspect ratio follows first_frame_image.
SHORT_FRAME_WIDTH = 576
SHORT_FRAME_HEIGHT = 1024  # 9:16

_POLL_INTERVAL_SECONDS = 3.0
_MAX_POLL_ATTEMPTS = 200  # ~10 minutes
_JSON2VIDEO_POLL_SECONDS = 5.0
# Seedance clips take several minutes each. 3 scenes routinely exceed 10 min.
_JSON2VIDEO_MAX_POLLS = 360  # ~30 minutes
_JSON2VIDEO_AI_SCENE_LIMIT = 3
_JSON2VIDEO_PROMPT_MAX = 1024
_VERTICAL_FRAME_DATA_URI: str | None = None
_WHITESPACE_RE = re.compile(r"\s+")


class VideoGenerationError(Exception):
    """Provider/transport failure — never includes API keys in the message."""


class VideoProviderNotConfiguredError(VideoGenerationError):
    """Raised when no video provider is configured."""


class VideoRateLimitError(VideoGenerationError):
    """Provider rate limit / quota exceeded."""


@dataclass
class VideoGenerationResult:
    video_url: str
    storage_key: str | None = None
    thumbnail_url: str | None = None
    provider: str | None = None
    raw: dict | None = None


class VideoGenerationService:
    def __init__(self, timeout: float = 600.0) -> None:
        self._timeout = timeout
        self._storage = StorageService()

    async def generate(
        self,
        *,
        brief: dict,
        format: str = "short",
        owner_id: str | None = None,
        video_provider: dict | None = None,
    ) -> VideoGenerationResult:
        # Product is short-form only; ignore/normalize any other value.
        format = "short"
        settings = get_settings()
        stored = (
            video_provider
            if video_provider
            and video_provider.get("provider") == "replicate"
            and video_provider.get("api_key")
            else None
        )
        provider = (settings.video_generation_provider or "none").strip().lower()

        # Determine which video generation provider to use, in order:
        # 1. If the user stored a Replicate credential in Settings, that's an
        #    explicit preference and always wins.
        # 2. Otherwise, if VIDEO_GENERATION_PROVIDER isn't explicitly set,
        #    fall back to whatever credentials are configured in the
        #    environment, preferring JSON2Video (cheaper, includes
        #    narration) over Replicate (diffusion model, no narration).
        if stored:
            provider = "replicate"  # User explicitly stored Replicate creds
        elif provider in {"", "none", "disabled"}:
            if settings.json2video_api_key:
                provider = "json2video"  # Preferred: narrated Shorts
            elif settings.replicate_api_token:
                provider = "replicate"  # Fallback: diffusion model

        # Final validation: no usable provider/credentials found anywhere.
        if provider in {"", "none", "disabled"}:
            raise VideoProviderNotConfiguredError(
                "VIDEO_GENERATION_PROVIDER is not configured. Save a Replicate "
                "API key in Settings → Integrations, or set JSON2VIDEO_API_KEY / "
                "REPLICATE_API_TOKEN on the backend. Creator OS will not invent "
                "or fake video assets."
            )

        if provider in {"json2video", "j2v"}:
            return await self._generate_json2video(brief=brief, owner_id=owner_id)
        if provider == "replicate":
            return await self._generate_replicate(
                brief=brief, owner_id=owner_id, stored=stored
            )
        if provider == "http":
            return await self._generate_http(
                brief=brief, format=format, owner_id=owner_id
            )

        raise VideoProviderNotConfiguredError(
            f"Unknown VIDEO_GENERATION_PROVIDER '{provider}'. "
            "Supported: none, json2video, replicate, http."
        )

    def _spoken_script(self, brief: dict) -> str:
        narration = normalize_spoken_narration(brief.get("narration") or "")
        if narration:
            return narration
        concept = (brief.get("concept") or "").strip()
        scenes = [
            _WHITESPACE_RE.sub(" ", str(s).strip())
            for s in (brief.get("scenes") or [])
            if str(s).strip()
        ]
        caption = (brief.get("caption") or "").strip()
        parts = [p for p in [concept, *scenes, caption] if p]
        spoken = normalize_spoken_narration(". ".join(parts))
        if not spoken:
            raise VideoGenerationError(
                "Video brief has no narration/scenes — refusing to call JSON2Video "
                "without text for voiceover."
            )
        return spoken

    def _scene_cards(self, brief: dict, *, limit: int = _JSON2VIDEO_AI_SCENE_LIMIT) -> list[str]:
        titles = brief.get("titles") or []
        concept = (brief.get("concept") or "").strip()
        scene_lines = [
            _WHITESPACE_RE.sub(" ", str(s).strip())
            for s in (brief.get("scenes") or [])
            if str(s).strip()
        ]
        headline = str(titles[0] if titles else concept or "Kids cartoon adventure")[:80]
        cards = scene_lines or [headline]
        return cards[:limit]

    def _kids_video_prompt(
        self, *, scene: str, concept: str, visual: str, spoken_line: str = ""
    ) -> str:
        beat = _WHITESPACE_RE.sub(
            " ", (scene or "the character notices a problem and tries to help").strip()
        )
        story = _WHITESPACE_RE.sub(" ", (concept or "").strip())
        style_bits = _WHITESPACE_RE.sub(" ", (visual or "").strip())
        line = _WHITESPACE_RE.sub(" ", (spoken_line or "").strip())
        talk = (
            f'The character is speaking these exact words, mouth clearly moving '
            f'in sync with the voice: "{line}". '
            if line
            else "The character is talking, mouth moving naturally with speech. "
        )
        prompt = (
            "Vertical 9:16 Pixar/storybook cartoon, cinematic kids Short. "
            "Waist-up medium shot, character centered, face and mouth visible, "
            "headroom, nothing cropped. Locked camera, no pan, no zoom. "
            "Same character and world for this whole video. Natural lighting "
            "for the setting. "
            f"{talk}"
            "Expressive acting that matches the line. "
            "No on-screen text, logos, subtitles, or watermark. "
            "Not a generic colorful void or random playground. "
            f"Story: {story}. "
            f"This beat: {beat}."
            + (f" Setting and look: {style_bits}." if style_bits else "")
        )
        return prompt[:_JSON2VIDEO_PROMPT_MAX].rstrip()

    def _split_spoken_beats(self, spoken: str, count: int) -> list[str]:
        """Split narration into one voice line per scene so audio length drives the cut."""
        count = max(1, int(count or 1))
        spoken = normalize_spoken_narration(spoken)
        words = spoken.split()
        if not words:
            return [spoken or ""] * count
        beats: list[str] = []
        start = 0
        for index in range(count):
            remaining_words = len(words) - start
            if remaining_words <= 0:
                break
            remaining_slots = count - index
            take = max(1, round(remaining_words / remaining_slots))
            take = min(take, remaining_words)
            chunk = words[start : start + take]
            start += take
            text = " ".join(chunk).strip()
            if text and text[-1] not in ".!?":
                text = f"{text}."
            beats.append(text)
        return beats or [spoken]

    def _json2video_movie(
        self, brief: dict, *, clip_urls: list[str] | None = None
    ) -> dict:
        """Build a 9:16 kids Short with per-scene TTS so picture matches speech."""
        settings = get_settings()
        spoken = self._spoken_script(brief)
        concept = (brief.get("concept") or "").strip()
        visual = (brief.get("visual_direction") or "").strip()
        cards = self._scene_cards(brief)
        sources = [
            url
            for url in (clip_urls or [])
            if isinstance(url, str) and url.startswith("http")
        ]
        if sources:
            cards = cards[: len(sources)] or cards[:1]
        video_model = (settings.json2video_video_model or "seedance-v1.5-pro").strip()
        world_color = backdrop_color(concept or spoken)
        voice_name = (settings.json2video_voice or "en-US-AnaNeural").strip()
        beats = self._split_spoken_beats(spoken, len(cards))
        cards = cards[: len(beats)]

        scenes: list[dict] = []
        for index, (line, spoken_line) in enumerate(zip(cards, beats)):
            if index < len(sources):
                visual_el: dict = {
                    "type": "video",
                    "src": sources[index],
                    "muted": True,
                    "loop": -1,
                    "resize": "cover",
                    "position": "center",
                    "duration": -2,
                }
            else:
                visual_el = {
                    "type": "video",
                    "model": video_model,
                    "prompt": self._kids_video_prompt(
                        scene=line,
                        concept=concept,
                        visual=visual,
                        spoken_line=spoken_line,
                    ),
                    "muted": True,
                    "loop": -1,
                    "resize": "cover",
                    "position": "center",
                    "duration": -2,
                }
            scene: dict = {
                "comment": f"kids-scene-{index + 1}",
                "duration": -1,
                "background-color": world_color,
                "cache": False,
                "elements": [
                    visual_el,
                    {
                        "type": "voice",
                        "text": spoken_line,
                        "model": "azure",
                        "voice": voice_name,
                        "start": 0,
                        "duration": -1,
                        "extra-time": 0.15,
                    },
                ],
            }
            if index > 0:
                scene["transition"] = {"style": "fade", "duration": 0.12}
            scenes.append(scene)

        return {
            "resolution": JSON2VIDEO_RESOLUTION,
            # Medium finishes faster on free-tier queues; high often exceeds render time.
            "quality": "medium",
            "cache": False,
            "comment": "creatoros-kids-short",
            "scenes": scenes,
        }

    async def _generate_motion_clips(self, brief: dict) -> list[str]:
        """Generate real motion clips (Replicate). Returns public MP4 URLs."""
        concept = (brief.get("concept") or "").strip()
        visual = (brief.get("visual_direction") or "").strip()
        prompts = [
            self._kids_video_prompt(scene=line, concept=concept, visual=visual)
            for line in self._scene_cards(brief)
        ]
        logger.info("Generating %s motion clips via Replicate", len(prompts))
        urls = await asyncio.gather(
            *[self._replicate_clip_url(prompt, optimize=False) for prompt in prompts]
        )
        return [str(url) for url in urls]

    async def _generate_json2video(
        self, *, brief: dict, owner_id: str | None = None
    ) -> VideoGenerationResult:
        settings = get_settings()
        api_key = (settings.json2video_api_key or "").strip()
        if not api_key:
            raise VideoProviderNotConfiguredError(
                "JSON2VIDEO_API_KEY is not configured. Set JSON2VIDEO_API_KEY "
                "and VIDEO_GENERATION_PROVIDER=json2video."
            )

        # Silent Replicate clips cannot match TTS timing. JSON2Video generates
        # each talking shot from the spoken line so the scene lasts as long as
        # the voice.
        movie = self._json2video_movie(brief)
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
        }

        scene_count = len(movie.get("scenes") or [])
        logger.info(
            "Starting JSON2Video render resolution=%s scenes=%s poll_budget=%ss",
            JSON2VIDEO_RESOLUTION,
            scene_count,
            int(_JSON2VIDEO_POLL_SECONDS * _JSON2VIDEO_MAX_POLLS),
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                create = await client.post(
                    f"{JSON2VIDEO_API_BASE}/movies",
                    headers=headers,
                    json=movie,
                )
            except httpx.HTTPError as exc:
                raise VideoGenerationError(
                    f"JSON2Video request failed: {exc}"
                ) from exc

            if create.status_code in {401, 402, 429}:
                detail = (create.text or "")[:300]
                raise VideoRateLimitError(
                    "JSON2Video quota/auth issue. Check free-tier credits or API key. "
                    f"HTTP {create.status_code}: {detail}"
                )
            if create.status_code >= 400:
                raise VideoGenerationError(
                    f"JSON2Video create failed HTTP {create.status_code}: "
                    f"{(create.text or '')[:400]}"
                )

            try:
                created = create.json()
            except ValueError as exc:
                raise VideoGenerationError(
                    "JSON2Video create returned invalid JSON"
                ) from exc

            project_id = created.get("project") or created.get("projectId")
            if not project_id:
                raise VideoGenerationError(
                    "JSON2Video response missing project id — refusing to invent a video."
                )

            movie_status: dict = {}
            status = ""
            poll_errors = 0
            for attempt in range(1, _JSON2VIDEO_MAX_POLLS + 1):
                await asyncio.sleep(_JSON2VIDEO_POLL_SECONDS)
                try:
                    poll = await client.get(
                        f"{JSON2VIDEO_API_BASE}/movies",
                        headers={"x-api-key": api_key},
                        params={"project": project_id},
                    )
                except httpx.HTTPError as exc:
                    poll_errors += 1
                    logger.warning(
                        "JSON2Video poll error %s/5 for %s: %s",
                        poll_errors,
                        project_id,
                        type(exc).__name__,
                    )
                    if poll_errors >= 5:
                        raise VideoGenerationError(
                            f"JSON2Video status poll failed: {exc}"
                        ) from exc
                    continue
                if poll.status_code >= 400:
                    poll_errors += 1
                    if poll_errors >= 5:
                        raise VideoGenerationError(
                            f"JSON2Video status poll HTTP {poll.status_code}: "
                            f"{(poll.text or '')[:300]}"
                        )
                    continue
                poll_errors = 0
                try:
                    payload = poll.json()
                except ValueError as exc:
                    raise VideoGenerationError(
                        "JSON2Video status returned invalid JSON"
                    ) from exc
                movie_status = payload.get("movie") if isinstance(payload, dict) else None
                if not isinstance(movie_status, dict):
                    movie_status = payload if isinstance(payload, dict) else {}
                status = str(movie_status.get("status") or "").lower()
                if attempt == 1 or attempt % 6 == 0 or status in {
                    "done",
                    "error",
                    "timeout",
                    "failed",
                }:
                    logger.info(
                        "JSON2Video project %s status=%s poll=%s/%s",
                        project_id,
                        status,
                        attempt,
                        _JSON2VIDEO_MAX_POLLS,
                    )
                if status in {"done", "error", "timeout", "failed"}:
                    break
            else:
                raise VideoGenerationError(
                    f"JSON2Video project {project_id} was still rendering after "
                    f"{int(_JSON2VIDEO_POLL_SECONDS * _JSON2VIDEO_MAX_POLLS / 60)} minutes. "
                    "AI video scenes take several minutes each — retry the Short."
                )

        if status == "timeout":
            raise VideoGenerationError(
                "JSON2Video stopped the render after its time limit. "
                "Retry — shorter 3-scene Shorts usually complete."
            )
        if status != "done":
            err = movie_status.get("message") or movie_status.get("error") or status
            raise VideoGenerationError(f"JSON2Video render failed: {err}")

        remote_url = (
            movie_status.get("url")
            or movie_status.get("video_url")
            or movie_status.get("movieUrl")
        )
        if not isinstance(remote_url, str) or not remote_url.startswith("http"):
            raise VideoGenerationError(
                "JSON2Video render succeeded but output URL is missing — "
                "refusing to invent a video."
            )

        stored = await self._persist_remote_video(remote_url, owner_id=owner_id)
        return VideoGenerationResult(
            video_url=stored["url"],
            storage_key=stored["storage_key"],
            thumbnail_url=None,
            provider="json2video",
            raw={
                "json2video_project": project_id,
                "json2video_url": remote_url,
                "resolution": JSON2VIDEO_RESOLUTION,
                "status": status,
            },
        )

    def _prompt_from_brief(self, brief: dict) -> str:
        concept = (brief.get("concept") or "").strip()
        visual = (brief.get("visual_direction") or "").strip()
        scenes = brief.get("scenes") or []
        narration = (brief.get("narration") or "").strip()
        scene_line = "; ".join(str(s).strip() for s in scenes if str(s).strip())
        parts = [
            concept,
            f"Visual direction: {visual}" if visual else "",
            f"Scenes: {scene_line}" if scene_line else "",
            f"Narration intent: {narration[:600]}" if narration else "",
            "Vertical 9:16 YouTube Shorts, centered medium shot, full character "
            "in frame with headroom. Same character and setting across the clip. "
            "Story acting, not a generic colorful void. No on-screen text.",
        ]
        prompt = "\n".join(p for p in parts if p).strip()
        if not prompt:
            raise VideoGenerationError(
                "Video brief is empty — refusing to call Replicate without a prompt."
            )
        return prompt

    @staticmethod
    def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    def _vertical_first_frame_data_uri(self) -> str:
        """Build a 9:16 PNG so minimax outputs vertical video with a center stage."""
        global _VERTICAL_FRAME_DATA_URI
        if _VERTICAL_FRAME_DATA_URI is not None:
            return _VERTICAL_FRAME_DATA_URI

        width, height = SHORT_FRAME_WIDTH, SHORT_FRAME_HEIGHT
        sky = bytes((135, 206, 250))
        ground = bytes((126, 200, 122))
        stage = bytes((255, 236, 179))
        horizon = int(height * 0.62)
        cx, cy = width / 2.0, height * 0.55
        rx, ry = width * 0.28, height * 0.20
        rows: list[bytes] = []
        for y in range(height):
            row = bytearray()
            for x in range(width):
                dx = (x - cx) / rx
                dy = (y - cy) / ry
                if dx * dx + dy * dy <= 1.0:
                    row.extend(stage)
                elif y < horizon:
                    row.extend(sky)
                else:
                    row.extend(ground)
            rows.append(b"\x00" + bytes(row))
        raw = b"".join(rows)
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        png = (
            b"\x89PNG\r\n\x1a\n"
            + self._png_chunk(b"IHDR", ihdr)
            + self._png_chunk(b"IDAT", zlib.compress(raw, 9))
            + self._png_chunk(b"IEND", b"")
        )
        encoded = base64.b64encode(png).decode("ascii")
        _VERTICAL_FRAME_DATA_URI = f"data:image/png;base64,{encoded}"
        return _VERTICAL_FRAME_DATA_URI

    def _replicate_request(
        self, model_id: str | None, input_payload: dict
    ) -> tuple[str, dict]:
        custom = (model_id or "").strip()
        if custom and re.fullmatch(r"[0-9a-fA-F]{64}", custom):
            return (
                f"{REPLICATE_API_BASE}/predictions",
                {"version": custom, "input": input_payload},
            )
        if custom and "/" in custom:
            return (
                f"{REPLICATE_API_BASE}/models/{custom}/predictions",
                {"input": input_payload},
            )
        return (
            f"{REPLICATE_API_BASE}/predictions",
            {"version": REPLICATE_VERSION, "input": input_payload},
        )

    async def _replicate_clip_url(
        self,
        prompt: str,
        *,
        optimize: bool = True,
        api_token: str | None = None,
        model_id: str | None = None,
    ) -> str:
        """Run one Replicate text-to-video prediction and return the MP4 URL."""
        settings = get_settings()
        token = (api_token or settings.replicate_api_token or "").strip()
        if not token:
            raise VideoProviderNotConfiguredError(
                "Replicate is not configured. Save an API key in Settings → "
                "Integrations, or set REPLICATE_API_TOKEN on the backend."
            )

        input_payload = {
            "prompt": prompt,
            "prompt_optimizer": optimize,
            "first_frame_image": self._vertical_first_frame_data_uri(),
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "respond-async",
        }
        create_url, body = self._replicate_request(model_id, input_payload)

        logger.info(
            "Starting Replicate prediction model=%s first_frame=%sx%s",
            (model_id or REPLICATE_MODEL),
            SHORT_FRAME_WIDTH,
            SHORT_FRAME_HEIGHT,
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                create = await client.post(
                    create_url,
                    headers=headers,
                    json=body,
                )
            except httpx.HTTPError as exc:
                raise VideoGenerationError(
                    f"Replicate request failed: {exc}"
                ) from exc

            if create.status_code == 429:
                raise VideoRateLimitError(
                    "Replicate rate limit exceeded. Try again shortly."
                )
            if create.status_code == 402:
                raise VideoRateLimitError(
                    "Replicate payment required (HTTP 402). Add billing credits at "
                    "replicate.com/account/billing and retry."
                )
            if create.status_code >= 400:
                detail = (create.text or "")[:400]
                lowered = detail.lower()
                if "insufficient credit" in lowered or "payment" in lowered:
                    raise VideoRateLimitError(
                        "Replicate billing/credits issue. Top up and retry."
                    )
                raise VideoGenerationError(
                    f"Replicate create prediction failed HTTP {create.status_code}: {detail}"
                )

            prediction = create.json()
            prediction_id = prediction.get("id")
            if not prediction_id:
                raise VideoGenerationError(
                    "Replicate response missing prediction id — refusing to invent a video."
                )

            status = prediction.get("status")
            for _ in range(_MAX_POLL_ATTEMPTS):
                if status in {"succeeded", "failed", "canceled"}:
                    break
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                try:
                    poll = await client.get(
                        f"{REPLICATE_API_BASE}/predictions/{prediction_id}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                except httpx.HTTPError as exc:
                    raise VideoGenerationError(
                        f"Replicate status poll failed: {exc}"
                    ) from exc
                if poll.status_code == 429:
                    raise VideoRateLimitError(
                        "Replicate rate limit exceeded while polling. Try again shortly."
                    )
                if poll.status_code >= 400:
                    raise VideoGenerationError(
                        f"Replicate status poll HTTP {poll.status_code}: {(poll.text or '')[:300]}"
                    )
                prediction = poll.json()
                status = prediction.get("status")
                logger.info(
                    "Replicate prediction %s status=%s", prediction_id, status
                )
            else:
                raise VideoGenerationError(
                    f"Replicate prediction {prediction_id} timed out while processing."
                )

        if status != "succeeded":
            err = prediction.get("error") or status
            raise VideoGenerationError(f"Replicate prediction failed: {err}")

        remote_url = self._extract_output_url(prediction.get("output"))
        if not remote_url:
            raise VideoGenerationError(
                "Replicate prediction succeeded but output URL is missing — "
                "refusing to invent a video."
            )
        return str(remote_url)

    async def _generate_replicate(
        self,
        *,
        brief: dict,
        owner_id: str | None = None,
        stored: dict | None = None,
    ) -> VideoGenerationResult:
        api_token = stored.get("api_key") if stored else None
        model_id = stored.get("model_id") if stored else None
        remote_url = await self._replicate_clip_url(
            self._prompt_from_brief(brief),
            api_token=api_token,
            model_id=model_id,
        )
        stored_file = await self._persist_remote_video(
            str(remote_url), owner_id=owner_id
        )
        return VideoGenerationResult(
            video_url=stored_file["url"],
            storage_key=stored_file["storage_key"],
            thumbnail_url=None,
            provider="replicate",
            raw={
                "replicate_output_url": str(remote_url),
                "model": model_id or REPLICATE_MODEL,
                "version": REPLICATE_VERSION,
            },
        )

    @staticmethod
    def _extract_output_url(output) -> str | None:
        if isinstance(output, str) and output.startswith("http"):
            return output
        if isinstance(output, list):
            for item in output:
                if isinstance(item, str) and item.startswith("http"):
                    return item
        if isinstance(output, dict):
            for key in ("url", "video", "video_url"):
                value = output.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value
        return None

    async def _persist_remote_video(
        self, remote_url: str, *, owner_id: str | None = None
    ) -> dict:
        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                response = await client.get(remote_url)
                response.raise_for_status()
                data = response.content
        except httpx.HTTPError as exc:
            raise VideoGenerationError(
                f"Failed to download generated video: {exc}"
            ) from exc

        if not data:
            raise VideoGenerationError("Downloaded video file is empty.")

        try:
            return self._storage.save_bytes(
                data=data,
                suffix=".mp4",
                prefix="videos",
                owner_id=owner_id,
            )
        except Exception as exc:
            # Provider already produced a real MP4. Storage failure must not
            # hide the video from the workspace.
            logger.warning(
                "Storage persist failed (%s); using provider URL instead.",
                type(exc).__name__,
            )
            return {"storage_key": None, "url": remote_url}

    async def _generate_http(
        self, *, brief: dict, format: str, owner_id: str | None = None
    ) -> VideoGenerationResult:
        settings = get_settings()
        api_key = settings.video_generation_api_key
        api_url = settings.video_generation_api_url
        if not api_key or not api_url:
            raise VideoProviderNotConfiguredError(
                "VIDEO_GENERATION_API_KEY and VIDEO_GENERATION_API_URL are required "
                "when VIDEO_GENERATION_PROVIDER=http."
            )

        payload = {"format": format, "brief": brief}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code == 429:
                    raise VideoRateLimitError(
                        "Video provider rate limit exceeded. Try again shortly."
                    )
                response.raise_for_status()
                data = response.json()
        except VideoRateLimitError:
            raise
        except httpx.HTTPStatusError as exc:
            detail = (exc.response.text or "")[:300]
            raise VideoGenerationError(
                f"Video provider returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise VideoGenerationError(f"Video provider request failed: {exc}") from exc
        except ValueError as exc:
            raise VideoGenerationError("Video provider returned invalid JSON") from exc

        video_url = data.get("video_url") or data.get("url")
        if not video_url:
            raise VideoGenerationError(
                "Video provider response missing video_url — refusing to invent one."
            )
        return VideoGenerationResult(
            video_url=str(video_url),
            storage_key=data.get("storage_key"),
            thumbnail_url=data.get("thumbnail_url"),
            provider="http",
            raw=data if isinstance(data, dict) else None,
        )
