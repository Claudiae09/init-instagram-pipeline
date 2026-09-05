#!/usr/bin/env python3
"""
Analysis helpers for the dashboard: period comparisons, per-format guidance and
caption findings. Kept separate from generate_report.py so the rendering code
stays readable.

Every function returns plain data (numbers + strings). Nothing here writes HTML.
"""
import datetime as dt

import pandas as pd

MIN_POSTS = 3          # below this a comparison is noise, not a signal
FORMATS = ["IG carousel", "IG reel", "IG image"]


# ── shared maths ────────────────────────────────────────────────────────────
def rate(df, col, per=1000):
    r = df["reach"].sum()
    return (df[col].sum() / r * per) if r else 0.0


def pct_change(before, after):
    return ((after - before) / before * 100) if before else 0.0


def window(m, days, offset=0):
    """Posts published in the `days`-long window ending `offset` days ago."""
    end = m["d"].max() - pd.Timedelta(days=offset)
    start = end - pd.Timedelta(days=days)
    return m[(m["d"] > start) & (m["d"] <= end)]


# ── period comparison ───────────────────────────────────────────────────────
def compare_periods(m, days, label, prior_label):
    """Current window vs the one before it. Returns None when too little data."""
    cur, prev = window(m, days), window(m, days, offset=days)
    if len(cur) < MIN_POSTS:
        return {"label": label, "enough": False, "posts": len(cur),
                "prior_label": prior_label}
    d = {
        "label": label, "prior_label": prior_label, "enough": True,
        "posts": len(cur), "prev_posts": len(prev),
        "share_1k": rate(cur, "shares"), "prev_share_1k": rate(prev, "shares"),
        "reach_med": cur["reach"].median(),
        "prev_reach_med": prev["reach"].median() if len(prev) else 0,
        "er": rate(cur, "total_interactions", 100),
        "prev_er": rate(prev, "total_interactions", 100),
        "prev_enough": len(prev) >= MIN_POSTS,
    }
    d["share_change"] = pct_change(d["prev_share_1k"], d["share_1k"])
    d["reach_change"] = pct_change(d["prev_reach_med"], d["reach_med"])
    # best and worst format inside the window (needs enough posts each)
    per_fmt = []
    for f, g in cur.groupby("post_type"):
        if len(g) >= 2:
            per_fmt.append((f, rate(g, "shares"), len(g)))
    d["formats"] = sorted(per_fmt, key=lambda x: -x[1])
    return d


def period_recommendations(p):
    """Turn a comparison dict into plain-language recommendations."""
    if not p["enough"]:
        return [f"Only {p['posts']} post{'s' if p['posts'] != 1 else ''} in this window — "
                f"not enough to draw a conclusion yet. Try the longer view."]
    out = []
    # 1. sharing direction
    if p["prev_enough"] and abs(p["share_change"]) >= 10:
        up = p["share_change"] > 0
        out.append(
            f"<b>Sharing is {'up' if up else 'down'} "
            f"{abs(p['share_change']):.0f}% vs {p['prior_label']}.</b> "
            f"{p['share_1k']:.1f} shares per 1,000 reached, against "
            f"{p['prev_share_1k']:.1f} before. "
            + ("Whatever changed, keep doing it." if up else
               "This is the metric that grows you — worth diagnosing before it settles in."))
    # 2. format leader in this window
    if p["formats"]:
        top = p["formats"][0]
        out.append(
            f"<b>{top[0]}s led this {p['label'].lower()}</b> at {top[1]:.1f} shares per "
            f"1,000 reached across {top[2]} post{'s' if top[2] != 1 else ''}."
            + (f" {p['formats'][-1][0]}s trailed at {p['formats'][-1][1]:.1f}."
               if len(p["formats"]) > 1 else ""))
    # 3. reach
    if p["prev_enough"] and abs(p["reach_change"]) >= 15:
        up = p["reach_change"] > 0
        out.append(
            f"<b>Reach per post is {'up' if up else 'down'} "
            f"{abs(p['reach_change']):.0f}%.</b> Median {p['reach_med']:,.0f} vs "
            f"{p['prev_reach_med']:,.0f} in {p['prior_label']}.")
    # 4. volume vs quality
    if p["prev_enough"] and p["posts"] > p["prev_posts"] and p["er"] < p["prev_er"]:
        out.append(
            f"<b>You posted more but engaged less.</b> {p['posts']} posts vs "
            f"{p['prev_posts']}, yet engagement fell from {p['prev_er']:.1f}% to "
            f"{p['er']:.1f}%. Volume isn't the lever here.")
    if not out:
        out.append(f"<b>Steady {p['label'].lower()}.</b> {p['posts']} posts, "
                   f"{p['share_1k']:.1f} shares per 1,000 reached, median reach "
                   f"{p['reach_med']:,.0f}. Nothing moved enough to act on.")
    return out


