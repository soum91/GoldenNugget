#!/usr/bin/env python3
"""End-to-end (offline) regression for the 2026-11-10 Mond report.

A real format-3, community-only windowing .batter is built on disk, imported
through TemplatesTweak.add_template exactly as the Templates page does, and
then pushed through:

  1. preflight_apply   - the new pre-backup check; must pass, must say no
                         PosterBoard DB is needed;
  2. compile_tweaks    - the real compiler; must NOT invoke PosterBoard
                         staging, and MUST hand the windowing key to the
                         community writer (proves the tweak is applied, not
                         merely that PosterBoard was skipped);
  3. negative cases    - a template that cannot run on the device and a
                         PosterBoard routing regression must fail in preflight
                         (before any backup), tagged as such.

No device, network or backup is used. Passing this is NOT device validation.

Run: python tools/test_mond_apply_preflight.py
"""
import asyncio
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from src.controllers.apply_preflight import ApplyPreflightError, preflight_apply  # noqa: E402
from src.controllers.tweak_compiler import CompilationContext, compile_tweaks  # noqa: E402
from src.devicemanagement.posterboard_intent import (  # noqa: E402
    is_posterboard_template, needs_posterboard_database,
)
from src.tweaks.posterboard.posterboard_tweak import PosterboardTweak  # noqa: E402
from src.tweaks.posterboard.template_options.templates_tweak import TemplatesTweak  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402

SB = "/var/Managed Preferences/mobile/com.apple.springboard.plist"
VERSION = "27.0.1"


def build_batter(directory: str, name: str, config: dict) -> str:
    path = os.path.join(directory, name)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("config.json", json.dumps(config))
    return path


MOND = {
    "title": "Mond iOS 27 Windowing (fixture)", "author": "fixture",
    "format_version": "3", "min_version": "27.0",
    "description": "Community-only windowing template, no wallpaper payload.",
    "tweaks": [{
        "id": "HybridWindowing", "label": "Hybrid windowing", "default": False,
        "min_version": "27.0",
        "writes": [{"type": "plist", "path": SB,
                    "values": {"SBChamoisWindowingEnabled": True}}],
        "writes_off": [{"type": "plist", "path": SB,
                        "values": {"SBChamoisWindowingEnabled": False}}],
    }],
}


class FakeHotLoad:
    def hidden_tweak_names(self, **_):
        return set()

    def rule_for(self, *_, **__):
        return None

    def disabled_daemon_keys(self, **_):
        return set()


def store_with(templates_tweak, pb):
    return {TweakID.Templates: templates_tweak, TweakID.PosterBoard: pb}


async def compile_store(store, templates):
    captured = {}

    async def prepare_setup(*_):
        return None

    def add_community_files(plists, files, files_to_restore, is_ios27):
        captured["plists"] = dict(plists)
        captured["files"] = dict(files)

    context = CompilationContext(
        store=store, version=VERSION, model="iPad16,2", templates=templates,
        force_pb_refresh=True, prepare_setup=prepare_setup,
        concat_file=lambda **_: None, add_community_files=add_community_files,
        update_label=lambda *_: None)
    artifacts = await compile_tweaks(context, FakeHotLoad())
    try:
        return artifacts, captured
    finally:
        artifacts.close()


