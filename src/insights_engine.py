"""Small, evidence-based summaries of competitor website analysis."""

import pandas as pd


def generate_insights(data: pd.DataFrame) -> list[str]:
    """Generate deterministic observations; never infer market share or rank."""
    if data is None or data.empty:
        return ["Add competitors and analyse public websites to see observations."]
    rows = data.copy()
    if "Website Score" not in rows:
        return ["Website scores are not available in this dataset."]
    scores = pd.to_numeric(rows["Website Score"], errors="coerce")
    valid = rows.loc[scores.notna()].copy()
    if valid.empty:
        return ["No websites produced a score; check availability and try again."]
    valid["_score"] = scores[scores.notna()]
    average = valid["_score"].mean()
    lines = [f"The average website signal score is {average:.0f}/100 across {len(valid)} scored website(s)."]
    leader = valid.loc[valid["_score"].idxmax()]
    lines.append(f"{leader.get('Business', 'A competitor')} had the highest measured website signal score ({leader['_score']:.0f}/100) in this set.")
    if "Website" in rows:
        missing = int(rows["Website"].fillna("").astype(str).str.strip().eq("").sum())
        if missing:
            lines.append(f"{missing} listed competitor(s) have no website URL to analyse.")
    if "Score Coverage" in valid:
        low = int(valid["Score Coverage"].fillna("").astype(str).str.startswith(("0/", "1/", "2/" )).sum())
        if low:
            lines.append(f"{low} scored website(s) have fewer than three observable signals; treat their scores cautiously.")
    lines.append("These checks describe visible website signals only; they do not measure traffic, reputation, market share, or overall business strength.")
    return lines
