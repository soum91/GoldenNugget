#!/usr/bin/env python3
"""Offline regression: tweak-only .batter imports must not invoke PosterBoard.

Run: python tools/test_posterboard_intent.py
"""

from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.devicemanagement.posterboard_intent import needs_posterboard_database


def main() -> int:
    blank = SimpleNamespace(tendies=[], videoFile=None)
    assert needs_posterboard_database(blank, []) is False

    # Mond's format-3 community-tweak-only template has no domain or files.
    mond = SimpleNamespace(domain="", tweaks=[object()])
    assert needs_posterboard_database(blank, [mond]) is False
    assert needs_posterboard_database(blank, [SimpleNamespace(tweaks=[object()])]) is False

    # Ordinary app container templates do not need the wallpaper sqlite.
    app = SimpleNamespace(domain="AppDomain-com.example.app")
    assert needs_posterboard_database(blank, [app]) is False

    # Both PosterBoard domain spellings still request the database.
    for domain in ("com.apple.PosterBoard", "AppDomain-com.apple.PosterBoard"):
        wallpaper = SimpleNamespace(domain=domain)
        assert needs_posterboard_database(blank, [wallpaper]) is True
        assert needs_posterboard_database(blank, [mond, wallpaper]) is True

    assert needs_posterboard_database(SimpleNamespace(tendies=[object()], videoFile=None), [mond]) is True
    assert needs_posterboard_database(SimpleNamespace(tendies=[], videoFile="clip.mov"), [mond]) is True

    print("POSTERBOARD_INTENT_OK: tweak-only skips DB; wallpapers still fetch DB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