def main():
    QCoreApplication.instance() or QCoreApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        templates_tweak = TemplatesTweak()
        mond = templates_tweak.add_template(build_batter(tmp, "Mond.batter", MOND), VERSION)
        assert mond.domain == "", f"community-only template got domain {mond.domain!r}"
        assert not is_posterboard_template(mond)
        mond.tweaks[0].enabled = True  # user switched Hybrid windowing on

        pb = PosterboardTweak()

        # PosterBoard must refuse to touch its DB for this selection at all.
        def no_db():
            raise AssertionError("PosterBoard DB requested for a community-only apply")
        pb.config_manager.update_sqlite = no_db

        store = store_with(templates_tweak, pb)

        # 1. preflight passes before any backup and says no DB is needed
        report = preflight_apply(store, VERSION)
        assert report.needs_posterboard_database is False
        assert report.posterboard_changes is False
        assert report.community_templates == [mond.name]
        assert report.community_write_targets == 1
        assert needs_posterboard_database(pb, templates_tweak.templates) is False

        # 2. the real compiler applies the windowing key and skips PosterBoard
        artifacts, captured = asyncio.run(compile_store(store, templates_tweak.templates))
        assert artifacts.files == [], f"unexpected staged files: {artifacts.files}"
        assert captured["plists"].get(SB, ({}, 0))[0] == {"SBChamoisWindowingEnabled": True}, captured
        assert artifacts.uses_domains, "community writes must request domain delivery"

        # switched off -> writes_off, still no PosterBoard
        mond.tweaks[0].enabled = False
        _, captured = asyncio.run(compile_store(store, templates_tweak.templates))
        assert captured["plists"][SB][0] == {"SBChamoisWindowingEnabled": False}

        # case/whitespace variants of the PosterBoard domain route consistently
        class T:
            def __init__(self, domain):
                self.domain = domain
        for domain in ("AppDomain-com.apple.PosterBoard", " appdomain-com.apple.posterboard ",
                       "com.apple.PosterBoard"):
            assert is_posterboard_template(T(domain)), domain
        for domain in ("", None, "AppDomain-com.apple.springboard", "Sparserestore-/var/x"):
            assert not is_posterboard_template(T(domain)), domain

        # 3a. a template the device cannot run fails in PREFLIGHT, not after backup
        old = dict(MOND, title="Old", max_version="26.9")
        stale = TemplatesTweak()
        stale.add_template(build_batter(tmp, "Old.batter", old))  # no device version at import
        try:
            preflight_apply(store_with(stale, PosterboardTweak()), VERSION)
            raise AssertionError("preflight accepted a template that rejects iOS 27.0.1")
        except ApplyPreflightError as exc:
            assert "does not support iOS 27.0.1" in str(exc)
            assert "before any backup or restore started" in str(exc)

        # 3b. if PosterBoard routing ever regresses, preflight catches it pre-backup
        regressed = PosterboardTweak()
        regressed.resetModes = ["Gallery Cache"]  # legit reset, no DB fetched
        def broken_apply(**_):
            raise RuntimeError("PosterBoard database file not selected!")
        regressed.apply_tweak = broken_apply
        try:
            preflight_apply(store_with(templates_tweak, regressed), VERSION)
            raise AssertionError("preflight missed a DB-less PosterBoard routing failure")
        except ApplyPreflightError as exc:
            assert "routed incorrectly" in str(exc)
            assert "PosterBoard database file not selected!" in exc.detail

        # 3c. stage-aware error text: compile failures never read as "restore failed"
        from src.devicemanagement.device_manager import APPLY_STAGE_ATTR, show_apply_error
        labels = []
        err = RuntimeError("boom")
        setattr(err, APPLY_STAGE_ATTR, "compile")
        alert = show_apply_error(err, labels.append)
        assert labels[-1].startswith("Failed while preparing tweaks"), labels
        assert "before the device restore started" in alert.txt, alert.txt

    real_mond_file_template()
    print("MOND_PREFLIGHT_OK: community windowing .batter compiles to its SpringBoard key, "
          "never touches PosterBoard, and deterministic errors fail before backup")


REAL_MOND = Path(__file__).resolve().parent.parent / "docs/diagnostics/evidence/Mond-iPhone-Windowing-Mobile.batter"


def real_mond_file_template():
    """The actual user-supplied Mond package (format 2, ManagedPreferencesDomain,
    whole com.apple.springboard.plist behind an inverted remove option)."""
    from src.restore.restore import merge_duplicates
    from src.utils.file_to_restore import FileToRestore
    import plistlib

    templates_tweak = TemplatesTweak()
    mond = templates_tweak.add_template(str(REAL_MOND), VERSION)
    assert mond.domain == "ManagedPreferencesDomain" and mond.format_version == 2
    assert not is_posterboard_template(mond)
    pb = PosterboardTweak()
    def no_db():
        raise AssertionError("PosterBoard DB requested for the real Mond package")
    pb.config_manager.update_sqlite = no_db
    store = store_with(templates_tweak, pb)

    for enabled, expect in ((True, 1), (False, 0)):
        mond.options[0].value = enabled
        report = preflight_apply(store, VERSION)
        assert report.needs_posterboard_database is False and report.posterboard_changes is False
        assert report.file_templates == [mond.name]

        async def run():
            async def prepare_setup(*_):
                return None
            context = CompilationContext(
                store=store, version=VERSION, model="iPhone18,3", templates=templates_tweak.templates,
                force_pb_refresh=True, prepare_setup=prepare_setup,
                concat_file=lambda **_: None, add_community_files=lambda *_: None,
                update_label=lambda *_: None)
            artifacts = await compile_tweaks(context, FakeHotLoad())
            try:
                staged = [(f.domain, f.restore_path, plistlib.loads(open(f.contents_path, "rb").read()))
                          for f in artifacts.files]
                if staged:
                    # Same plist also written by a built-in SpringBoard tweak:
                    # merge_duplicates used to TypeError on the path-backed
                    # template payload, after the protective backup.
                    builtin = FileToRestore(contents=plistlib.dumps({"SBHideDock": True}),
                                            restore_path="mobile/com.apple.springboard.plist",
                                            domain="ManagedPreferencesDomain")
                    merged = merge_duplicates(list(artifacts.files) + [builtin])
                    assert len(merged) == 1, merged
                    assert plistlib.loads(merged[0].contents) == {
                        "SBChamoisWindowingEnabled": True, "SBMedusaMultitaskingEnabled": True,
                        "SBHideDock": True}
                return staged
            finally:
                artifacts.close()

        staged = asyncio.run(run())
        assert len(staged) == expect, staged
        if staged:
            assert staged[0][:2] == ("ManagedPreferencesDomain", "/mobile/com.apple.springboard.plist")
            assert staged[0][2] == {"SBChamoisWindowingEnabled": True, "SBMedusaMultitaskingEnabled": True}

    # Wrong iOS build: the package pins 27.0.1 exactly -> preflight, not post-backup.
    try:
        preflight_apply(store, "27.1")
        raise AssertionError("preflight accepted Mond on iOS 27.1")
    except ApplyPreflightError as exc:
        assert "does not support iOS 27.1" in str(exc)


if __name__ == "__main__":
    main()
