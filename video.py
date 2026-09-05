#!/usr/bin/env python3
"""
Which reels people stop watching soonest.

Not a skip rate. A skip rate needs the video's length, and Instagram does not
expose it: `duration`, `video_duration`, `media_duration`, `length` and
`play_count` are all rejected on the media node, and the only durations we hold
come from 2024 static exports that predate the posts we analyse. So there is no
reel for which both length and watch time are known.

What is knowable is how many seconds people actually watched. That stands on its
own: dropping off at four seconds is bad whether the reel ran ten seconds or
sixty, because the opening is where attention is won or lost. It is reported in
seconds and never as a percentage, because a percentage would be inventing the
denominator.
"""
import datetime as dt

import pandas as pd

MIN_REACH = 200      # below this the average is a handful of people
SHOW = 8


def video_findings(m, year=None):
    """Scoped to the calendar year. A reel from last year is not a useful
    example of what is losing people this semester, and the reels the org
    makes now are not the reels it made then."""
    year = year or dt.date.today().year
    r = m[(m["post_type"] == "IG reel")
          & (m["d"].dt.year == year)
          & m["avg_watch_time_sec"].notna()
          & (m["avg_watch_time_sec"] > 0)].copy()
    r = r[r["reach"] >= MIN_REACH]
    if len(r) < 5:
        return {"enough": False}
    med = float(r["avg_watch_time_sec"].median())
    worst = r.nsmallest(SHOW, "avg_watch_time_sec")
    rows = []
    for _, x in worst.iterrows():
        cap = str(x.get("caption") or "").replace("\n", " ").strip()
        rows.append({
            "caption": (cap[:62] + "…") if len(cap) > 62 else (cap or "(no caption)"),
            "link": x.get("permalink") or "",
            "watched": float(x["avg_watch_time_sec"]),
            "reach": float(x["reach"]),
            "vs_median": float(x["avg_watch_time_sec"]) - med,
        })
    return {"enough": True, "rows": rows, "median": med, "reels": len(r),
            "year": year}


def video_note(vf):
    if not vf.get("enough"):
        return ["Not enough reels with watch-time data yet."]
    rows = vf["rows"]
    worst = rows[0]
    out = [f"<b>A typical reel holds {vf['median']:.1f} seconds</b> across the "
           f"{vf['reels']} you posted in {vf['year']}. The ones below lost "
           f"people fastest, the weakest at {worst['watched']:.1f} seconds."]
    reachy = [r for r in rows if r["reach"] >= 1500]
    if reachy:
        out.append(f"<b>{len(reachy)} of these still reached 1,500 or more</b>, "
                   f"so distribution was not the problem. People arrived and "
                   f"left, which points at the first second or two.")
    out.append("<i>Instagram does not give us video length, so this is seconds "
               "watched rather than a percentage skipped. A share would need a "
               "denominator we do not have.</i>")
    return out
