#!/usr/bin/env python3
"""
Invariant tests for the dashboard.

Deliberately not assertions about today's numbers, which change on every pull.
These check the properties that must hold whatever the data does: that windows
mean what they say, that small samples cannot become recommendations, that no
claim is made from a denominator we do not have, and that the rendered document
is well-formed and internally consistent.

Run:  ./venv/bin/python tests.py
"""
import datetime as dt
import pathlib
import re
import sys

import pandas as pd

import audience
import chart_notes
import competitors
import render
import report_sections as R
import timing
import topics
import video

FAILS = []
RAN = 0


def check(name, cond, detail=""):
    global RAN
    RAN += 1
    if not cond:
        FAILS.append((name, detail))
    print(("  ok   " if cond else "  FAIL ") + name + (f"  — {detail}" if not cond and detail else ""))


# ── analysis invariants ─────────────────────────────────────────────────────
def test_analysis(m):
    print("\nanalysis")

    # 1. Windows are anchored to today, not to the newest post. Tested on
    #    synthetic data whose newest post is 20 days old, because on live data
    #    the two behaviours coincide whenever something was posted today —
    #    which is exactly why the original bug survived so long.
    today = pd.Timestamp(dt.date.today())
    stale = pd.DataFrame({
        "d": [today - pd.Timedelta(days=n) for n in (20, 22, 24, 40)],
        "media_id": ["a", "b", "c", "d"],
        "reach": [100, 100, 100, 100], "shares": [1, 1, 1, 1],
        "saved": [0, 0, 0, 0], "total_interactions": [1, 1, 1, 1],
        "post_type": ["IG reel"] * 4,
    })
    check("a 7-day window over stale data is empty, not back-dated",
          len(R.window(stale, 7)) == 0,
          f"{len(R.window(stale, 7))} posts found in an empty week")
    check("a 30-day window over stale data holds only the 3 recent posts",
          len(R.window(stale, 30)) == 3, f"{len(R.window(stale, 30))}")

    # 2. Current and previous windows must not overlap, or the comparison is
    #    partly against itself.
    cur, prev = R.window(m, 30), R.window(m, 30, offset=30)
    overlap = set(cur["media_id"]) & set(prev["media_id"])
    check("current and previous windows are disjoint", not overlap,
          f"{len(overlap)} posts in both")

    # 3. A format may not be named a leader on too few posts or on one post's
    #    virality. This produced three wrong recommendations historically.
    #    Asserted against literals, not against R.MIN_FMT_POSTS: reading the
    #    same constant the code reads makes the test agree with any value,
    #    including a broken one.
    for days in (7, 30, None):
        p = R.compare_periods(m, days, "X", "Y")
        if not p.get("enough"):
            continue
        for fmt, rate, n in p["formats"]:
            g = R.window(m, days)
            g = g[g["post_type"] == fmt]
            tot = g["shares"].sum()
            conc = (g["shares"].max() / tot) if tot else 0
            check(f"[{days}] {fmt} ranked on 5+ posts", n >= 5, f"n={n}")
            check(f"[{days}] {fmt} not carried by one post",
                  conc <= 0.45, f"{conc:.0%}")

    # A format with 2 posts, and one whose shares come from a single post,
    # must both be excluded. Synthetic so the case always exists.
    tiny = pd.DataFrame({
        "d": [today - pd.Timedelta(days=n) for n in range(1, 13)],
        "media_id": [str(i) for i in range(12)],
        "reach": [1000] * 12,
        "shares": [5] * 10 + [5, 5],
        "saved": [0] * 12, "total_interactions": [50] * 12,
        "post_type": ["IG carousel"] * 10 + ["IG image"] * 2,
    })
    got = [f for f, _r, _n in R.compare_periods(tiny, 30, "X", "Y")["formats"]]
    check("a 2-post format is never ranked", "IG image" not in got, str(got))

    spike = tiny.copy()
    spike.loc[spike["post_type"] == "IG carousel", "post_type"] = "IG reel"
    spike.loc[spike.index[0], "shares"] = 500        # one post = 91% of shares
    got2 = [f for f, _r, _n in R.compare_periods(spike, 30, "X", "Y")["formats"]]
    check("a format carried by one viral post is never ranked",
          "IG reel" not in got2, str(got2))

    # 4. Rates are aggregate (sum/sum), never a mean of per-post rates, which
    #    lets a 12-reach post weigh as much as a 3,000-reach one.
    g = m[m["post_type"] == "IG carousel"]
    agg = g["shares"].sum() / g["reach"].sum() * 1000
    check("share rate is aggregate, not a mean of per-post rates",
          abs(R.rate(g, "shares") - agg) < 1e-9)

    # 5. An excluded format that outscores the named leader must be disclosed,
    #    or the page contradicts its own tab.
    p = R.compare_periods(m, None, "Year", "prev")
    if p.get("enough") and p["formats"]:
        top = p["formats"][0][1]
        beats = [e for e in p.get("excluded", []) if e["rate"] > top]
        if beats:
            txt = " ".join(R.period_recommendations(p))
            check("a higher-scoring excluded format is disclosed",
                  beats[0]["fmt"] in txt, f"{beats[0]['fmt']} missing from copy")


