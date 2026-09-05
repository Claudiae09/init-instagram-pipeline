#!/usr/bin/env python3
"""
When to post, and how often.

Both answers need the full history rather than the selected period: a single
week holds too few posts to place a best time, and cadence is a question about
weeks, so you need many of them. The card says so, because everything else on
the page follows the period control.
"""
import pandas as pd

import report_sections as R

MIN_DAY  = 8        # posts needed before a weekday can be called the best
MIN_SLOT = 6        # posts needed in an hour before we name that hour
BANDS = [(1, 2), (3, 4), (5, 6), (7, 99)]
MIN_BAND_WEEKS = 5  # a band with fewer weeks than this is not a recommendation
RECENT_WEEKS = 8


def _label(lo, hi):
    return f"{lo} or {hi}" if hi == lo + 1 else (f"{lo}+" if hi > 50 else f"{lo} to {hi}")


def posting_findings(m, since_year=2025):
    """Best day/hour overall, and which weekly volume actually performs."""
    m = m[m["d"].dt.year >= since_year].copy()
    if len(m) < 30:
        return {"enough": False}

    out = {"enough": True, "posts": len(m)}

    # ── best day, then the best hour inside it ──────────────────────────────
    # Picking a day+hour outright lands on a slot with three or four posts.
    # The day is settled on dozens, so choose that first and only name an hour
    # when that hour is itself carried by enough posts.
    d = m.groupby("publish_weekday").agg(n=("reach", "size"),
                                         med=("reach", "median"))
    d = d[d["n"] >= MIN_DAY].sort_values("med", ascending=False)
    if len(d):
        day, row = next(d.iterrows())
        out["day"] = day
        out["day_reach"], out["day_n"] = int(row["med"]), int(row["n"])
        out["worst_day"] = d.index[-1]
        out["worst_day_reach"] = int(d.iloc[-1]["med"])
        hrs = m[m["publish_weekday"] == day].groupby("publish_hour_est").agg(
            n=("reach", "size"), med=("reach", "median"))
        hrs = hrs[hrs["n"] >= MIN_SLOT].sort_values("med", ascending=False)
        if len(hrs):
            out["hour"] = int(hrs.index[0])
            out["hour_n"] = int(hrs.iloc[0]["n"])
        else:
            out["hour"] = None

    # ── how often ───────────────────────────────────────────────────────────
    m["wk"] = m["d"].dt.to_period("W")
    wk = m.groupby("wk").agg(posts=("reach", "size"), sh=("shares", "sum"),
                             rch=("reach", "sum"), med=("reach", "median"))
    wk = wk[wk["rch"] > 0]
    bands = []
    for lo, hi in BANDS:
        b = wk[(wk["posts"] >= lo) & (wk["posts"] <= hi)]
        if len(b) >= MIN_BAND_WEEKS:
            bands.append({"label": _label(lo, hi), "lo": lo, "hi": hi,
                          "weeks": len(b),
                          "rate": b["sh"].sum() / b["rch"].sum() * 1000,
                          "reach": float(b["med"].median())})
    if bands:
        bands.sort(key=lambda x: -x["rate"])
        out["bands"] = bands
        out["best_band"] = bands[0]
        out["worst_band"] = bands[-1]
    recent = wk.tail(RECENT_WEEKS)
    if len(recent):
        out["recent_avg"] = float(recent["posts"].mean())
        out["recent_weeks"] = len(recent)
    return out


def posting_note(pf):
    """One or two short lines explaining the cadence number."""
    if not pf.get("enough") or "best_band" not in pf:
        return []
    b, w = pf["best_band"], pf.get("worst_band")
    out = [f"Weeks with <b>{b['label']} posts</b> earned {b['rate']:.1f} shares "
           f"per 1,000 across {b['weeks']} weeks"
           + (f", against {w['rate']:.1f} for weeks of {w['label']}."
              if w and w is not b else ".")]
    if w and w is not b and b["reach"] and w["reach"]:
        out.append(f"Those quieter weeks also reached more people per post: "
                   f"{b['reach']:,.0f} against {w['reach']:,.0f}. Posting more "
                   f"has not bought reach.")
    if pf.get("recent_avg") is not None:
        cur = pf["recent_avg"]
        if cur > b["hi"]:
            out.append(f"You are averaging <b>{cur:.1f} a week</b> over the last "
                       f"{pf['recent_weeks']}, above the band that performs best.")
        elif cur < b["lo"]:
            out.append(f"You are averaging <b>{cur:.1f} a week</b>, below that band.")
        else:
            out.append(f"You are averaging <b>{cur:.1f} a week</b>, which is "
                       f"inside that band.")
    return out
