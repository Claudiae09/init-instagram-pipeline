#!/usr/bin/env python3
"""
Short, data-derived descriptions for each Tableau chart.

Each note is one line saying what the chart plots, plus a few short bullets
saying what it currently shows: what is working, what is not, and what to make
more of. Bullets rather than a paragraph because these sit under nine charts
and a wall of text at each one does not get read.

Everything is computed from the CSVs at build time, so the wording follows the
data instead of going stale. Nothing here is hardcoded commentary.

Scope is stated in each note, because the Tableau views may carry their own
filters and a description that quietly disagrees with the picture is worse
than no description.
"""
import datetime as dt

import pandas as pd

import report_sections as R

MIN_N = R.MIN_FMT_POSTS          # don't call a format a winner below this
CONC = R.MAX_POST_CONCENTRATION  # or when one post carries it


def _fmt_rates(m, col, per=1000):
    """Per-format rate, dropping formats too thin or too outlier-driven to trust."""
    keep, skipped = [], []
    for f, g in m.groupby("post_type"):
        if len(g) < MIN_N:
            skipped.append((f, f"only {len(g)} posts"))
            continue
        tot = g[col].sum()
        if tot > 0 and g[col].max() / tot > CONC:
            skipped.append((f, "one post carries most of it"))
            continue
        keep.append((f.replace("IG ", ""), R.rate(g, col, per), len(g)))
    return sorted(keep, key=lambda x: -x[1]), skipped


def _corr(x, y):
    """Pearson r, guarding the degenerate cases that make it meaningless."""
    x, y = pd.Series(x).astype(float), pd.Series(y).astype(float)
    ok = x.notna() & y.notna()
    if ok.sum() < 6 or x[ok].nunique() < 3 or y[ok].nunique() < 3:
        return None
    r = x[ok].corr(y[ok])          # pandas, so numpy stays a transitive dep
    return None if pd.isna(r) else float(r)


def _strength(r):
    a = abs(r)
    return "no real" if a < .15 else "a weak" if a < .35 else \
           "a moderate" if a < .6 else "a strong"


def _year_caution(m, col, per):
    """Warn when a current-year view flips the ranking on a thin sample.

    Sheet1 and Sheet6 in Tableau are filtered to the current year, where a
    format with a handful of posts can top the chart. That contradicts the
    note sitting above it, so say why rather than leaving the reader to guess
    which one to believe."""
    import datetime as _dt
    cur = m[m["d"].dt.year == _dt.date.today().year]
    if not len(cur):
        return ""
    ranked = []
    for f, g in cur.groupby("post_type"):
        if g["reach"].sum():
            ranked.append((f.replace("IG ", ""), g[col].sum() / g["reach"].sum() * per,
                           len(g)))
    ranked.sort(key=lambda x: -x[1])
    allh, _ = _fmt_rates(m, col, per)
    if not ranked or not allh or ranked[0][0] == allh[0][0]:
        return ""
    thin = ranked[0]
    return (f"<b>Caution:</b> with the chart filtered to this year, {thin[0]}s look "
            f"like the winner, but that is off just {thin[2]} posts. These figures "
            f"use all {len(m)}.")


def _monthly(m, complete_only=True):
    """Monthly aggregates. The current calendar month is still being written —
    it has a partial post count and a partial reach curve — so comparing it to
    finished months reads as a collapse that hasn't happened. Drop it."""
    g = m.dropna(subset=["d"]).copy()
    g["ym"] = g["d"].dt.to_period("M")
    t = g.groupby("ym").agg(posts=("reach", "size"), reach=("reach", "median"),
                            inter=("total_interactions", "sum"),
                            rch=("reach", "sum")).assign(
        er=lambda t: t["inter"] / t["rch"] * 100)
    if complete_only and len(t):
        this_month = pd.Period(dt.date.today(), freq="M")
        t = t[t.index < this_month]
    return t


