#!/usr/bin/env python3
"""
Which *kinds* of post work, and which ones are being under-used.

Instagram exposes nothing about what is trending, so the useful version of
"what should we post next" has to come from the account's own history. We tag
each post by what it is about, rank those topics by share rate, then compare
that ranking against what has actually been posted lately. A topic that
performs well but has gone quiet is the recommendation.

Topics are keyword matched and deliberately not exclusive: a ShellHacks
giveaway counts as both. We are ranking subjects, not filing posts.
"""
import pandas as pd

import report_sections as R

# Tuned to what this account actually posts. Order does not matter.
TOPICS = {
    "Giveaways":         r"giveaway|raffle|\bwin a\b|\bprize",
    "Deadlines and applications": r"\bapply\b|application|deadline|closes? (?:today|soon)|last chance",
    "Member spotlights":  r"spotlight|congrat|\balum(?:ni|na|nus)\b|shoutout|member of the (?:week|month)|meet one of",
    "ShellHacks":        r"shellhack",
    "Workshops and learning": r"workshop|bootcamp|learn to|tutorial|intro to|hands.?on",
    "Careers and internships": r"intern(?:ship)?\b|resume|career|hiring|\bjob\b|recruit",
    "Partners and sponsors": r"sponsor|partner|thank you to|powered by",
    "Socials and hangouts": r"\bsocial\b|mixer|game night|pizza|come hang|\bmeet ?up",
    "Team and behind the scenes": r"\bour team\b|\be-?board\b|behind the scenes|board member",
}

# Instagram truncates a caption after roughly this much, and the opening line
# is where a post states what it is about. Matching the whole caption tagged
# registration posts as "partners" because the sponsor thank-you sits in the
# boilerplate at the bottom.
LEDE = 150

# Two different bars, because showing a subject and trusting its rate are
# different questions. A subject with 4 posts belongs in the table (hiding it
# implies it does not exist) but must not drive a recommendation.
SHOW_MIN  = 3            # appears in the table
TRUST_MIN = 8            # allowed to lead the advice
RECENT_DAYS = 30         # window used to spot a topic that has gone quiet
MIN_YEAR_POSTS = 60      # below this, a single year is too thin to rank subjects


def _tag(m):
    m = m[m["caption"].notna() & (m["reach"] > 0)].copy()
    lede = m["caption"].astype(str).str[:LEDE]
    for name, pat in TOPICS.items():
        m[name] = lede.str.contains(pat, case=False, regex=True, na=False)
    # How many subjects each post matches. A post about everything is a poor
    # illustration of any one subject.
    m["_ntopics"] = m[list(TOPICS)].sum(axis=1)
    return m


def _example(g):
    """The post to point at for this subject: the one people shared most per
    viewer. A minimum reach keeps a fluke with 30 viewers from being the
    example everyone is told to copy."""
    pool = g[g["reach"] >= 200]
    if not len(pool):
        pool = g
    # Prefer a post that is mostly about THIS subject, so the same catch-all
    # post doesn't end up illustrating half the table.
    for limit in (1, 2, 3):
        focused = pool[pool["_ntopics"] <= limit]
        if len(focused) >= 3:
            pool = focused
            break
    pool = pool.assign(_r=pool["shares"] / pool["reach"] * 1000)
    best = pool.sort_values("_r", ascending=False).iloc[0]
    cap = str(best.get("caption") or "").replace("\n", " ").strip()
    return {"link": best.get("permalink") or "",
            "example": (cap[:52].rstrip() + "…") if len(cap) > 52 else cap,
            "example_rate": float(best["_r"])}