# ── per-format guidance ─────────────────────────────────────────────────────
def best_time_for(m, fmt, min_posts=3):
    """Best day+hour for a format. Requires >= min_posts in the slot so a single
    lucky post can't set the recommendation; widens to day-only if too sparse."""
    g = m[m["post_type"] == fmt]
    if len(g) < 8:
        return None
    t = g.groupby(["publish_weekday", "publish_hour_est"]).agg(
        n=("reach", "size"), med=("reach", "median"))
    t = t[t["n"] >= min_posts].sort_values("med", ascending=False)
    if not len(t):
        # fall back to best weekday overall for this format
        d = g.groupby("publish_weekday").agg(n=("reach", "size"), med=("reach", "median"))
        d = d[d["n"] >= min_posts].sort_values("med", ascending=False)
        if not len(d):
            return None
        day, row = next(d.iterrows())
        return {"day": day, "hour": None, "median_reach": int(row["med"]),
                "n": int(row["n"])}
    (day, hour), row = next(t.iterrows())
    return {"day": day, "hour": int(hour), "median_reach": int(row["med"]),
            "n": int(row["n"])}


def format_profile(m, fmt):
    g = m[m["post_type"] == fmt]
    if not len(g):
        return None
    allm = m
    return {
        "format": fmt, "posts": len(g),
        "share_1k": rate(g, "shares"),
        "saves_1k": rate(g, "saved"),
        "er": rate(g, "total_interactions", 100),
        "reach_med": g["reach"].median(),
        "share_vs_avg": pct_change(rate(allm, "shares"), rate(g, "shares")),
        "best_time": best_time_for(m, fmt),
        # Best performer is scoped to the current year — a 2024 post is not a
        # useful template for what to make this semester.
        **_top_post_this_year(g),
    }


def _top_post_this_year(g):
    """Top post of the current year, falling back to all-time if none yet."""
    year = dt.date.today().year
    cur = g[g["d"].dt.year == year] if "d" in g.columns else g.iloc[0:0]
    scope, pool = str(year), cur
    if not len(pool):
        scope, pool = "all time", g
    if not len(pool):
        return {"top_post": None, "top_scope": scope}
    return {"top_post": pool.nlargest(1, "shares")[
        ["caption", "permalink", "shares", "reach"]].to_dict("records")[0],
        "top_scope": scope}


# ── caption findings ────────────────────────────────────────────────────────
LENGTH_BUCKETS = [(0, 150, "under 150"), (150, 300, "150–300"),
                  (300, 500, "300–500"), (500, 10 ** 6, "500+")]


def caption_findings(m, fmt=None):
    """Which caption traits go with more sharing. Returns only real signals."""
    g = m if fmt is None else m[m["post_type"] == fmt]
    g = g[g["reach"] > 0].copy()
    if len(g) < 15:
        return {"enough": False, "posts": len(g)}
    g["cap"] = g["caption"].fillna("").astype(str)
    g["len"] = g["cap"].str.len()

    # length buckets, aggregate rate per bucket
    buckets = []
    for lo, hi, name in LENGTH_BUCKETS:
        b = g[(g["len"] >= lo) & (g["len"] < hi)]
        if len(b) >= 5:
            buckets.append({"name": name, "posts": len(b), "share_1k": rate(b, "shares")})

    def split_rate(mask, label):
        a, b = g[mask], g[~mask]
        if len(a) < 5 or len(b) < 5:
            return None
        ra, rb = rate(a, "shares"), rate(b, "shares")
        return {"label": label, "with": ra, "without": rb,
                "lift": pct_change(rb, ra), "n_with": len(a)}

    traits = [t for t in [
        split_rate(g["cap"].str.contains(r"\?", regex=True), "asks a question"),
        split_rate(g["cap"].str.contains("http|link in bio", case=False), "includes a link"),
        split_rate(g["cap"].str.count("#") >= 8, "uses 8+ hashtags"),
        split_rate(g["cap"].str.contains(
            r"sign up|register|join us|rsvp|apply", case=False, regex=True), "has a clear CTA"),
    ] if t]
    return {"enough": True, "posts": len(g), "buckets": buckets,
            "traits": sorted(traits, key=lambda t: -abs(t["lift"]))}