# ── one function per chart ──────────────────────────────────────────────────
def share_by_format(m):
    what = ("How often people share your posts, per 1,000 who saw them. Sharing is "
            "what reaches people who don't follow you yet.")
    rates, skipped = _fmt_rates(m, "shares")
    if not rates:
        return what, ["No format has enough posts yet to rank them fairly."]
    top = rates[0]
    out = [f"<b>Working:</b> {top[0].capitalize()}s, at {top[1]:.1f} per 1,000 "
           f"across {top[2]} posts. Make more of these."]
    if len(rates) > 1 and rates[-1][1]:
        low = rates[-1]
        out.append(f"<b>Not working:</b> {low[0].capitalize()}s, at {low[1]:.1f}. "
                   f"Use them for reminders, not for growth.")
    if skipped:
        out.append("Left out: " + ", ".join(f"{f.replace('IG ', '')}s, {w}"
                                            for f, w in skipped) + ".")
    c = _year_caution(m, "shares", 1000)
    if c:
        out.append(c)
    return what, out


def reach_trend(m):
    what = ("The typical reach of a post each month. We use the middle value so one "
            "viral post can't hide a quiet month.")
    t = _monthly(m)
    if len(t) < 4:
        return what, ["We need a few more months before this means much."]
    last, prior = t["reach"].iloc[-1], t["reach"].iloc[-4:-1].mean()
    ch, name = R.pct_change(prior, last), t.index[-1].strftime("%B")
    if ch > 0:
        out = [f"<b>Working:</b> {name} reached {last:,.0f} per post, up {ch:.0f}% "
               f"on the three months before ({prior:,.0f}).",
               f"Whatever changed in {name}, keep doing it."]
    else:
        out = [f"<b>Not working:</b> {name} reached {last:,.0f} per post, down "
               f"{abs(ch):.0f}% on the three months before ({prior:,.0f}).",
               "Reach slides when posts get samey. Look at what you made earlier "
               "in the year."]
    out.append("The current month is still being posted, so it is left out.")
    return what, out


def volume_vs_engagement(m):
    what = ("How much you posted each month against how well it did. It settles "
            "whether posting more actually helps.")
    r = _corr(_monthly(m)["posts"], _monthly(m)["er"])
    if r is None:
        return what, ["Not enough months of history yet."]
    if r < -.15:
        return what, ["<b>Not working:</b> your busier months get <i>less</i> "
                      "engagement, not more.",
                      "Fewer, stronger posts will beat filling the calendar."]
    if r > .15:
        return what, ["<b>Working:</b> the months you post more are the months you "
                      "engage better.",
                      "Keep the rhythm you have."]
    return what, ["Posting more and engaging better are not connected either way "
                  "in your data.",
                  "What you post matters more than how often."]


def best_time(m):
    what = ("Typical reach depending on the day and hour a post goes out. Good for "
            "planning, not for explaining one post.")
    d = m.groupby("publish_weekday").agg(n=("reach", "size"), med=("reach", "median"))
    d = d[d["n"] >= R.MIN_POSTS].sort_values("med", ascending=False)
    if len(d) < 2:
        return what, ["Not enough posts on each day yet."]
    bd, br, wd, wr = d.index[0], d.iloc[0], d.index[-1], d.iloc[-1]
    return what, [f"<b>Working:</b> {bd}, at {br['med']:,.0f} typical reach across "
                  f"{int(br['n'])} posts.",
                  f"<b>Not working:</b> {wd}, at {wr['med']:,.0f} across "
                  f"{int(wr['n'])}.",
                  f"Move your {wd} posts to {bd}. It costs nothing to change."]


def saves_vs_shares(m):
    what = ("Saves against shares. A save means someone wants it later. A share "
            "means they passed it to someone else.")
    sh, _ = _fmt_rates(m, "shares")
    sv, _ = _fmt_rates(m, "saved")
    if not sh or not sv:
        return what, ["No format has enough posts yet."]
    out = [f"<b>Most shared:</b> {sh[0][0].capitalize()}s, {sh[0][1]:.1f} per 1,000.",
           f"<b>Most saved:</b> {sv[0][0].capitalize()}s, {sv[0][1]:.1f} per 1,000."]
    if sh[0][0] == sv[0][0]:
        out.append(f"The same content type wins both, which is rare. Make more "
                   f"{sh[0][0]}s.")
    else:
        out.append(f"Use {sv[0][0]}s for deadlines and how-to posts. Use "
                   f"{sh[0][0]}s when you want new people.")
    return what, out


