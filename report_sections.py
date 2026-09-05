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
MIN_ER_DELTA = 0.5     # percentage points; below this an engagement move is noise
MIN_VOLUME_POSTS = 8   # don't prescribe from a handful of posts
MIN_FMT_POSTS = 5      # minimum posts before we call a format a winner
MAX_POST_CONCENTRATION = 0.45   # if one post is >45% of a format's shares, skip it
FORMATS = ["IG carousel", "IG reel", "IG image"]


# ── shared maths ────────────────────────────────────────────────────────────
def rate(df, col, per=1000):
    r = df["reach"].sum()
    return (df[col].sum() / r * per) if r else 0.0


def pct_change(before, after):
    return ((after - before) / before * 100) if before else 0.0


def window(m, days, offset=0):
    """Posts published in the `days`-long window ending `offset` days ago.

    `days=None` means "this calendar year to date" (and with an offset, the same
    span of the previous year) so the Year view is genuinely about this year,
    not a rolling 365 days straddling two.
    """
    if days is None:
        today = m["d"].max()
        year = today.year - (1 if offset else 0)
        start = pd.Timestamp(year=year, month=1, day=1)
        end = today.replace(year=year) if offset else today
        return m[(m["d"] >= start) & (m["d"] <= end)]
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
    # Best/worst format inside the window. Two guards, because a format with a
    # handful of posts and one viral outlier will otherwise look like the winner:
    #   1. at least MIN_FMT_POSTS posts
    #   2. no single post may account for most of that format's shares
    per_fmt, excluded = [], []
    for f, g in cur.groupby("post_type"):
        r, n = rate(g, "shares"), len(g)
        tot = g["shares"].sum()
        conc = (g["shares"].max() / tot) if tot else 0
        if n < MIN_FMT_POSTS:
            excluded.append({"fmt": f, "rate": r, "n": n, "why": "posts"})
            continue
        if tot > 0 and conc > MAX_POST_CONCENTRATION:
            excluded.append({"fmt": f, "rate": r, "n": n, "why": "concentration",
                             "conc": conc})
            continue
        per_fmt.append((f, r, n))
    d["formats"] = sorted(per_fmt, key=lambda x: -x[1])
    # A format the reader can see in its own tab must not silently vanish from
    # the headline. Keep the ones that would look like they beat the leader.
    d["excluded"] = sorted(excluded, key=lambda e: -e["rate"])
    return d