def caption_recommendations(cf):
    """Plain-language caption guidance from the findings."""
    if not cf.get("enough"):
        return [f"Only {cf.get('posts', 0)} posts with captions here — not enough to "
                f"read caption patterns yet."]
    out = []
    b = cf["buckets"]
    if len(b) >= 2:
        best, worst = max(b, key=lambda x: x["share_1k"]), min(b, key=lambda x: x["share_1k"])
        if pct_change(worst["share_1k"], best["share_1k"]) >= 20:
            out.append(
                f"<b>Write longer captions.</b> Posts with <b>{best['name']} characters</b> "
                f"get {best['share_1k']:.1f} shares per 1,000 reached, against "
                f"{worst['share_1k']:.1f} for {worst['name']}. "
                f"Give the context — it gets shared more than a one-liner.")
    for t in cf["traits"][:3]:
        if abs(t["lift"]) < 15:
            continue
        if t["lift"] > 0:
            out.append(f"<b>Keep doing: {t['label']}.</b> Those posts earn "
                       f"{t['with']:.1f} vs {t['without']:.1f} shares per 1,000 "
                       f"(+{t['lift']:.0f}%), across {t['n_with']} posts.")
        else:
            out.append(f"<b>Reconsider: {t['label']}.</b> Those posts earn "
                       f"{t['with']:.1f} vs {t['without']:.1f} shares per 1,000 "
                       f"({t['lift']:.0f}%), across {t['n_with']} posts.")
    if not out:
        out.append("No caption pattern stands out strongly enough to act on yet.")
    return out


# ── stories ─────────────────────────────────────────────────────────────────
def story_findings(csv_dir):
    """Story completion and interaction. Honest about small samples."""
    import pandas as _pd
    p = csv_dir / "stories.csv"
    if not p.exists():
        return {"enough": False, "n": 0}
    s = _pd.read_csv(p)
    for c in ["reach", "replies", "shares", "nav_tap_exit", "nav_tap_forward",
              "nav_tap_back", "nav_swipe_forward"]:
        if c in s.columns:
            s[c] = _pd.to_numeric(s[c], errors="coerce").fillna(0)
    s = s[s.get("reach", 0) > 0]
    if len(s) < 5:
        return {"enough": False, "n": len(s)}
    total_reach = s["reach"].sum()
    out = {
        "enough": True, "n": len(s),
        "reach_med": s["reach"].median(),
        "completion": (1 - s["nav_tap_exit"].sum() / total_reach) * 100,
        "replies_per_1k": s["replies"].sum() / total_reach * 1000,
        "by_type": [],
        "thin": len(s) < 40,        # flag that this is still an early read
    }
    for t, g in s.groupby("media_type"):
        if len(g) >= 3:
            out["by_type"].append({
                "type": t.title(), "n": len(g),
                "completion": (1 - g["nav_tap_exit"].sum() / g["reach"].sum()) * 100,
                "reach_med": g["reach"].median()})
    out["by_type"].sort(key=lambda x: -x["completion"])
    return out


def story_recommendations(sf):
    if not sf.get("enough"):
        return [f"Only {sf.get('n', 0)} stories captured so far. The daily job collects "
                f"them from now on — check back in a few weeks."]
    out = [f"<b>{sf['completion']:.0f}% of viewers watch your stories through</b> "
           f"rather than tapping away, on a median reach of {sf['reach_med']:,.0f}. "
           f"Anything above roughly 70% is healthy."]
    bt = sf["by_type"]
    if len(bt) >= 2 and (bt[0]["completion"] - bt[-1]["completion"]) >= 5:
        out.append(
            f"<b>{bt[0]['type']} stories hold attention better</b> — "
            f"{bt[0]['completion']:.0f}% completion against {bt[-1]['completion']:.0f}% "
            f"for {bt[-1]['type'].lower()}. Lead with {bt[0]['type'].lower()}s when the "
            f"message matters.")
    if sf["replies_per_1k"] < 0.5:
        out.append(
            "<b>Nobody is replying.</b> Across every story captured, replies are "
            "essentially zero — which usually means there's nothing to reply <i>to</i>. "
            "Add a poll, question box or quiz sticker; stories that ask for a tap are "
            "the ones that start conversations and feed the algorithm.")
    if sf["thin"]:
        out.append(f"<i>Early read — based on {sf['n']} stories. Treat as a direction, "
                   f"not a conclusion; it firms up as the daily job collects more.</i>")
    return out


