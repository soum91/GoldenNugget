"""Decide whether an apply needs the on-device PosterBoard database.

Imported .batter templates can contain only community preference tweaks.
Their presence in the Templates list must not trigger wallpaper backup work.

Every place that routes a template (device_manager's backup decision, the
tweak compiler, PosterboardTweak and TemplatesTweak) must use
``is_posterboard_template`` so the four can never disagree. The original
Mond failure (2026-11-10) was exactly such a disagreement: the backup skipped
the PosterBoard DB while the compiler still ran PosterBoard staging.
"""

_POSTERBOARD_DOMAINS = frozenset({
    "com.apple.posterboard",  # legacy domain spelling
    "appdomain-com.apple.posterboard",
})


def _normalized_domain(template) -> str:
    domain = getattr(template, "domain", "") or ""
    return domain.strip().lower() if isinstance(domain, str) else ""


def is_posterboard_template(template) -> bool:
    """True when a template's payload belongs in the PosterBoard container.

    Empty domains (community-tweak-only .batter files such as Mond's iOS 27
    windowing template), other app domains and Sparserestore domains are NOT
    PosterBoard templates. Matching is case/whitespace tolerant so a
    hand-edited config.json cannot slip between the routing checks."""
    return _normalized_domain(template) in _POSTERBOARD_DOMAINS


def needs_posterboard_database(posterboard, templates) -> bool:
    """True only for selected wallpapers or PosterBoard-domain templates."""
    return bool(
        getattr(posterboard, "tendies", None)
        or getattr(posterboard, "videoFile", None) is not None
        or any(is_posterboard_template(template) for template in (templates or ()))
    )


def has_posterboard_changes(posterboard, templates) -> bool:
    """Include explicit wallpaper resets, which do not need a database fetch."""
    return bool(
        getattr(posterboard, "full_reset", False)
        or getattr(posterboard, "resetModes", None)
        or needs_posterboard_database(posterboard, templates)
    )
