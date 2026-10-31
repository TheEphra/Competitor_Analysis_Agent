"""Transparent, missing-data-aware scoring for website and competitor signals."""

from collections.abc import Mapping

WEBSITE_RULES = {
    "Title present": ("Title", lambda x: bool(str(x or "").strip())),
    "Meta description present": ("Meta Description", lambda x: bool(str(x or "").strip())),
    "Exactly one H1": ("H1 Count", lambda x: x == 1),
    "Useful heading structure": ("Heading Count", lambda x: x >= 2),
    "Substantial page text": ("Word Count", lambda x: x >= 100),
    "Contact information signal": ("Contact Signal", bool),
}


def score_website(record: Mapping) -> dict:
    """Return score (0-100) based only on measurable checks and their coverage."""
    available, passed = [], []
    for label, (field, rule) in WEBSITE_RULES.items():
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        available.append(label)
        try:
            passed.append(bool(rule(value)))
        except (TypeError, ValueError):
            passed.append(False)
    count = len(available)
    return {"Website Score": round(100 * sum(passed) / count) if count else None,
            "Score Coverage": f"{count}/{len(WEBSITE_RULES)} signals",
            "Available Signals": available,
            "Passed Signals": [name for name, ok in zip(available, passed) if ok]}


def score_competitors(records: list[Mapping]) -> list[dict]:
    """Add score fields to copied records without mutating caller data."""
    return [{**dict(item), **score_website(item)} for item in records]
