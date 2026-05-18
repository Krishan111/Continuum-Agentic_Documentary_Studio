#!/usr/bin/env python3
"""Create a VideoDB sandbox for OmniVoice and print env vars for continuum/.env."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

try:
    from videodb import SandboxTier, connect  # noqa: E402
except ImportError as exc:
    print(
        "Wrong videodb package — SandboxTier needs the hackathon SDK.\n"
        "Use the backend venv Python (after: cd backend && pip install -r requirements.txt):\n"
        "  ..\\backend\\.venv\\Scripts\\python.exe scripts\\create_sandbox.py\n"
        f"\nOriginal error: {exc}"
    )
    sys.exit(1)


def main() -> None:
    if not os.getenv("VIDEO_DB_API_KEY"):
        print("Set VIDEO_DB_API_KEY in continuum/.env first.")
        sys.exit(1)

    tier = os.getenv("VIDEO_DB_SANDBOX_TIER", "small")
    print(f"Creating sandbox (tier={tier})…")
    conn = connect()
    sandbox = conn.create_sandbox(tier=tier, name="continuum-voice")
    print(f"  id: {sandbox.id}")
    print(f"  status: {sandbox.status}")
    print("Waiting until active (up to 5 min)…")
    sandbox.wait_for_ready(timeout=300, interval=5)
    sandbox.refresh()
    print(f"  status: {sandbox.status}")

    print("\nAdd to continuum/.env:\n")
    print("VIDEO_DB_USE_SANDBOX_VOICE=1")
    print(f"VIDEO_DB_SANDBOX_ID={sandbox.id}")
    print("VIDEO_DB_SANDBOX_AUTO_CREATE=0")
    print("\nThen reinstall deps and restart the backend:")
    print("  cd backend && pip install -r requirements.txt")
    print("  ..\\scripts\\run_backend.ps1")


if __name__ == "__main__":
    main()