def test_stories(csv):
    print("\nstories")
    for days in (7, 30, None):
        sf = R.story_findings(csv, days)
        if not sf.get("enough"):
            continue
        # A window we cannot fill must not silently repeat a shorter one's
        # numbers under a longer label.
        if sf.get("truncated"):
            check(f"[{days}] truncated story window is disclosed",
                  sf["span_days"] < (days or 366))
        check(f"[{days}] story sets never exceed frames",
              sf["sets"] <= sf["n"], f"{sf['sets']} > {sf['n']}")
        check(f"[{days}] completion is a percentage",
              0 <= sf["completion"] <= 100, f"{sf['completion']}")
        check(f"[{days}] derived likes are non-negative",
              sf["passive"] >= 0)


def test_followers(csv):
    print("\nfollowers")
    seen = {}
    for label, days in (("week", 7), ("month", 30), ("year", None)):
        g = audience.follower_growth(csv, days)
        if not g.get("enough"):
            continue
        check(f"[{label}] coverage is a fraction", 0 < g["coverage"] <= 1)
        # The bug this catches: Month and Year both clamped to the same 20 days
        # and showed identical numbers under different labels.
        if g["reportable"]:
            key = (g["change"], g["days"])
            check(f"[{label}] reportable window is not a duplicate of a shorter one",
                  key not in seen, f"same as {seen.get(key)}")
            seen[key] = label
        else:
            check(f"[{label}] unfillable window is suppressed",
                  g["coverage"] < audience.MIN_COVERAGE)


def test_topics(m):
    print("\nsubjects")
    tf = topics.topic_findings(m)
    if tf.get("enough"):
        # Subjects are matched on the caption opening; matching the whole
        # caption filed registration posts under "partners" because the
        # sponsor thank-you sits in the boilerplate.
        for r in tf["rows"]:
            cap = str(m[m["permalink"] == r["link"]].iloc[0]["caption"])[:topics.LEDE]
            check(f"{r['topic']} example matches its own subject",
                  bool(re.search(topics.TOPICS[r["topic"]], cap, re.I)))
        links = [r["link"] for r in tf["rows"]]
        check("each subject has a distinct example", len(links) == len(set(links)))
        for r in tf["solid"]:
            check(f"{r['topic']} drives advice only when well sampled",
                  r["posts"] >= topics.TRUST_MIN and not r["skewed"])


def test_timing(m):
    print("\ntiming")
    pf = timing.posting_findings(m)
    if pf.get("enough") and "day" in pf:
        check("best day rests on enough posts", pf["day_n"] >= timing.MIN_DAY)
        if pf.get("hour") is not None:
            check("named hour rests on enough posts",
                  pf["hour_n"] >= timing.MIN_SLOT, f"n={pf['hour_n']}")
    bd = timing.best_time_by_day(m)
    if bd.get("enough"):
        check("day table covers all seven days", len(bd["rows"]) == 7)
        for r in bd["rows"]:
            if "hour" in r:
                check(f"{r['day']} hour is shown or marked",
                      r["hour_n"] >= timing.HOUR_SHOW)
                check(f"{r['day']} hour is a real hour", 0 <= r["hour"] <= 23)