# ── why did a period move? ──────────────────────────────────────────────────
def diagnose(m, days):
    """Explain a period's share-rate change by testing the things we can measure:
    format mix, posting time, caption length, and within-window spread.

    Returns the factors that actually shifted. If none did, that is itself the
    finding — the difference is in the content, not the mechanics.
    """
    cur, prev = window(m, days), window(m, days, offset=days)
    if len(cur) < MIN_POSTS or len(prev) < MIN_POSTS:
        return None
    cur, prev = cur.copy(), prev.copy()
    for d in (cur, prev):
        d["caplen"] = d["caption"].fillna("").astype(str).str.len()
        d["rate"] = d["shares"] / d["reach"] * 1000

    out = {"factors": [], "cur_rate": rate(cur, "shares"),
           "prev_rate": rate(prev, "shares"), "n": len(cur)}

    # 1. format mix — did the share of the best format drop?
    best_fmt = max(FORMATS, key=lambda f: rate(m[m["post_type"] == f], "shares"))
    c_share = (cur["post_type"] == best_fmt).mean() * 100
    p_share = (prev["post_type"] == best_fmt).mean() * 100
    if abs(c_share - p_share) >= 15:
        out["factors"].append({
            "name": "format mix", "helped": c_share > p_share,
            "text": f"{best_fmt}s went from {p_share:.0f}% to {c_share:.0f}% of posts"})

    # 2. caption length
    cl, pl = cur["caplen"].median(), prev["caplen"].median()
    if pl and abs(pct_change(pl, cl)) >= 25:
        out["factors"].append({
            "name": "caption length", "helped": cl > pl,
            "text": f"median caption went from {pl:.0f} to {cl:.0f} characters"})

    # 3. posting hour drift
    ch, ph = cur["publish_hour_est"].median(), prev["publish_hour_est"].median()
    if abs(ch - ph) >= 2:
        out["factors"].append({
            "name": "posting time", "helped": None,
            "text": f"typical posting hour moved from {ph:.0f}:00 to {ch:.0f}:00"})

    # 4. spread — is a minority of posts dragging the average?
    weak = cur[cur["rate"] < out["cur_rate"] * 0.5]
    strong = cur[cur["rate"] > out["cur_rate"] * 1.5]
    out["weak_n"], out["strong_n"] = len(weak), len(strong)
    out["spread"] = len(weak) >= 2 and len(strong) >= 1
    out["weak_posts"] = weak.nsmallest(3, "rate")[
        ["caption", "permalink", "post_type", "reach", "shares", "rate"]
    ].to_dict("records")
    return out


def diagnosis_text(dg):
    """Plain-language 'why', including saying so when the data can't explain it."""
    if not dg:
        return []
    out = []
    helped = [f for f in dg["factors"] if f["helped"] is True]
    hurt = [f for f in dg["factors"] if f["helped"] is False]
    if hurt:
        out.append("<b>What likely hurt:</b> " +
                   "; ".join(f["text"] for f in hurt) + ".")
    if helped:
        out.append("<b>What moved in your favour:</b> " +
                   "; ".join(f["text"] for f in helped) + ".")
    if dg["spread"]:
        out.append(
            f"<b>It wasn't how much you posted — it was which posts.</b> "
            f"{dg['strong_n']} post{'s' if dg['strong_n'] != 1 else ''} did well while "
            f"{dg['weak_n']} landed under half the average. The gap between your best and "
            f"worst post this period is far bigger than the gap between periods.")
    if not hurt and dg.get("spread"):
        out.append(
            "<b>Format, timing and caption length don't separate the winners from the "
            "losers here</b> — so the difference is the content itself: the subject, the "
            "hook, the visual. Open the weak posts below and compare them to your best "
            "performer for that format.")
    return out
