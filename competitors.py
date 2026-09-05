#!/usr/bin/env python3
"""
Competitor follower tracking.

Instagram will not give us anyone else's numbers. business_discovery is the
endpoint for it and it does not exist on the Instagram Login host we use:

    graph.instagram.com -> "Tried accessing nonexisting field (business_discovery)"

It needs Facebook Login, which needs the Page that someone else administers. So
the counts are typed in rather than fetched, into a Competitors tab in the same
Google Sheet the rest of the pipeline uses. The weekly job stamps a new row with
the date and our own follower count; a person fills in the rest.

Handles live in the sheet's header row, not in this file, so competitors can be
added or renamed without a code change.
"""
import pandas as pd

OURS = "init.fiu"


def competitor_findings(csv_dir, ours_now=None):
    p = csv_dir / "competitors.csv"
    if not p.exists():
        return {"enough": False}
    d = pd.read_csv(p)
    if "date" not in d.columns or not len(d):
        return {"enough": False}
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date")
    handles = [c for c in d.columns if c != "date"]
    if not handles:
        return {"enough": False}
    for h in handles:
        d[h] = pd.to_numeric(d[h], errors="coerce")

    latest = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else None
    rows = []
    for h in handles:
        now = latest.get(h)
        if pd.isna(now):
            continue
        before = prev.get(h) if prev is not None else None
        rows.append({
            "handle": h,
            "followers": float(now),
            "change": (float(now - before)
                       if before is not None and not pd.isna(before) else None),
            "ours": h == OURS,
        })
    if not rows:
        return {"enough": False, "awaiting": True, "handles": handles,
                "as_of": latest["date"]}
    # Which accounts are still blank in the newest row. Naming them is the
    # whole point of the empty state: it says exactly what to go and type.
    missing = [h for h in handles
               if h != OURS and pd.isna(latest.get(h))]
    # Our own number alone is not a comparison.
    if len([r for r in rows if not r["ours"]]) == 0:
        return {"enough": False, "awaiting": True, "missing": missing,
                "as_of": latest["date"]}
    rows.sort(key=lambda r: -r["followers"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    us = next((r for r in rows if r["ours"]), None)
    if us is None and ours_now:
        us = {"handle": OURS, "followers": float(ours_now), "change": None,
              "ours": True, "rank": None}
        rows.append(us)
        rows.sort(key=lambda r: -r["followers"])
        for i, r in enumerate(rows, 1):
            r["rank"] = i
    return {"enough": True, "rows": rows, "us": us, "as_of": latest["date"],
            "weeks": len(d), "handles": handles, "missing": missing}


def competitor_note(cf):
    if not cf.get("enough"):
        miss = cf.get("missing") or []
        who = ("".join(f" @{h}," for h in miss).rstrip(",")
               if miss else " the competitor columns")
        return [f"<b>Waiting on the first numbers.</b> Open the "
                f"<b>Competitors</b> tab of the Google Sheet and fill in"
                f"{who}. Your own count is filled in for you each week.",
                "<i>Instagram does not publish other accounts' follower counts "
                "to us, so these have to be typed in.</i>"]
    rows, us = cf["rows"], cf.get("us")
    out = []
    if us and us.get("rank"):
        bigger = [r for r in rows if r["followers"] > us["followers"]]
        if not bigger:
            out.append(f"<b>You are the largest</b> of the {len(rows)} accounts "
                       f"tracked, at {us['followers']:,.0f} followers.")
        else:
            ahead = bigger[-1]                     # the nearest one above
            gap = ahead["followers"] - us["followers"]
            out.append(f"<b>You are {us['rank']} of {len(rows)}</b> at "
                       f"{us['followers']:,.0f} followers. "
                       f"@{ahead['handle']} is nearest above you, "
                       f"{gap:,.0f} ahead.")
    if cf.get("missing"):
        out.append("<i>Still blank this week: "
                   + ", ".join(f"@{h}" for h in cf["missing"]) + ".</i>")
    moved = [r for r in rows if r.get("change") is not None]
    if moved:
        moved.sort(key=lambda r: -r["change"])
        top = moved[0]
        out.append(f"Fastest growing since the last reading: "
                   f"<b>@{top['handle']}</b>, {top['change']:+,.0f}.")
    if cf["weeks"] < 2:
        out.append("<i>One reading so far. Week-on-week movement appears once "
                   "there are two.</i>")
    out.append("<i>Instagram does not publish other accounts' figures to us, so "
               "these are entered by hand in the Google Sheet rather than "
               "collected automatically.</i>")
    return out
