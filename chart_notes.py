#!/usr/bin/env python3
"""
Short, data-derived descriptions for each Tableau chart.

Each note is two parts: what the chart plots, and what it currently says —
what is working and what is not. Everything is computed from the CSVs at build
time, so the wording follows the data instead of going stale. Nothing here is
hardcoded commentary.

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
    return (f" One caution: if you have the chart filtered to this year only, "
            f"{thin[0]}s will look like the winner, but that is off just "
            f"{thin[2]} posts. Too few to trust. The figures above use all "
            f"{len(m)} posts.")


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
    rates, skipped = _fmt_rates(m, "shares")
    what = ("How often people share your posts, per 1,000 who saw them, broken out "
            "by format. Sharing is how you reach people who don't follow you yet, "
            "so this is the number that grows the account.")
    if not rates:
        return what, "No format has enough posts yet to rank them fairly."
    top, says = rates[0], ""
    says = (f"<b>Working:</b> {top[0].capitalize()}s. They get shared {top[1]:.1f} times per "
            f"1,000 people reached, across {top[2]} posts. That is the format to "
            f"keep making.")
    if len(rates) > 1 and rates[-1][1]:
        low = rates[-1]
        says += (f" <b>Not working:</b> {low[0].capitalize()}s, at {low[1]:.1f}. They get shared "
                 f"about {top[1] / low[1]:.1f} times less often. Worth using them "
                 f"for reminders and announcements rather than for growth.")
    if skipped:
        says += (" Left out of the ranking: " +
                 ", ".join(f"{f.replace('IG ', '')}s, {why}" for f, why in skipped) + ".")
    says += _year_caution(m, "shares", 1000)
    return what, says


def reach_trend(m):
    t = _monthly(m)
    what = ("The typical reach of a post each month. We use the middle value rather "
            "than the average so that one post going viral doesn't hide a quiet "
            "month.")
    if len(t) < 4:
        return what, "We need a few more months before a trend here means much."
    last, prior = t["reach"].iloc[-1], t["reach"].iloc[-4:-1].mean()
    ch, name = R.pct_change(prior, last), t.index[-1].strftime("%B")
    tail = (" The current month is still being posted, so it is left out of this "
            "comparison.")
    if ch > 0:
        return what, (f"<b>Working:</b> {name} was your last complete month and a "
                      f"typical post reached {last:,.0f} people, up {ch:.0f}% on the "
                      f"three months before it ({prior:,.0f}). Whatever changed in "
                      f"{name}, keep doing it.{tail}")
    return what, (f"<b>Not working:</b> {name} was your last complete month and a "
                  f"typical post reached {last:,.0f} people, down {abs(ch):.0f}% on "
                  f"the three months before it ({prior:,.0f}). Reach usually slides "
                  f"when posts get more similar to each other, so it is worth "
                  f"looking at what you were making earlier in the year.{tail}")


def volume_vs_engagement(m):
    t = _monthly(m)
    what = ("How much you posted each month set against how well those posts did. "
            "It answers a question worth settling: does posting more actually help?")
    r = _corr(t["posts"], t["er"])
    if r is None:
        return what, "Not enough months of history yet to answer that."
    if r < -.15:
        return what, ("<b>Not working:</b> your busier months tend to get "
                      "<i>less</i> engagement, not more. Posting more often is not "
                      "the lever here. You will get further making fewer, stronger "
                      "posts than filling a calendar.")
    if r > .15:
        return what, ("<b>Working:</b> the months you post more are also the months "
                      "you engage better. Staying consistent is paying off, so keep "
                      "the current rhythm going.")
    return what, ("Posting more and engaging better are not connected in your data "
                  "either way. Publishing more often will not hurt you, but it will "
                  "not lift engagement on its own. What you post matters more than "
                  "how often.")


def best_time(m):
    what = ("The typical reach of a post depending on which day and hour it went "
            "out. Good for planning your schedule, not for explaining why one "
            "particular post did well.")
    d = m.groupby("publish_weekday").agg(n=("reach", "size"), med=("reach", "median"))
    d = d[d["n"] >= R.MIN_POSTS].sort_values("med", ascending=False)
    if len(d) < 2:
        return what, "Not enough posts on each day yet to rank them."
    bd, br, wd, wr = d.index[0], d.iloc[0], d.index[-1], d.iloc[-1]
    return what, (f"<b>Working:</b> {bd}. A typical {bd} post reaches "
                  f"{br['med']:,.0f} people across {int(br['n'])} posts. "
                  f"<b>Not working:</b> {wd}, at {wr['med']:,.0f} across "
                  f"{int(wr['n'])}. Shifting your {wd} posts to {bd} is the easiest "
                  f"win on this page, since it costs nothing to change.")


def saves_vs_shares(m):
    sh, _ = _fmt_rates(m, "shares")
    sv, _ = _fmt_rates(m, "saved")
    what = ("Saves set against shares, by format. The two mean different things. A "
            "save means someone wants to come back to it later. A share means they "
            "thought it was worth passing on to someone else.")
    if not sh or not sv:
        return what, "No format has enough posts yet."
    says = (f"Most shared: <b>{sh[0][0].capitalize()}s</b>, at {sh[0][1]:.1f} per 1,000 reached. "
            f"Most saved: <b>{sv[0][0].capitalize()}s</b>, at {sv[0][1]:.1f}.")
    if sh[0][0] == sv[0][0]:
        says += (f" The same format wins both, which does not happen often. "
                 f"{sh[0][0].capitalize()}s are doing double duty for you, so make "
                 f"more of them.")
    else:
        says += (f" They split. {sv[0][0].capitalize()}s get kept for later, so use "
                 f"them for things people need to act on, like deadlines and how-to "
                 f"posts. {sh[0][0].capitalize()}s get passed around, so use those "
                 f"when the goal is reaching new people.")
    return what, says


def most_shared(m):
    what = ("Your most shared posts, ranked. This is the list to actually study, "
            "because these are the posts that brought new people in.")
    g = m.dropna(subset=["shares"]).sort_values("shares", ascending=False)
    if len(g) < 5:
        return what, "Not enough posts yet."
    top5 = g.head(5)
    part = top5["shares"].sum() / g["shares"].sum() * 100
    kinds = top5["post_type"].str.replace("IG ", "").value_counts()
    says = (f"Your top 5 posts account for <b>{part:.0f}% of every share you have "
            f"ever had</b>, and {kinds.iloc[0]} of those 5 are {kinds.index[0]}s.")
    if part > 50:
        says += (" That is very concentrated. It means the typical post does almost "
                 "nothing and a handful carry everything, so copy what these five "
                 "did rather than looking at your averages.")
    else:
        says += (f" Open the top few and look for what they have in common. That is "
                 f"your template, and {kinds.index[0]}s are the format to build it "
                 f"in.")
    return what, says


def reel_watch(m):
    what = ("How many seconds people actually watch your reels for. Instagram pushes "
            "reels that hold attention much harder than it pushes reels that get "
            "likes.")
    g = m[(m["post_type"] == "IG reel") & m["avg_watch_time_sec"].notna()]
    g = g[g["avg_watch_time_sec"] > 0]
    if len(g) < 5:
        return what, "Not enough reels with watch time data yet."
    med = g["avg_watch_time_sec"].median()
    r = _corr(g["avg_watch_time_sec"], g["reach"])
    says = (f"People watch a typical reel for <b>{med:.1f} seconds</b>, across "
            f"{len(g)} reels.")
    if r is not None and r > .15:
        says += (" <b>Working:</b> the reels people stay with also travel further. "
                 "Holding attention is what buys you reach, so keep making the kind "
                 "that people watch to the end, and keep them short enough that they "
                 "do.")
    elif r is not None and r < -.15:
        says += (" Longer watch times are not turning into reach, which usually "
                 "means people are dropping off in the first second or two. The "
                 "opening frame is where to focus.")
    else:
        says += (" Watch time and reach are not moving together yet, so length is "
                 "not what is holding your reels back. The subject matters more.")
    return what, says


def reach_vs_share_rate(m):
    what = ("Every dot is one post. How far it travelled runs across, how often "
            "people shared it runs up. It separates posts Instagram simply pushed "
            "from posts people actually chose to pass on.")
    g = m[(m["reach"] > 0) & m["shares"].notna()].copy()
    g["rate"] = g["shares"] / g["reach"] * 1000
    r = _corr(g["reach"], g["rate"])
    if r is None:
        return what, "Not enough posts yet."
    if r > .15:
        return what, ("<b>Working:</b> your furthest reaching posts are also the "
                      "most shared. That means your reach is earned rather than just "
                      "handed to you, which is the healthy version of this chart. "
                      "Look at the dots in the top right and make more like them.")
    if r < -.15:
        return what, ("<b>Not working:</b> the posts that reach the most people are "
                      "shared the least by the people who see them. Big reach is "
                      "coming from Instagram pushing the post, not from people "
                      "wanting to pass it on. Judge posts by the share rate going "
                      "up the chart, not by how far right they sit.")
    return what, ("Reach and sharing are not related in your data. A post reaching "
                  "more people does not mean it landed better, so use share rate to "
                  "judge what worked, not reach.")


def er_by_format(m):
    rates, _ = _fmt_rates(m, "total_interactions", per=100)
    what = ("Likes and comments as a share of the people who saw the post, by "
            "format. This measures whether people who already follow you approve, "
            "which is a different question from whether a post grows you.")
    if not rates:
        return what, "No format has enough posts yet."
    sh, _ = _fmt_rates(m, "shares")
    says = (f"<b>{rates[0][0].capitalize()}s</b> do best here, at "
            f"{rates[0][1]:.1f}% across {rates[0][2]} posts.")
    if sh and sh[0][0] != rates[0][0]:
        says += (f" Worth knowing that this disagrees with sharing, where "
                 f"{sh[0][0]}s lead. {rates[0][0].capitalize()}s win approval from "
                 f"people who already follow you. {sh[0][0].capitalize()}s bring new "
                 f"people in. When the goal is growing, follow the sharing number.")
    says += _year_caution(m, "total_interactions", 100)
    return what, says


BUILDERS = {
    "Share rate by format": share_by_format,
    "Reach trend by month": reach_trend,
    "Posting volume vs engagement": volume_vs_engagement,
    "Best day and time to post": best_time,
    "Saves vs shares by format": saves_vs_shares,
    "Most-shared posts": most_shared,
    "Reel watch time": reel_watch,
    "Reach vs share rate, per post": reach_vs_share_rate,
    "Engagement rate by format": er_by_format,
}


def note_for(title, m):
    """(what it shows, what it currently says) or None if we have no builder."""
    fn = BUILDERS.get(title)
    if not fn:
        return None
    try:
        return fn(m)
    except Exception as e:                      # never let a note break the page
        print(f"  ! note failed for {title}: {e}")
        return None
