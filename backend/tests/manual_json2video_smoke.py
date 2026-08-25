"""Live JSON2Video smoke (requires JSON2VIDEO_API_KEY).

  .venv\\Scripts\\python.exe tests/manual_json2video_smoke.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.video_generation_service import VideoGenerationService


async def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.json2video_api_key:
        print("BLOCKED: JSON2VIDEO_API_KEY missing")
        return 2

    print("provider=", settings.video_generation_provider)
    print("voice=", settings.json2video_voice)
    result = await VideoGenerationService().generate(
        brief={
            "concept": "A friendly fox teaches counting with forest friends",
            "titles": ["Count to 5 with Fox and Friends!"],
            "scenes": [
                "Cute fox waving hello in a sunny cartoon forest",
                "Fox and bunny counting three bright apples",
                "Happy animals celebrating with balloons and stars",
            ],
            "narration": (
                "Hi friends! Let's count with Fox. One, two, three shiny apples. "
                "Four and five make us smile. Great job counting today!"
            ),
            "visual_direction": "Pixar-style kids cartoon, bright pastels, soft lighting",
        },
        format="short",
        owner_id=f"smoke-{uuid4()}",
    )
    print("provider_result=", result.provider)
    print("storage_key=", result.storage_key)
    print("video_url=", (result.video_url or "")[:160])
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
