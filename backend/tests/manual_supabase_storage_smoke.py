"""Live Supabase Storage smoke (requires SUPABASE_SECRET_KEY).

  .venv\\Scripts\\python.exe tests/manual_supabase_storage_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.storage_service import StorageService


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    print("backend=", settings.storage_backend)
    print("url=", settings.supabase_url)
    if not settings.supabase_secret_key and not settings.supabase_key:
        print(
            "BLOCKED: Set SUPABASE_SECRET_KEY in .env to the project's "
            "secret/service_role key (not the publishable key), then re-run."
        )
        return 2

    owner = f"smoke-{uuid4()}"
    svc = StorageService()
    result = svc.save_bytes(
        data=b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64,
        owner_id=owner,
        suffix=".mp4",
        content_type="video/mp4",
    )
    print("storage_key=", result["storage_key"])
    print("signed_url=", result["url"][:120], "...")
    svc.assert_owner_path(result["storage_key"], owner)
    refreshed = svc.create_signed_url(result["storage_key"])
    print("refresh_ok=", refreshed.startswith("http"))
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
