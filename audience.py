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