def period_recommendations(p):
    """Turn a comparison dict into plain-language recommendations."""
    if not p["enough"]:
        return [f"Only {p['posts']} post{'s' if p['posts'] != 1 else ''} in this window, "
                f"which is not enough to draw a conclusion yet. Try the longer view."]
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
               "Worth looking into before it settles in."))
    # 2. format leader in this window
    if p["formats"]:
        top = p["formats"][0]
        out.append(
            f"<b>{top[0]}s led this {p['label'].lower()}</b> at {top[1]:.1f} shares per "
            f"1,000 reached, across {top[2]} post{'s' if top[2] != 1 else ''}. "
            f"That is the content type to make more of."
            + (f" {p['formats'][-1][0]}s trailed at {p['formats'][-1][1]:.1f}."
               if len(p["formats"]) > 1 else ""))
        # Close the contradiction: if an excluded format scores higher than the
        # named leader, the reader will find it one tab away.
        beats = [e for e in p.get("excluded", []) if e["rate"] > top[1]]
        if beats:
            e = beats[0]
            why = (f"on {e['n']} post{'s' if e['n'] != 1 else ''}"
                   + (f" with one carrying {e['conc']:.0%} of them"
                      if e.get("conc") else ""))
            out.append(
                f"{e['fmt']}s scored {e['rate']:.1f}, but {why}. Not enough to "
                f"call, which is why they are not the recommendation.")
    # 3. reach
    if p["prev_enough"] and abs(p["reach_change"]) >= 15:
        up = p["reach_change"] > 0
        out.append(
            f"<b>Reach per post is {'up' if up else 'down'} "
            f"{abs(p['reach_change']):.0f}%.</b> Median {p['reach_med']:,.0f} vs "
            f"{p['prev_reach_med']:,.0f} in {p['prior_label']}.")
    # 4. volume vs quality
    if (p["prev_enough"] and p["posts"] > p["prev_posts"]
            and (p["prev_er"] - p["er"]) >= MIN_ER_DELTA
            and p["posts"] >= MIN_VOLUME_POSTS):
        out.append(
            f"<b>You posted more but engaged less.</b> {p['posts']} posts against "
            f"{p['prev_posts']}, yet engagement fell from {p['prev_er']:.1f}% to "
            f"{p['er']:.1f}%. Fewer, stronger posts beat filling the calendar.")
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
        return [f"Only {cf.get('posts', 0)} posts with captions here, not enough to "
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
                f"Give people the context.")
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
def story_findings(csv_dir, days=None):
    """Story completion and interaction, optionally scoped to a period.

    `days=None` means this calendar year; an integer means the last N days.
    Windowing uses the stories' own timestamps, which run ahead of the media
    pull because stories are collected daily."""
    import pandas as _pd
    p = csv_dir / "stories.csv"
    if not p.exists():
        return {"enough": False, "n": 0}
    s = _pd.read_csv(p)
    for c in ["reach", "replies", "shares", "follows", "profile_visits",
              "profile_activity", "total_interactions", "nav_tap_exit",
              "nav_tap_forward", "nav_tap_back", "nav_swipe_forward"]:
        if c in s.columns:
            s[c] = _pd.to_numeric(s[c], errors="coerce").fillna(0)
    s = s[s.get("reach", 0) > 0]
    data_start = newest = requested_start = None
    if "timestamp" in s.columns and len(s):
        s = s.copy()
        s["_ts"] = _pd.to_datetime(s["timestamp"], errors="coerce", utc=True)
        s = s.dropna(subset=["_ts"])
        if len(s):
            newest = s["_ts"].max()
            data_start = s["_ts"].min()
            if days is None:
                requested_start = _pd.Timestamp(year=newest.year, month=1, day=1,
                                                tz="UTC")
            else:
                requested_start = newest - _pd.Timedelta(days=days)
            s = s[s["_ts"] >= requested_start]
    if len(s) < 5:
        return {"enough": False, "n": len(s), "days": days}
    total_reach = s["reach"].sum()
    # Each row is one story FRAME. Several frames posted back to back are a
    # single story you tap through, so count sets too — a gap of more than an
    # hour starts a new set. "17 frames" and "10 sets" mean different things
    # and the page should not conflate them.
    _t = s["_ts"].sort_values() if "_ts" in s.columns else None
    if _t is not None and len(_t):
        sets = int((_t.diff() > _pd.Timedelta(hours=1)).sum()) + 1
        days_active = int(_t.dt.tz_convert("America/New_York").dt.date.nunique())
    else:
        sets, days_active = len(s), len(s)
    out = {
        "enough": True, "n": len(s), "days": days,
        "sets": sets, "days_active": days_active,
        "reach_med": s["reach"].median(),
        "completion": (1 - s["nav_tap_exit"].sum() / total_reach) * 100,
        "replies_per_1k": s["replies"].sum() / total_reach * 1000,
        "shares": s["shares"].sum() if "shares" in s else 0,
        "replies": s["replies"].sum() if "replies" in s else 0,
        "follows": s["follows"].sum() if "follows" in s else 0,
        "profile_visits": s["profile_visits"].sum() if "profile_visits" in s else 0,
        "interactions": s["total_interactions"].sum() if "total_interactions" in s else 0,
        # Instagram does not expose poll votes, quiz answers or question replies.
        # total_interactions minus the parts we CAN see approximates likes and
        # sticker taps — the closest available read on sticker engagement.
        "passive": max(0, (s["total_interactions"].sum() if "total_interactions" in s else 0)
                       - (s["replies"].sum() if "replies" in s else 0)
                       - (s["shares"].sum() if "shares" in s else 0)),
        "total_reach": total_reach,
        # Daily story collection started partway through the year, so a 30-day
        # and a year-to-date window can cover the identical set of stories.
        # Flag that, otherwise the page looks broken when the numbers repeat.
        "since": (f"{data_start.day} {data_start.strftime('%b %Y')}"
                  if data_start is not None else None),
        "span_days": (int((newest - data_start).days) + 1
                      if data_start is not None else None),
        "truncated": bool(data_start is not None
                          and requested_start is not None
                          and data_start > requested_start),
        # The date this window stops being partial: once collection is `days`
        # old, a rolling window is fully covered. The year-to-date window is
        # only whole once the calendar rolls past the first collection year.
        "complete_on": (
            (data_start + _pd.Timedelta(days=days)).strftime("%-d %b %Y")
            if data_start is not None and days is not None
            else (f"1 Jan {data_start.year + 1}" if data_start is not None else None)),
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
        return [f"Only {sf.get('n', 0)} stories captured in this window. The daily job "
                f"collects them from now on, so check back in a few weeks."]
    out = [f"<b>{sf['completion']:.0f}% of viewers watch through</b> rather than tapping "
           f"away, on a median reach of {sf['reach_med']:,.0f}. Above roughly 70% is healthy."]

    bt = sf["by_type"]
    if len(bt) >= 2 and (bt[0]["completion"] - bt[-1]["completion"]) >= 5:
        out.append(
            f"<b>{bt[0]['type']} stories hold attention better.</b> "
            f"{bt[0]['completion']:.0f}% of people watch them through, against "
            f"{bt[-1]['completion']:.0f}% for {bt[-1]['type'].lower()}. Lead with "
            f"{bt[0]['type'].lower()}s when the story actually matters.")

    # what kind of engagement is actually happening
    if sf.get("interactions"):
        out.append(
            f"<b>Engagement is passive.</b> Of {sf['interactions']:.0f} interactions, "
            f"about {sf['passive']:.0f} are likes or sticker taps, {sf['shares']:.0f} are "
            f"shares and {sf['replies']:.0f} are replies. Add a poll or question "
            f"sticker to turn taps into actual replies.")

    # conversion: does any of this reach go anywhere?
    if sf.get("total_reach"):
        out.append(
            f"<b>Stories aren't converting.</b> {sf['total_reach']:,.0f} people reached "
            f"produced {sf['profile_visits']:.0f} profile visits and "
            f"{sf['follows']:.0f} follows. Add a link sticker or a "
            f"'tap the profile' line.")

    out.append("<i>Poll votes, quiz answers and question replies are app-only, so "
               "the API cannot see them. The likes and stickers figure is "
               "worked out from total interactions.</i>")
    if sf.get("truncated"):
        pass                      # covered by the banner at the top of the pane
    elif sf["thin"]:
        out.append(f"<i>Early read, based on {sf['n']} stories. It firms up as the "
                   f"daily job keeps running.</i>")
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
            f"<b>It was not how much you posted, it was which posts.</b> "
            f"{dg['strong_n']} post{'s' if dg['strong_n'] != 1 else ''} did well while "
            f"{dg['weak_n']} landed under half the average. The spread between your "
            f"own posts is wider than the change between periods.")
    if not hurt and dg.get("spread"):
        out.append(
            "<b>Format, timing and caption length don't separate the winners from "
            "the losers here.</b> The difference is the content itself: subject, "
            "hook, visual. Compare the weak posts below against your best.")
    return out


