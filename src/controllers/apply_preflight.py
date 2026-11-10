"""Cheap, device-free checks that must pass BEFORE the protective backup.

The 2026-11-10 Mond report: a community-only windowing .batter sat through a
3+ hour protective backup, then died at "Adding tendies..." with
``PosterBoard database file not selected!``. Every input needed to predict
that failure was known before the backup started. This module runs the
template/compiler routing that would otherwise first execute after the
backup, so a deterministic error surfaces in seconds instead of hours.

What it checks (nothing here talks to the device or weakens protection):
  * every template supports the target iOS version (TemplatesTweak would
    raise the same ValueError after the backup);
  * every community tweak resolves to plist/file writes for that version;
  * file-carrying templates extract and stage cleanly;
  * PosterBoard routing is consistent: when the DB will NOT be fetched,
    PosterboardTweak.apply_tweak must stage nothing that needs it;
  * PosterKit overrides are not combined with real wallpaper work.

What it does NOT do: skip, shorten or reuse the protective backup, or
predict device-side restore failures. Passing preflight is not proof the
apply will succeed on the device.
"""
from dataclasses import dataclass, field
from tempfile import TemporaryDirectory

from src.devicemanagement.posterboard_intent import (
    has_posterboard_changes, is_posterboard_template, needs_posterboard_database,
)
from src.exceptions.nugget_exception import NuggetException
from src.tweaks.tweak_names import TweakID

NOTHING_STARTED = ("Preflight stopped the apply before any backup or restore "
                   "started. Your device was not changed.")


class ApplyPreflightError(NuggetException):
    """A deterministic apply error detected before the protective backup."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(f"{message}\n\n{NOTHING_STARTED}", detailed_text=detail or None)
        self.preflight_message = message
        self.detail = detail


@dataclass
class PreflightReport:
    needs_posterboard_database: bool = False
    posterboard_changes: bool = False
    community_templates: list = field(default_factory=list)
    posterboard_templates: list = field(default_factory=list)
    file_templates: list = field(default_factory=list)
    community_write_targets: int = 0

    def summary(self) -> str:
        return (f"preflight ok: needs_posterboard_db={self.needs_posterboard_database} "
                f"posterboard_changes={self.posterboard_changes} "
                f"community_templates={self.community_templates} "
                f"posterboard_templates={self.posterboard_templates} "
                f"file_templates={self.file_templates} "
                f"community_write_targets={self.community_write_targets}")


def _version_ok(template, version) -> bool:
    from src.devicemanagement.constants import Version
    if getattr(template, "min_version", None) and Version(version) < Version(template.min_version):
        return False
    if getattr(template, "max_version", None) and Version(version) > Version(template.max_version):
        return False
    return True


def preflight_apply(store, version: str) -> PreflightReport:
    """Raise ApplyPreflightError for any failure that is certain before backup."""
    report = PreflightReport()
    templates_tweak = store.get(TweakID.Templates)
    templates = list(getattr(templates_tweak, "templates", []) or [])
    pb = store.get(TweakID.PosterBoard)

    for template in templates:
        name = getattr(template, "name", "template")
        if not _version_ok(template, version):
            raise ApplyPreflightError(
                f"Template {name} does not support iOS {version}.",
                f"min_version={getattr(template, 'min_version', None)} "
                f"max_version={getattr(template, 'max_version', None)}")
        if is_posterboard_template(template):
            report.posterboard_templates.append(name)
        elif getattr(template, "domain", ""):
            report.file_templates.append(name)
        if getattr(template, "tweaks", None):
            report.community_templates.append(name)

    if templates_tweak is not None and templates:
        try:
            plists, files = templates_tweak.community_writes(version)
        except Exception as exc:
            raise ApplyPreflightError(
                "A community tweak in an imported template could not be prepared.",
                f"{type(exc).__name__}: {exc}") from exc
        report.community_write_targets = len(plists) + len(files)

        # Stage file-carrying (non-PosterBoard) templates exactly as the real
        # compile would, into a throwaway directory. Catches unreadable or
        # corrupt payloads that would otherwise fail after the backup.
        if report.file_templates:
            with TemporaryDirectory() as tmp:
                try:
                    templates_tweak.apply_tweak(
                        files_to_restore=[], output_dir=tmp, templates=templates,
                        version=version, force_pb_refresh=False)
                except Exception as exc:
                    raise ApplyPreflightError(
                        "An imported template's files could not be prepared.",
                        f"{type(exc).__name__}: {exc}") from exc

    if pb is not None:
        report.needs_posterboard_database = needs_posterboard_database(pb, templates)
        report.posterboard_changes = has_posterboard_changes(pb, templates)
        if report.posterboard_changes and not report.needs_posterboard_database:
            # Reset-only (or, defensively, any non-DB) PosterBoard work must
            # stage without the database the backup will not fetch. This is
            # the exact path that failed for Mond; run it now, not post-backup.
            staged = []
            with TemporaryDirectory() as tmp:
                try:
                    pb.apply_tweak(files_to_restore=staged, output_dir=tmp,
                                   templates=templates, version=version,
                                   force_pb_refresh=False)
                except Exception as exc:
                    raise ApplyPreflightError(
                        "PosterBoard work was routed incorrectly for this selection "
                        "(it needs a database that will not be fetched).",
                        f"{type(exc).__name__}: {exc}") from exc

    posterkit = store.get(TweakID.PosterKitOverrides)
    if (posterkit is not None and getattr(posterkit, "enabled", False)
            and getattr(posterkit, "value", None) and report.posterboard_changes):
        raise ApplyPreflightError(
            "Apply PosterKit settings separately from wallpaper imports and resets.")
    return report
