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
    # Which accounts are still blank in the newest row.
    missing = [h for h in handles if h != OURS and pd.isna(latest.get(h))]

    # Always return a row per tracked account, even with no number yet, so the
    # page can render the table rather than a message about a spreadsheet.
    listed = []
    for h in handles:
        now = latest.get(h)
        before = prev.get(h) if prev is not None else None
        listed.append({
            "handle": h,
            "followers": None if pd.isna(now) else float(now),
            "change": (float(now - before)
                       if before is not None and not pd.isna(before)
                       and not pd.isna(now) else None),
            "ours": h == OURS,
        })
    known = [r for r in listed if r["followers"] is not None]
    known.sort(key=lambda r: -r["followers"])
    unknown = [r for r in listed if r["followers"] is None]
    rows = known + unknown
    for i, r in enumerate(known, 1):
        r["rank"] = i

    us = next((r for r in rows if r["ours"]), None)
    if us and us["followers"] is None and ours_now:
        us["followers"] = float(ours_now)

    # How each account compares with us, on size and on growth
    if us and us["followers"]:
        for r in rows:
            if r["ours"] or r["followers"] is None:
                continue
            r["gap"] = r["followers"] - us["followers"]
            if r.get("change") is not None and us.get("change") is not None:
                r["growth_gap"] = r["change"] - us["change"]

    age = (pd.Timestamp.today().normalize() - latest["date"]).days
    return {"enough": True, "rows": rows, "us": us, "as_of": latest["date"],
            "weeks": len(d), "handles": handles, "missing": missing,
            "have_numbers": len(known) > 1, "age_days": int(age),
            "stale": age > 45}


def competitor_note(cf):
    if not cf.get("enough"):
        return ["No competitor list set up yet."]
    if not cf.get("have_numbers"):
        miss = cf.get("missing") or []
        return [f"<b>No follower counts yet.</b> Instagram does not publish other "
                f"accounts' figures to us, so these {len(miss)} have to be entered "
                f"by hand, in the <b>Competitors</b> tab of the Google Sheet or by "
                f"telling Claude the numbers. Yours is filled in automatically."]
    rows, us = cf["rows"], cf.get("us")
    out = []
    if us and us.get("rank"):
        bigger = [r for r in rows if r["followers"] and not r["ours"]
                  and r["followers"] > us["followers"]]
        total = len([r for r in rows if r["followers"]])
        if not bigger:
            out.append(f"<b>You are the largest</b> of the {total} accounts "
                       f"tracked, at {us['followers']:,.0f} followers.")
        else:
            ahead = min(bigger, key=lambda r: r["followers"])
            out.append(f"<b>You are {us['rank']} of {total}</b> at "
                       f"{us['followers']:,.0f}. @{ahead['handle']} is nearest "
                       f"above you, {ahead['followers'] - us['followers']:,.0f} "
                       f"ahead.")
    grew = [r for r in rows if r.get("growth_gap") is not None]
    if grew and us and us.get("change") is not None:
        faster = [r for r in grew if r["growth_gap"] > 0]
        if not faster:
            out.append(f"<b>You grew fastest</b> this week, {us['change']:+,.0f} "
                       f"against every account tracked.")
        else:
            top = max(faster, key=lambda r: r["change"])
            out.append(f"<b>@{top['handle']} grew fastest</b>, "
                       f"{top['change']:+,.0f} against your "
                       f"{us['change']:+,.0f}.")
    if cf.get("stale"):
        out.append(f"<i>These numbers are {cf['age_days']} days old. A fresh row "
                   f"is added to the sheet every month for someone to fill.</i>")
    if cf.get("missing"):
        out.append("<i>Still blank: "
                   + ", ".join(f"@{h}" for h in cf["missing"]) + ".</i>")
    if cf["weeks"] < 2:
        out.append("<i>One reading so far. Growth comparisons appear once there "
                   "are two.</i>")
    return out
