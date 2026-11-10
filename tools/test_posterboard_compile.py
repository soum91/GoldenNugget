#!/usr/bin/env python3
"""Regression: a format-3 community .batter cannot start PosterBoard staging.

Run after installing requirements: python tools/test_posterboard_compile.py
"""
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.controllers.tweak_compiler import CompilationContext, _Compilation, compile_one
from src.tweaks.posterboard.posterboard_tweak import PosterboardTweak
from src.tweaks.tweak_names import TweakID


def state_for(templates):
    context = CompilationContext(
        store={}, version="27.0.1", model="iPhone18,3",
        templates=templates, force_pb_refresh=False,
        prepare_setup=lambda *_: None,
        concat_file=lambda **_: None,
        add_community_files=lambda *_: None,
        update_label=lambda *_: None,
    )
    return _Compilation(context)


def main():
    # Mond is a community-tweak template, not an on-device wallpaper.
    mond = SimpleNamespace(domain="", tweaks=[object()])
    pb = PosterboardTweak()
    assert pb.tendies == []
    assert pb.videoFile is None

    # Direct apply_tweak was the original failure: even with no wallpapers,
    # it used to reach PBConfigManager.update_sqlite() and reject a missing DB.
    files = []
    pb.apply_tweak(files_to_restore=files, output_dir=".",
                   templates=[mond], version="27.0.1",
                   force_pb_refresh=False)
    assert files == [], "tweak-only template staged PosterBoard files"

    # The compiler must also skip creating a PosterBoard workspace at all.
    original = pb.apply_tweak
    def unexpected(**_):
        raise AssertionError("compiler invoked PosterBoard for Mond")
    pb.apply_tweak = unexpected
    state = state_for([mond])
    try:
        compile_one(pb, TweakID.PosterBoard, state)
        assert not state.artifacts.files
        assert not state.artifacts.temporary_dirs
    finally:
        state.artifacts.close()
        pb.apply_tweak = original

    # Wallpaper-domain templates must still reach the compiler.
    called = []
    pb.apply_tweak = lambda **_: called.append(True)
    state = state_for([SimpleNamespace(domain="com.apple.PosterBoard")])
    try:
        compile_one(pb, TweakID.PosterBoard, state)
        assert called and state.artifacts.uses_domains
    finally:
        state.artifacts.close()
        pb.apply_tweak = original

    # Explicit PosterBoard reset is a legitimate operation without a DB fetch.
    pb.full_reset = True
    called.clear()
    state = state_for([mond])
    pb.apply_tweak = lambda **_: called.append(True)
    try:
        compile_one(pb, TweakID.PosterBoard, state)
        assert called and state.artifacts.uses_domains
    finally:
        state.artifacts.close()
        pb.apply_tweak = original

    print("POSTERBOARD_COMPILE_OK: Mond skipped, wallpapers and resets preserved")


if __name__ == "__main__":
    main()
