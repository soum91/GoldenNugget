# Changelog

## Unreleased (2026-11-10)

### Fixed

- Desktop GoldenNugget no longer treats every imported `.batter` template as a PosterBoard wallpaper change. Community-tweak-only format-3 templates (including Mond's iOS 27 windowing experiment) now bypass the unrelated PosterBoard encrypted-backup restriction.
- Both the apply preflight and targeted PosterBoard database backup use the same selection check. Actual tendies, wallpaper videos and PosterBoard-domain templates still request the database; other app-domain templates do not.
- Fixed a second, later PosterBoard error after a completed protective backup: the compiler and PosterBoard staging now skip unrelated community `.batter` templates, preventing the misleading `PosterBoard database file not selected!` failure. Explicit wallpaper resets and actual PosterBoard imports remain enabled.

### Verified

- Added `tools/test_posterboard_intent.py`, an offline regression suite for tweak-only templates, non-PosterBoard domains, both PosterBoard domain spellings, tendies and videos.
- Added `tools/test_posterboard_compile.py` to exercise the previously failing compile route directly; the Windows build workflow runs both suites before packaging.
- This is a desktop source change. Existing GoldenNugget executable downloads will not include it until rebuilt.
