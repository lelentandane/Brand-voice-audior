"""scoring.py - turn raw signals into scores. Heuristics, tunable."""

WEIGHTS = {"voice": 0.5, "seo": 0.3, "visual": 0.2}


def visual_score(visuals: dict | None) -> int | None:
    """Palette cohesion based on how many distinct hue families the brand uses.
    Returns None when no chromatic colors were found (unscored, not zero)."""
    if not visuals or visuals["metrics"]["palette_size"] == 0:
        return None
    families = visuals["metrics"]["hue_families"]
    return {1: 100, 2: 95, 3: 80, 4: 60}.get(families, 40)


def health_score(voice: int | None, seo: int | None, visual: int | None) -> dict:
    """Weighted average over the components that could be scored."""
    parts = {"voice": voice, "seo": seo, "visual": visual}
    used = {k: v for k, v in parts.items() if v is not None}
    total_weight = sum(WEIGHTS[k] for k in used)
    overall = round(sum(v * WEIGHTS[k] for k, v in used.items()) / total_weight) if used else None
    return {
        "overall": overall,
        "components": parts,
        "weights": {k: round(WEIGHTS[k] / total_weight, 2) for k in used} if used else {},
    }


def priorities(voice: dict | None, seo: dict | None, limit: int = 5) -> list[dict]:
    """The fixes worth doing first, in plain language.

    Voice issues come first because voice carries the largest weight. Failed
    SEO checks follow. Each item has an area, a short title and an action.
    """
    items = []
    for issue in (voice or {}).get("issues", []):
        items.append({"area": "Voice", "title": issue["issue"], "action": issue["fix"]})
    for check in (seo or {}).get("checks", []):
        if not check["passed"]:
            items.append({"area": "SEO", "title": check["check"],
                          "action": check.get("advice", "")})
    return items[:limit]
