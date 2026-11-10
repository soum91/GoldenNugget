"""Decide whether an apply needs the on-device PosterBoard database.

Imported .batter templates can contain only community preference tweaks.
Their presence in the Templates list must not trigger wallpaper backup work.
"""

_POSTERBOARD_DOMAINS = frozenset({
    "com.apple.PosterBoard",  # legacy domain spelling
    "AppDomain-com.apple.PosterBoard",
})


def needs_posterboard_database(posterboard, templates) -> bool:
    """True only for selected wallpapers or PosterBoard-domain templates."""
    return bool(
        posterboard.tendies
        or posterboard.videoFile is not None
        or any(getattr(template, "domain", "") in _POSTERBOARD_DOMAINS
               for template in templates)
    )