def test_video(m):
    print("\nreels")
    vf = video.video_findings(m)
    if vf.get("enough"):
        check("scoped to the current year", vf["year"] == dt.date.today().year)
        rows = vf["rows"]
        check("ordered by seconds watched ascending",
              all(rows[i]["watched"] <= rows[i + 1]["watched"] for i in range(len(rows) - 1)))
        check("every reel is linked", all(r["link"] for r in rows))
        # Instagram gives no video length, so no percentage may be claimed.
        txt = " ".join(video.video_note(vf))
        check("no skip percentage is claimed", "% skipped" not in txt)


def test_competitors(csv):
    print("\ncompetitors")
    cf = competitors.competitor_findings(csv)
    if cf.get("enough"):
        known = [r for r in cf["rows"] if r["followers"] is not None]
        check("known rows are sorted by size, largest first",
              all(known[i]["followers"] >= known[i + 1]["followers"]
                  for i in range(len(known) - 1)))
        check("exactly one row is ours", sum(r["ours"] for r in cf["rows"]) == 1)
        for r in cf["rows"]:
            if r.get("growth") is not None and r.get("gained") is not None:
                check(f"@{r['handle']} growth agrees with gained",
                      (r["gained"] >= 0) == (r["growth"] >= 0))


# ── rendered document ───────────────────────────────────────────────────────
def test_document(h):
    print("\nrendered page")
    check("div tags balance",
          len(re.findall(r"<div\b", h)) == len(re.findall(r"</div>", h)),
          f'{len(re.findall(r"<div\b", h))} open / {len(re.findall(r"</div>", h))} close')
    ids = re.findall(r'id="([^"]+)"', h)
    dupes = [i for i in set(ids) if ids.count(i) > 1]
    check("no duplicate ids", not dupes, str(dupes))

    idset = set(ids)
    dangling = [t for c in re.findall(r'aria-controls="([^"]+)"', h)
                for t in c.split() if t not in idset]
    check("no dangling aria-controls", not dangling, str(dangling))
    dangling2 = [t for t in re.findall(r'aria-labelledby="([^"]+)"', h)
                 if t not in idset]
    check("no dangling aria-labelledby", not dangling2, str(dangling2))

    # Exactly one visible pane per tab group, or the page shows two answers.
    for prefix in ("k", "p", "g"):
        on = re.findall(rf'id="{prefix}-\w+" [^>]*class="[^"]*is-on', h) or \
             re.findall(rf'class="pane is-on" id="{prefix}-\w+"', h)
        check(f"exactly one {prefix}- pane visible by default", len(on) == 1,
              f"{len(on)}")

    check("charts are deferred, not inlined",
          h.count("<iframe") == 0 and len(re.findall(r'class="viz" data-src', h)) == 9)
    ext = re.findall(r'<a [^>]*href="https?://[^"]+"[^>]*>', h)
    check("every external link is rel=noopener",
          all("noopener" in a for a in ext), f"{sum('noopener' not in a for a in ext)} without")
    check("landmarks present",
          "<main" in h and 'class="skip"' in h and 'name="description"' in h)
    check("build stamp present", "Page built" in h)

    # The page's own voice: no em dashes outside quoted caption text.
    text = re.sub(r"<[^>]+>", " ", h)
    check("no em dashes in the page's own copy", text.count("—") <= 1,
          f"{text.count('—')} found")


def main():
    m = render.load()
    csv = pathlib.Path("csv")
    print(f"testing against {len(m)} posts, newest {m['d'].max().date()}")
    test_analysis(m)
    test_stories(csv)
    test_followers(csv)
    test_topics(m)
    test_timing(m)
    test_video(m)
    test_competitors(csv)
    test_document(pathlib.Path("site/index.html").read_text(encoding="utf-8"))

    print(f"\n{RAN - len(FAILS)}/{RAN} passed")
    if FAILS:
        print("\nfailures:")
        for n, d in FAILS:
            print(f"  · {n}" + (f" — {d}" if d else ""))
        sys.exit(1)
    print("all invariants hold")


if __name__ == "__main__":
    main()