# ── why did ONE post underperform? ──────────────────────────────────────────
def explain_post(m, post):
    """Compare a weak post against its own format's benchmarks and say what
    plausibly went wrong — distribution, timing, caption, or the content itself.
    Returns (diagnosis, suggestion)."""
    fmt = post["post_type"]
    peers = m[m["post_type"] == fmt]
    if len(peers) < 8:
        return ("Not enough posts of this format to compare against yet.", "")

    peer_reach = peers["reach"].median()
    peer_rate = rate(peers, "shares")
    caplen = len(str(post.get("caption") or ""))
    peer_cap = peers["caption"].fillna("").astype(str).str.len().median()
    hour = post.get("publish_hour_est")

    # was it seen? reach well below the format's normal
    seen_badly = post["reach"] < peer_reach * 0.7
    # was it seen but ignored?
    ignored = (not seen_badly) and post["rate"] < peer_rate * 0.5

    bits, fix = [], []
    if seen_badly:
        bits.append(f"it reached {post['reach']:,.0f} people against a typical "
                    f"{peer_reach:,.0f} for {fmt.replace('IG ','')}s, so it did not get "
                    f"distributed")
        best = best_time_for(m, fmt)
        if best and hour is not None and abs(int(hour) - (best["hour"] or int(hour))) >= 2:
            bits.append(f"it went out at {int(hour)}:00, away from the "
                        f"{best['day']} {best['hour']}:00 slot that reaches most")
            fix.append(f"try this content again in the {best['day']} "
                       f"{best['hour'] % 12 or 12}"
                       f"{'am' if best['hour'] < 12 else 'pm'} slot")
        else:
            fix.append("the hook or opening frame likely didn't hold people in the "
                       "first seconds, since that is what drives distribution")
    if ignored:
        bits.append(f"plenty of people saw it ({post['reach']:,.0f}) but almost nobody "
                    f"passed it on")
        if caplen < peer_cap * 0.75:
            bits.append(f"its caption is {caplen} characters against a typical "
                        f"{peer_cap:.0f}")
            fix.append("give it the context that makes it worth forwarding: who it is "
                       "for, why it matters, what happens next")
        else:
            fix.append("this reads as an announcement rather than something someone "
                       "would send to a friend. Add a reason to share: name the person "
                       "it helps, or make it feel like news worth passing on")
    if fmt == "IG image":
        fix.append("single graphics are your weakest content type for sharing, so the same "
                   "message as a carousel usually travels further")
    if not bits:
        bits.append("nothing in the timing, format or caption stands out, so this looks "
                    "like the content simply didn't land")
        fix.append("compare it against your best performer for this format and look at "
                   "the difference in subject and hook")
    return ("Likely why: " + "; ".join(bits) + ".",
            "Try next: " + "; ".join(fix) + "." if fix else "")


def format_in_window(m, fmt, days):
    """Period-scoped view of one format: what it did in this window only.
    Guidance that needs volume (best time, captions) stays on full history."""
    w = window(m, days)
    g = w[w["post_type"] == fmt]
    if not len(g):
        return {"posts": 0, "top": None}
    top = g.nlargest(1, "shares")[
        ["caption", "permalink", "shares", "reach"]].to_dict("records")[0]
    tot = g["shares"].sum()
    return {
        "posts": len(g),
        "share_1k": rate(g, "shares"),
        "reach_med": g["reach"].median(),
        "top": top,
        # flag when one post is doing all the work, so the UI can say so
        "concentrated": bool(tot > 0 and g["shares"].max() / tot > MAX_POST_CONCENTRATION
                             and len(g) >= 2),
        "thin": len(g) < MIN_FMT_POSTS,
    }