def most_shared(m):
    what = "Your most shared posts, ranked. These are the ones that brought people in."
    g = m.dropna(subset=["shares"]).sort_values("shares", ascending=False)
    if len(g) < 5:
        return what, ["Not enough posts yet."]
    top5 = g.head(5)
    part = top5["shares"].sum() / g["shares"].sum() * 100
    kinds = top5["post_type"].str.replace("IG ", "").value_counts()
    out = [f"Your top 5 posts are <b>{part:.0f}% of every share you have ever had</b>.",
           f"{kinds.iloc[0]} of those 5 are {kinds.index[0]}s."]
    if part > 50:
        out.append("That is very concentrated. Copy what these five did rather than "
                   "looking at your averages.")
    else:
        out.append(f"Open the top few and find what they have in common. That is "
                   f"your template, built as a {kinds.index[0]}.")
    return what, out


def reel_watch(m):
    what = ("How long people actually watch your reels. Instagram pushes reels that "
            "hold attention harder than ones that get likes.")
    g = m[(m["post_type"] == "IG reel") & m["avg_watch_time_sec"].notna()]
    g = g[g["avg_watch_time_sec"] > 0]
    if len(g) < 5:
        return what, ["Not enough reels with watch time data yet."]
    med = g["avg_watch_time_sec"].median()
    r = _corr(g["avg_watch_time_sec"], g["reach"])
    out = [f"People watch a typical reel for <b>{med:.1f} seconds</b>, across "
           f"{len(g)} reels."]
    if r is not None and r > .15:
        out += ["<b>Working:</b> the reels people stay with also reach further.",
                "Keep them short enough that people finish them."]
    elif r is not None and r < -.15:
        out += ["Longer watch times are not turning into reach.",
                "People are dropping off in the first second or two. Fix the "
                "opening frame."]
    else:
        out.append("Length is not what is holding your reels back. The subject "
                   "matters more.")
    return what, out


def reach_vs_share_rate(m):
    what = ("Each dot is one post. How far it travelled runs across, how often it "
            "was shared runs up.")
    g = m[(m["reach"] > 0) & m["shares"].notna()].copy()
    g["rate"] = g["shares"] / g["reach"] * 1000
    r = _corr(g["reach"], g["rate"])
    if r is None:
        return what, ["Not enough posts yet."]
    if r > .15:
        return what, ["<b>Working:</b> your furthest reaching posts are also the "
                      "most shared.",
                      "That means your reach is earned, not just handed to you.",
                      "Look at the dots in the top right and make more like them."]
    if r < -.15:
        return what, ["<b>Not working:</b> the posts reaching the most people are "
                      "shared the least by those who see them.",
                      "That reach is Instagram pushing the post, not people passing "
                      "it on.",
                      "Judge posts by how high they sit, not how far right."]
    return what, ["Reach and sharing are not related in your data.",
                  "Reaching more people does not mean a post landed better. Use "
                  "share rate to judge what worked."]


def er_by_format(m):
    what = ("Likes and comments as a share of who saw the post. This is approval "
            "from people who already follow you, not growth.")
    rates, _ = _fmt_rates(m, "total_interactions", per=100)
    if not rates:
        return what, ["No format has enough posts yet."]
    sh, _ = _fmt_rates(m, "shares")
    out = [f"<b>{rates[0][0].capitalize()}s</b> lead at {rates[0][1]:.1f}% across "
           f"{rates[0][2]} posts."]
    if sh and sh[0][0] != rates[0][0]:
        out.append(f"This disagrees with sharing, where {sh[0][0]}s lead. When the "
                   f"goal is growing, follow the sharing number.")
    c = _year_caution(m, "total_interactions", 100)
    if c:
        out.append(c)
    return what, out


BUILDERS = {
    "Share rate by content type": share_by_format,
    "Reach trend by month": reach_trend,
    "Posting volume vs engagement": volume_vs_engagement,
    "Best day and time to post": best_time,
    "Saves vs shares by content type": saves_vs_shares,
    "Most-shared posts": most_shared,
    "Reel watch time": reel_watch,
    "Reach vs share rate, per post": reach_vs_share_rate,
    "Engagement rate by content type": er_by_format,
}


def note_for(title, m):
    """(what it shows, [short bullets]) or None if we have no builder."""
    fn = BUILDERS.get(title)
    if not fn:
        return None
    try:
        return fn(m)
    except Exception as e:                      # never let a note break the page
        print(f"  ! note failed for {title}: {e}")
        return None
