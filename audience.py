#!/usr/bin/env python3
"""
Who actually follows the account.

This is the only part of the dashboard that is not about posts, which is
exactly why it is worth keeping: everything else tells you how content
performed, and this tells you who it reached. For a student org the age split
is the number that matters, because an audience that has aged past the student
body cannot be recruited from no matter how well the posts do.
"""
import pandas as pd

STUDENT_AGES = ("18-24",)


def audience_findings(csv_dir):
    p = csv_dir / "audience_demographics.csv"
    if not p.exists():
        return {"enough": False}
    d = pd.read_csv(p)
    if not len(d):
        return {"enough": False}
    d = d[d["pull_date"] == d["pull_date"].max()]
    d["follower_count"] = pd.to_numeric(d["follower_count"], errors="coerce").fillna(0)

    out = {"enough": True, "as_of": str(d["pull_date"].iloc[0]), "parts": {}}
    for b, g in d.groupby("breakdown"):
        tot = g["follower_count"].sum()
        if not tot:
            continue
        seg = [(str(r["segment"]), r["follower_count"], r["follower_count"] / tot * 100)
               for _, r in g.sort_values("follower_count", ascending=False).iterrows()]
        out["parts"][b] = {"total": tot, "segments": seg}
    return out if out["parts"] else {"enough": False}


def audience_recommendations(af):
    if not af.get("enough"):
        return ["No audience data collected yet."]
    out, parts = [], af["parts"]

    age = parts.get("age")
    if age:
        top = age["segments"][0]
        student = sum(p for s, _, p in age["segments"] if s in STUDENT_AGES)
        if top[0] not in STUDENT_AGES:
            out.append(
                f"<b>Not working:</b> your biggest group is <b>{top[0]}</b> at "
                f"{top[2]:.0f}%, while students aged 18 to 24 are only "
                f"{student:.0f}%. Most of the people you reach have aged past "
                f"the students you recruit.")
        else:
            out.append(f"<b>Working:</b> {student:.0f}% of followers are 18 to 24, "
                       f"so the audience matches who you recruit.")

    city = parts.get("city")
    if city:
        top3 = city["segments"][:3]
        share = sum(p for _, _, p in top3)
        names = ", ".join(s.split(",")[0] for s, _, _ in top3)
        out.append(f"<b>Where they are:</b> {names} account for {share:.0f}% of "
                   f"followers with a known city. That is FIU's catchment, which "
                   f"is what you want.")

    country = parts.get("country")
    if country:
        us = next((p for s, _, p in country["segments"] if s == "US"), None)
        if us is not None and us < 85:
            out.append(f"<b>Worth watching:</b> only {us:.0f}% of followers are in "
                       f"the US, so a slice of your reach cannot attend anything "
                       f"you run.")

    gender = parts.get("gender")
    if gender:
        known = [(s, p) for s, _, p in gender["segments"] if s in ("M", "F")]
        if len(known) == 2:
            (a, ap), (b, bp) = known
            label = {"M": "men", "F": "women"}
            if ap - bp >= 10:
                out.append(f"<b>Split:</b> {ap:.0f}% {label[a]} against {bp:.0f}% "
                           f"{label[b]}. Worth knowing when you pick who appears "
                           f"in a post.")

    out.append(f"<i>Instagram reports these for followers only, and a share are "
               f"unknown, so the percentages are indicative rather than exact. "
               f"Collected {af['as_of']}.</i>")
    return out


# ── follower growth ─────────────────────────────────────────────────────────
GAP_DAYS = 14          # a longer hole than this means collection was not running
MIN_COVERAGE = 0.5     # a window covered less than this cannot be reported as itself


def follower_growth(csv_dir, days=None):
    """Follower counts over the continuously-collected stretch.

    Readings exist from before the daily job started, separated by a 54 day
    hole. Plotting straight through that would draw a smooth line across two
    months nobody measured, so the series starts after the last real gap and
    the earlier reading is reported separately as context.
    """
    p = csv_dir / "account_insights.csv"
    if not p.exists():
        return {"enough": False}
    d = pd.read_csv(p)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["followers_count"] = pd.to_numeric(d["followers_count"], errors="coerce")
    d = (d.dropna(subset=["date", "followers_count"])
           .sort_values("date").drop_duplicates("date", keep="last"))
    if len(d) < 3:
        return {"enough": False}

    gaps = d["date"].diff().dt.days
    start = 0
    for i, g in enumerate(gaps):
        if g and g > GAP_DAYS:
            start = i
    series = d.iloc[start:]
    dropped = d.iloc[:start]

    # Scope to the selected period. `days=None` means this calendar year.
    newest = series["date"].max()
    if days is None:
        want = pd.Timestamp(year=newest.year, month=1, day=1)
    else:
        want = newest - pd.Timedelta(days=days)
    collection_start = series["date"].min()      # when daily pulls actually began
    wanted_days = max(1, (newest - want).days)
    scoped = series[series["date"] >= want]
    # Truncated means collection did not run back that far, not merely that no
    # reading landed on the window's first day. Readings are a few days apart,
    # so comparing against the window edge would flag every week as partial.
    truncated = bool(series["date"].min() > want)
    if len(scoped) >= 2:
        series = scoped
    elif len(series) < 2:
        return {"enough": False}
    else:
        truncated = True
    if len(series) < 2:
        return {"enough": False}

    first, last = series.iloc[0], series.iloc[-1]
    days = max(1, (last["date"] - first["date"]).days)
    change = last["followers_count"] - first["followers_count"]
    held = max(1, (last["date"] - first["date"]).days)
    coverage = min(1.0, held / wanted_days)
    return {
        "enough": True, "days": days, "truncated": truncated,
        "collection_start": collection_start,
        "wanted_days": wanted_days, "coverage": coverage,
        # Below this the window shares its numbers with a shorter one, which
        # reads as a bug. Report the shortfall instead of the duplicate.
        "reportable": coverage >= MIN_COVERAGE,
        "points": [(r["date"], float(r["followers_count"]))
                   for _, r in series.iterrows()],
        "current": float(last["followers_count"]),
        "change": float(change),
        "span": days,
        "per_week": change / days * 7,
        "pct": (change / first["followers_count"] * 100)
               if first["followers_count"] else 0,
        "since": first["date"],
        "until": last["date"],
        "earlier": ({"date": dropped.iloc[-1]["date"],
                     "count": float(dropped.iloc[-1]["followers_count"])}
                    if len(dropped) else None),
    }


def growth_note(g):
    if not g.get("enough"):
        return []
    up = g["change"] >= 0
    out = [f"<b>{'Working' if up else 'Not working'}:</b> "
           f"{'up' if up else 'down'} <b>{abs(g['change']):,.0f} followers</b> "
           f"in {g['days']} days, about {abs(g['per_week']):,.0f} a week."]
    # Only disclose the gap when this window actually reaches past collection.
    if g.get("truncated"):
        out.append(f"This period only holds {g['days']} days of readings. Daily "
                   f"tracking began {g['collection_start']:%d %b}"
                   + (f", and the reading before that was "
                      f"{g['earlier']['count']:,.0f} on {g['earlier']['date']:%d %b} "
                      f"with nothing measured in between."
                      if g.get("earlier") else "."))
    return out