def topic_findings(m, year=None):
    """Rank topics by share rate, scoped to the current year.

    What worked in 2025 is not necessarily what to make this semester, so the
    ranking follows the calendar year. If this year is still too thin to rank
    fairly we fall back to all history and say so on the page."""
    import datetime as _dt
    year = year or _dt.date.today().year
    t = _tag(m)
    if not len(t):
        return {"enough": False}
    scoped = t[t["d"].dt.year == year]
    if len(scoped) >= MIN_YEAR_POSTS:
        t, scope = scoped, str(year)
    else:
        scope = "all history"
    base = t["shares"].sum() / t["reach"].sum() * 1000
    recent = R.window(t, RECENT_DAYS)
    rows = []
    for name in TOPICS:
        g = t[t[name]]
        if len(g) < SHOW_MIN or not g["reach"].sum():
            continue
        # Same outlier guard used elsewhere, but here it flags rather than
        # deletes: dropping a subject from the table entirely hides the fact
        # that it exists. It just cannot be trusted to lead the advice.
        tot = g["shares"].sum()
        skewed = bool(tot > 0
                      and g["shares"].max() / tot > R.MAX_POST_CONCENTRATION)
        rows.append({
            "skewed": skewed, "thin": len(g) < TRUST_MIN,
            "topic": name, "posts": len(g),
            "rate": g["shares"].sum() / g["reach"].sum() * 1000,
            "recent": int(recent[name].sum()) if len(recent) else 0,
            **_example(g),
        })
    if not rows:
        return {"enough": False}
    for r in rows:
        r["vs_avg"] = R.pct_change(base, r["rate"])
    rows.sort(key=lambda r: -r["rate"])
    solid = [r for r in rows if not r["skewed"] and not r["thin"]]
    # What has been dominating the calendar lately, which is often not the same
    # thing as what performs. That gap is the most useful recommendation here.
    dominant = max(rows, key=lambda r: r["recent"]) if len(recent) else None
    return {"enough": True, "base": base, "rows": rows, "solid": solid,
            "dominant": dominant,
            "scope": scope, "recent_posts": len(recent), "total": len(t)}


def topic_recommendations(tf):
    """Short bullets: what works, what is crowding it out, what to ease off."""
    if not tf.get("enough"):
        return ["Not enough captions yet to tell which subjects work."]
    rows, base, out = tf["solid"] or tf["rows"], tf["base"], []
    top = rows[0]

    out.append(f"<b>Working:</b> {top['topic']}, at {top['rate']:.1f} per 1,000 "
               f"across {top['posts']} posts. Your best subject.")

    # The calendar is usually crowded by one thing. Say so when that thing is
    # not the thing that performs.
    dom = tf.get("dominant")
    if (dom and dom["topic"] != top["topic"] and tf["recent_posts"]
            and dom["recent"] / tf["recent_posts"] >= .4
            and top["rate"] > dom["rate"] * 1.15):
        gap = R.pct_change(dom["rate"], top["rate"])
        # top is already named in the bullet above, so don't repeat it
        out.append(
            f"<b>Make more of them.</b> Lately you are mostly posting "
            f"{dom['topic']} ({dom['recent']} of your last {tf['recent_posts']}), "
            f"and {top['topic']} get shared {gap:.0f}% more.")
    else:
        # otherwise flag a strong subject that has simply gone quiet
        gaps = [r for r in rows if r["vs_avg"] >= 15 and r["recent"] <= 2]
        if gaps:
            g, n = gaps[0], gaps[0]["recent"]
            out.append(f"<b>Make more:</b> {g['topic']}, {g['vs_avg']:.0f}% "
                       f"above your average, but " +
                       ("none " if n == 0 else f"only {n} ") +
                       f"posted in the last {RECENT_DAYS} days.")

    low = rows[-1]
    if low["vs_avg"] <= -15:
        out.append(f"<b>Ease off:</b> {low['topic']}, at {low['rate']:.1f} "
                   f"against your {base:.1f} average. Worth posting, just not for "
                   f"growth.")

    # When nothing stands out, say that rather than padding with a weak claim.
    if len(out) == 1 and len(rows) > 1:
        lo = rows[-1]
        out.append(f"Your subjects sit close together this year, from "
                   f"{top['rate']:.1f} down to {lo['rate']:.1f} per 1,000. "
                   f"No single subject is running away with it, so format and "
                   f"timing matter more than topic right now.")

    sc = tf.get("scope", "")
    where = f"your {sc} posts" if sc.isdigit() else "all your posts"
    out.append(f"<i>Based on {tf['total']} captions from {where}. Instagram "
               f"publishes nothing about what is trending, so this ranks what "
               f"works for your own audience.</i>")
    return out
