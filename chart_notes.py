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
    what = ("Shares per 1,000 people reached, by format. Shares are what put you "
            "in front of people who don't already follow you, so this is the "
            "growth metric.")
    if not rates:
        return what, "Not enough posts in any one format yet to rank them."
    top = rates[0]
    says = (f"<b>Working:</b> {top[0].capitalize()}s lead at {top[1]:.1f} per 1,000 across "
            f"{top[2]} posts.")
    if len(rates) > 1:
        low = rates[-1]
        says += (f" <b>Not working:</b> {low[0].capitalize()}s at {low[1]:.1f} — "
                 f"{top[1] / low[1]:.1f}× behind." if low[1] else
                 f" <b>Not working:</b> {low[0].capitalize()}s draw almost no shares.")
    if skipped:
        says += (" Excluded: " +
                 ", ".join(f"{f.replace('IG ', '')}s ({why})" for f, why in skipped) + ".")
    return what, says


def reach_trend(m):
    t = _monthly(m)
    what = ("Median reach per post, by month. Median rather than average, so one "
            "viral post can't make a flat month look healthy.")
    if len(t) < 4:
        return what, "Needs a few more months before a trend means anything."
    last, prior = t["reach"].iloc[-1], t["reach"].iloc[-4:-1].mean()
    ch = R.pct_change(prior, last)
    d = "up" if ch > 0 else "down"
    lbl = "<b>Working:</b>" if ch > 0 else "<b>Not working:</b>"
    name = t.index[-1].strftime("%B")
    return what, (f"{lbl} {name}, the last complete month, sits at {last:,.0f} "
                  f"median reach — {d} {abs(ch):.0f}% on the three months before "
                  f"it ({prior:,.0f}). The current month is still in progress and "
                  f"is left out of this comparison.")


def volume_vs_engagement(m):
    t = _monthly(m)
    what = ("How many posts you published each month, against the engagement rate "
            "those posts earned. It answers whether posting more actually helps.")
    r = _corr(t["posts"], t["er"])
    if r is None:
        return what, "Not enough months yet to say."
    if r < -.15:
        return what, ("<b>Not working:</b> months with more posts tend to have "
                      f"<i>lower</i> engagement ({_strength(r)} negative "
                      f"relationship). Volume is not the lever — quality per post is.")
    if r > .15:
        return what, (f"<b>Working:</b> busier months engage better "
                      f"({_strength(r)} positive relationship). Consistency is "
                      f"paying off.")
    return what, ("Posting volume and engagement move independently — there is no "
                  "real relationship. Publishing more won't hurt, but it won't "
                  "lift engagement on its own either.")


def best_time(m):
    what = ("Median reach by the day and hour a post went out. Use it to schedule, "
            "not to explain why one post did well.")
    d = m.groupby("publish_weekday").agg(n=("reach", "size"), med=("reach", "median"))
    d = d[d["n"] >= R.MIN_POSTS].sort_values("med", ascending=False)
    if len(d) < 2:
        return what, "Not enough posts per day yet to rank them."
    bd, br = d.index[0], d.iloc[0]
    wd, wr = d.index[-1], d.iloc[-1]
    return what, (f"<b>Working:</b> {bd} reaches furthest — {br['med']:,.0f} median "
                  f"across {int(br['n'])} posts. <b>Not working:</b> {wd} at "
                  f"{wr['med']:,.0f} across {int(wr['n'])}. Moving a {wd} post to "
                  f"{bd} is the cheapest change on this page.")


def saves_vs_shares(m):
    sh, _ = _fmt_rates(m, "shares")
    sv, _ = _fmt_rates(m, "saved")
    what = ("Saves against shares, by format. They mean different things: a save "
            "is “useful to me later”, a share is “worth passing on”.")
    if not sh or not sv:
        return what, "Not enough posts in any one format yet."
    says = (f"Most shared: <b>{sh[0][0].capitalize()}s</b> ({sh[0][1]:.1f} per 1,000). "
            f"Most saved: <b>{sv[0][0].capitalize()}s</b> ({sv[0][1]:.1f} per 1,000).")
    if sh[0][0] == sv[0][0]:
        says += (f" The same format wins both, which is unusual and worth leaning "
                 f"into — {sh[0][0]}s are doing double duty.")
    else:
        says += (f" They differ: {sv[0][0]}s get kept for later, {sh[0][0]}s get "
                 f"passed around. Reach needs {sh[0][0].lower()}s; recruitment "
                 f"material can be {sv[0][0].lower()}s.")
    return what, says


