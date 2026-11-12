# Changelog

## Unreleased (2026-11-10)

### Fixed

- Desktop GoldenNugget no longer treats every imported `.batter` template as a PosterBoard wallpaper change. Community-tweak-only format-3 templates (including Mond's iOS 27 windowing experiment) now bypass the unrelated PosterBoard encrypted-backup restriction.
- Both the apply preflight and targeted PosterBoard database backup use the same selection check. Actual tendies, wallpaper videos and PosterBoard-domain templates still request the database; other app-domain templates do not.
- Fixed a second, later PosterBoard error after a completed protective backup: the compiler and PosterBoard staging now skip unrelated community `.batter` templates, preventing the misleading `PosterBoard database file not selected!` failure. Explicit wallpaper resets and actual PosterBoard imports remain enabled.

- Deterministic apply errors now fail **before** the protective backup instead of after it. A new device-free preflight (`src/controllers/apply_preflight.py`) runs ahead of Phase 0 and checks template iOS version bounds, community tweak write resolution, file-carrying template staging, PosterBoard routing for selections that will not fetch the database, and the PosterKit/wallpaper conflict. A failure reports that no backup or restore started. The protective backup itself is unchanged.
- Template routing now uses one shared `is_posterboard_template()` check (case and whitespace tolerant) in the backup decision, compiler, `PosterboardTweak` and `TemplatesTweak`, so the four can no longer disagree about whether a template needs PosterBoard.
- PosterKit overrides are no longer blocked just because a community-only `.batter` is loaded; only real wallpaper imports and resets conflict with them.
- Apply failures now say where they happened. A tweak compile failure reports that it happened before the device restore started and that nothing was restored, instead of the generic "Failed to restore".

- Fixed a second post-backup crash: when a file template (such as the real Mond iPhone windowing package, which ships `ManagedPreferencesDomain/mobile/com.apple.springboard.plist`) and a built-in tweak wrote the same plist, `merge_duplicates` read the path-backed template payload as `None` and raised `InvalidFileException` at the start of the restore. It now reads the template file, uses it as the base and merges built-in keys on top.

- New `GoldenNugget rescue` command for a SpringBoard boot loop (the Mond iPhone windowing package boot-looped an iPhone 17 on iOS 27.0.1, 2026-11-12). It waits for the device and, the moment usbmux lists it, sends a one-file partial restore: an empty dictionary plist over `ManagedPreferencesDomain/mobile/com.apple.springboard.plist` (`--uikit` adds `com.apple.UIKit.plist`). It uses the existing no-protective-backup single pass (no iOS 27 three-phase flow, no security wipe) and retries every boot cycle. Each attempt is classified as LOCKED (not unlocked since boot), FIND MY, DROPPED or OTHER, and logged to `goldennugget-rescue.log` on the Desktop. On Windows the windowed build opens its own console for it. Offline-tested only; not device-verified.

### Verified

- `tools/test_mond_apply_preflight.py` now also runs the user-supplied Mond package (`docs/diagnostics/evidence/Mond-iPhone-Windowing-Mobile.batter`, format 2, `ManagedPreferencesDomain`). Ticked, it stages exactly that springboard plist with `SBChamoisWindowingEnabled` and `SBMedusaMultitaskingEnabled`; unticked, nothing. PosterBoard is never touched, iOS 27.1 is refused in preflight, and the duplicate merge with a built-in SpringBoard key succeeds (it fails on the previous code).

- Added `tools/test_mond_apply_preflight.py`: builds a real format-3 community windowing `.batter`, imports it through `TemplatesTweak`, and runs preflight plus the real `compile_tweaks`. It asserts `SBChamoisWindowingEnabled` reaches the community writer (on and off states), PosterBoard never requests its database, and version-incompatible templates and PosterBoard routing regressions fail in preflight. Offline only; not device validation.
- Added `tools/test_posterboard_intent.py`, an offline regression suite for tweak-only templates, non-PosterBoard domains, both PosterBoard domain spellings, tendies and videos.
- Added `tools/test_posterboard_compile.py` to exercise the previously failing compile route directly; the Windows build workflow runs both suites before packaging.
- This is a desktop source change. Existing GoldenNugget executable downloads will not include it until rebuilt.