def most_shared(m):
    what = "Your most-shared posts, ranked. The template worth copying."
    g = m.dropna(subset=["shares"]).sort_values("shares", ascending=False)
    if len(g) < 5:
        return what, "Not enough posts yet."
    top5 = g.head(5)
    part = top5["shares"].sum() / g["shares"].sum() * 100
    kinds = top5["post_type"].str.replace("IG ", "").value_counts()
    lead = f"{kinds.iloc[0]} of the top 5 are {kinds.index[0]}s"
    says = (f"The top 5 posts account for <b>{part:.0f}% of all shares</b> ever. "
            f"{lead}.")
    if part > 50:
        says += (" That concentration means the average post does very little — "
                 "the wins are rare, so study these five rather than the average.")
    return what, says


def reel_watch(m):
    what = ("Average seconds watched per reel. Watch time is what the algorithm "
            "rewards, more than likes.")
    g = m[(m["post_type"] == "IG reel") & m["avg_watch_time_sec"].notna()]
    g = g[g["avg_watch_time_sec"] > 0]
    if len(g) < 5:
        return what, "Not enough reels with watch-time data yet."
    med = g["avg_watch_time_sec"].median()
    r = _corr(g["avg_watch_time_sec"], g["reach"])
    says = f"Median watch time is <b>{med:.1f}s</b> across {len(g)} reels."
    if r is not None and r > .15:
        says += (f" <b>Working:</b> reels held longer also reach further "
                 f"({_strength(r)} positive relationship) — holding attention "
                 f"is what buys distribution.")
    elif r is not None and r < -.15:
        says += (" Longer watch times are not translating into reach here, which "
                 "usually means the opening second is losing people before the "
                 "average is measured.")
    else:
        says += (" Watch time and reach move independently so far — length is "
                 "not the thing holding reels back.")
    return what, says


def reach_vs_share_rate(m):
    what = ("One dot per post: how far it reached, against how often it was shared. "
            "It separates posts that were merely pushed from posts people chose to "
            "pass on.")
    g = m[(m["reach"] > 0) & m["shares"].notna()].copy()
    g["rate"] = g["shares"] / g["reach"] * 1000
    r = _corr(g["reach"], g["rate"])
    if r is None:
        return what, "Not enough posts yet."
    if r > .15:
        return what, (f"<b>Working:</b> your widest-reaching posts are also the most "
                      f"shared ({_strength(r)} positive relationship) — reach here "
                      f"is earned, not just served.")
    if r < -.15:
        return what, (f"<b>Not working:</b> the posts that reach furthest are shared "
                      f"<i>least</i> per viewer ({_strength(r)} negative relationship). "
                      f"Big reach is coming from distribution, not from content people "
                      f"want to pass on.")
    return what, ("Reach and share rate are unrelated — a post reaching more people "
                  "doesn't mean it resonated more. Judge posts on share rate, not "
                  "raw reach.")


def er_by_format(m):
    rates, _ = _fmt_rates(m, "total_interactions", per=100)
    what = ("Total interactions as a percentage of reach, by format. This counts "
            "likes and comments, so it measures approval rather than growth.")
    if not rates:
        return what, "Not enough posts in any one format yet."
    sh, _ = _fmt_rates(m, "shares")
    says = (f"<b>{rates[0][0].capitalize()}s</b> engage best at {rates[0][1]:.1f}% across "
            f"{rates[0][2]} posts.")
    if sh and sh[0][0] != rates[0][0]:
        says += (f" Note this disagrees with shares, where {sh[0][0]}s lead — "
                 f"{rates[0][0].lower()}s get approval from people who already "
                 f"follow you, {sh[0][0].lower()}s bring in new ones. Prefer "
                 f"{sh[0][0].lower()}s when the goal is growth.")
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
    """(what it shows, what it currently says) — or None if we have no builder."""
    fn = BUILDERS.get(title)
    if not fn:
        return None
    try:
        return fn(m)
    except Exception as e:                      # never let a note break the page
        print(f"  ! note failed for {title}: {e}")
        return None
