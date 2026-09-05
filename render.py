#!/usr/bin/env python3
"""
Renders site/index.html: a recommendations-first dashboard.

Structure — deliberately not a stack of equal cards:
  1. One decision card at the top, with Week / Month / Year buttons
  2. Per-format guidance behind tabs (carousel / reel / graphic)
  3. Caption guidance
  4. The Tableau charts, collapsed behind a disclosure ("see the data")

The page is one static HTML file. The only JavaScript is ~20 lines of tab
switching; every number is baked in at build time.
"""
import datetime as dt
import html
from pathlib import Path

import pandas as pd

import audience as AU
import timing as TM
import chart_notes as CN
import competitors as CP
import report_sections as R
import topics as TP

HERE = Path(__file__).resolve().parent
CSV = HERE / "csv"
OUT = HERE / "site"
OUT.mkdir(exist_ok=True)

TABLEAU_WORKBOOK = "Init-Instagram"
TABLEAU_PROFILE = "claudia.espinosa3716"
TABLEAU_HOME = (f"https://public.tableau.com/app/profile/{TABLEAU_PROFILE}"
                f"/viz/{TABLEAU_WORKBOOK}/Sheet1")

# section title -> published Tableau sheet
CHARTS = [
    ("Share rate by content type", "Sheet1"),
    ("Reach trend by month", "Sheet2"),
    ("Posting volume vs engagement", "Sheet4"),
    ("Best day and time to post", "Sheet5"),
    ("Saves vs shares by content type", "Sheet7"),
    ("Most-shared posts", "Sheet8"),
    ("Reel watch time", "Sheet9"),
    ("Reach vs share rate, per post", "Sheet3"),
    ("Engagement rate by content type", "Sheet6"),
]

PERIODS = [("week", "Week", 7, "the week before"),
           ("month", "Month", 30, "the month before"),
           ("year", "Year", None, "the same span last year")]

FORMAT_LABEL = {"IG carousel": "Carousels", "IG reel": "Reels", "IG image": "Graphics"}


def esc(s):
    return html.escape(str(s))


def load():
    m = pd.read_csv(CSV / "media_performance.csv")
    for c in ["reach", "shares", "saved", "total_interactions", "likes",
              "comments", "views", "avg_watch_time_sec", "follows", "profile_visits"]:
        if c in m.columns:
            m[c] = pd.to_numeric(m[c], errors="coerce")
    m["d"] = pd.to_datetime(m["publish_date_est"], errors="coerce")
    return m.dropna(subset=["d"])


def hour_label(h):
    if h is None:
        return ""
    return f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"


# ── page pieces ─────────────────────────────────────────────────────────────
def kpi_panes(m):
    """One KPI strip per period; the page-level control swaps them."""
    out = []
    for i, (key, label, days, _p) in enumerate(PERIODS):
        on = " is-on" if i == 1 else ""
        out.append(f'<div class="pane{on}" id="k-{key}" role="tabpanel" '
                   f'aria-labelledby="t-{key}">{kpi_strip(m, days, label)}</div>')
    return f'<div class="stage" data-stage="k">{"".join(out)}</div>'


def competitor_section(m):
    """Where the account sits against the other orgs competing for the same
    students. Always renders the table, blanks included, so the accounts being
    tracked are visible on the page rather than only in a spreadsheet."""
    cf = CP.competitor_findings(CSV)
    notes = "".join(f"<li>{n}</li>" for n in CP.competitor_note(cf))
    if not cf.get("enough"):
        return ('<section class="block panel"><h2>How you compare</h2>'
                f'<ul class="csays">{notes}</ul></section>')

    # Growth columns need a second reading to subtract from; an empty column
    # reads as broken rather than as pending, so they appear when they can.
    has_growth = any(r.get("growth") is not None for r in cf["rows"])
    body = []
    for r in cf["rows"]:
        me = " me" if r["ours"] else ""
        name = (f'<a class="tlink" href="https://www.instagram.com/'
                f'{esc(r["handle"])}/" target="_blank" rel="noopener">'
                f'@{esc(r["handle"])}</a>')
        fol = f'{r["followers"]:,.0f}' if r["followers"] is not None else "—"
        cells = f'<td>{name}</td><td class="n">{fol}</td>'
        if has_growth:
            g = r.get("gained")
            cells += f'<td class="n">{g:+,.0f}</td>' if g is not None else '<td class="n">—</td>'
            pct = r.get("growth")
            if pct is None:
                cells += '<td class="n">—</td>'
            else:
                # Red where someone is gaining on us in percentage terms, which
                # is the thing raw follower counts hide.
                cls = ("up" if r["ours"] else
                       "down" if r.get("outpacing") else "")
                cells += f'<td class="n {cls}">{pct:+.1f}%</td>'
        body.append(f'<tr class="crow{me}">{cells}</tr>')

    stamp = f'As recorded {cf["as_of"]:%d %b %Y}'
    if has_growth:
        stamp += (f'. Gained and Growth are since '
                  f'{cf["tracked_since"]:%d %b %Y}, across {cf["weeks"]} '
                  f'readings.')
    else:
        stamp += '.'
    return ('<section class="block panel"><h2>How you compare</h2>'
            f'<p class="sub2">The accounts competing for the same students. '
            f'{stamp} Updated monthly.</p>'
            '<div class="tw"><table class="topics compact"><thead><tr>'
            '<th>Account</th><th class="n">Followers</th>'
            + ('<th class="n">Gained</th><th class="n">Growth</th>'
               if has_growth else '')
            + f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
            f'<ul class="csays">{notes}</ul></section>')


def guidance_card(m):
    """When to post and how often. Deliberately not period-scoped: a single
    week cannot place a best time, and cadence is a question about weeks."""
    pf = TM.posting_findings(m)
    if not pf.get("enough") or "day" not in pf:
        return ""
    when = f'{pf["day"]}'
    if pf.get("hour") is not None:
        when += f', {hour_label(pf["hour"])}'      # short enough for one line
    band = pf.get("best_band")
    cells = [
        ("Best day to post", when,
         f'median reach {pf["day_reach"]:,} across {pf["day_n"]} posts'),
    ]
    if band:
        cells.append(("How often", f'{band["label"]} a week',
                      f'{band["rate"]:.1f} shares per 1,000 across '
                      f'{band["weeks"]} weeks'))
    if pf.get("recent_avg") is not None:
        cells.append(("You are posting", f'{pf["recent_avg"]:.1f} a week',
                      f'average of the last {pf["recent_weeks"]} weeks'))
    tiles = "".join(
        f'<div class="kpi"><span class="kl">{esc(l)}</span>'
        f'<span class="kv kvs">{esc(v)}</span>'
        f'<span class="kd">{esc(d)}</span></div>' for l, v, d in cells)
    notes = "".join(f"<li>{n}</li>" for n in TM.posting_note(pf))
    return ('<section class="block panel"><h2>When and how often to post</h2>'
            '<p class="sub2">Weekly guidance from your full history, so this '
            'one does not follow the period above.</p>'
            f'<div class="kpis kpis-3">{tiles}</div>'
            + (f'<ul class="csays">{notes}</ul>' if notes else "")
            + "</section>")


def period_bar():
    """The period control, lifted out of the decision card.

    It always drove the format panes further down the page as well, which meant
    clicking it changed things the reader could not see. As a page-level filter
    it looks like what it is.
    """
    tabs = []
    for i, (key, label, days, _prior) in enumerate(PERIODS):
        sel = (i == 1)
        tabs.append(f'<button class="seg{" is-on" if sel else ""}" '
                    f'data-period="{key}" id="t-{key}" role="tab" '
                    f'aria-controls="k-{key} p-{key} g-{key}" '
                    f'aria-selected="{str(sel).lower()}" '
                    f'tabindex="{0 if sel else -1}">{label}</button>')
    return ('<div class="chrome"><div class="toolbar">'
            '<span class="tlabel">Showing</span>'
            f'<div class="segs" role="tablist" aria-label="Time period">'
            f'<span class="segpill" aria-hidden="true"></span>{"".join(tabs)}</div>'
            '<span class="thint">Changes every section below</span>'
            '</div></div>')


def kpi_strip(m, days, label):
    """The four numbers someone opens a dashboard to see, before any prose."""
    g = AU.follower_growth(CSV, days)
    cur = R.window(m, days)
    prev = R.window(m, days, offset=days) if days else R.window(m, None, offset=1)
    span = label.lower()
    tiles = []

    if g.get("enough"):
        if g.get("reportable"):
            up = g["change"] >= 0
            tiles.append(("Followers", f"{g['current']:,.0f}",
                          f"{g['change']:+,.0f} in {g['days']} days",
                          "up" if up else "down"))
        else:
            tiles.append(("Followers", f"{g['current']:,.0f}",
                          f"tracking began {g['collection_start']:%d %b}", ""))
    if len(cur):
        now, before = R.rate(cur, "shares"), R.rate(prev, "shares")
        ch = R.pct_change(before, now)
        tiles.append(("Shares per 1k", f"{now:.1f}",
                      (f"{ch:+.0f}% vs previous {span}" if len(prev) else
                       f"this {span}"),
                      "up" if ch >= 0 else "down"))
        tiles.append(("Median reach", f"{cur['reach'].median():,.0f}",
                      f"per post, this {span}", ""))
        tiles.append(("Posts", f"{len(cur)}", f"this {span}", ""))
    if not tiles:
        return ""
    cells = "".join(
        f'<div class="kpi"><span class="kl">{esc(label)}</span>'
        f'<span class="kv">{esc(value)}</span>'
        f'<span class="kd {cls}">{esc(delta)}</span></div>'
        for label, value, delta, cls in tiles)
    return f'<div class="kpis">{cells}</div>'


def decision_card(m):
    """The one thing at the top: recommendations, switchable by period."""
    panes = []
    # Compare each period against the others first. A week can point one way
    # and the month the other, and switching tabs then reads as the page
    # contradicting itself unless we say which to trust.
    comps = {k: R.compare_periods(m, d, l, pr) for k, l, d, pr in PERIODS}
    for i, (key, label, days, prior) in enumerate(PERIODS):
        p = comps[key]
        recs = R.period_recommendations(p)
        if key == "week":
            mo = comps.get("month")
            if (p.get("enough") and mo and mo.get("enough")
                    and p.get("prev_enough") and mo.get("prev_enough")
                    and p["share_change"] * mo["share_change"] < 0
                    and abs(p["share_change"]) >= 10
                    and abs(mo["share_change"]) >= 10):
                up = mo["share_change"] > 0
                recs.append(
                    f"<i>Note the month reads the other way, "
                    f"{'up' if up else 'down'} {abs(mo['share_change']):.0f}%. "
                    f"A single week swings on one or two posts, so trust the "
                    f"month for direction and use the week to spot what just "
                    f"changed.</i>")
        active = " is-on" if i == 1 else ""          # default to Month

        span = ("this year so far" if days is None else f"the last {days} days")
        meta = (f"{p['posts']} posts in {span}"
                if p.get("enough") else "not enough posts yet")

        # "Why did this move?" — only shown when we can actually say something.
        dg = R.diagnose(m, days)
        why = ""
        if dg:
            lines = R.diagnosis_text(dg)
            weak = ""
            if dg.get("weak_posts"):
                parts = []
                for w in dg["weak_posts"]:
                    why_txt, fix_txt = R.explain_post(m, w)
                    parts.append(
                        f'<li><a href="{esc(w["permalink"])}" target="_blank" '
                        f'rel="noopener">{esc(str(w["caption"])[:80])}…</a> '
                        f'<span class="dim">{w["post_type"].replace("IG ","")} · '
                        f'{w["rate"]:.1f} per 1k</span>'
                        f'<span class="diag">{esc(why_txt)}</span>'
                        + (f'<span class="fix">{esc(fix_txt)}</span>' if fix_txt else "")
                        + "</li>")
                items = "".join(parts)
                weak = ('<p class="line"><b>Worth a look: the weakest posts '
                        f'this period:</b></p><ul class="weak">{items}</ul>')
            if lines or weak:
                why = ('<details class="why-mini"><summary>'
                       '<span class="chev">›</span> Why did this happen?</summary>'
                       + "".join(f"<p class='line'>{l}</p>" for l in lines)
                       + weak + "</details>")

        panes.append(
            f'<div class="pane{active}" id="p-{key}" role="tabpanel" '
            f'aria-labelledby="t-{key}" tabindex="0">'
            f'<p class="pane-meta">{meta}</p><ol>'
            + "".join(f"<li>{r}</li>" for r in recs) + "</ol>" + why + "</div>")
    return (
        '<section class="decision">'
        '<div class="decision-head"><h2>What changed</h2></div>'
        + '<p class="sub2 head-sub">How this period compares with the one '
          'before it, and why.</p>'
        + f'<div class="stage" data-stage="p">{"".join(panes)}</div>'
        + "</section>")


def format_section(m):
    """Per-format guidance. Headline numbers and the best post follow the period
    chosen above; best-time and caption guidance stay on the full history,
    because a single week has too few posts per format to say anything real."""
    fmt_tabs = []
    panes = []
    labels = [(f, FORMAT_LABEL.get(f, f)) for f in R.FORMATS] + [(None, "Stories")]

    for j, (fmt, label) in enumerate(labels):
        on = " is-on" if j == 0 else ""
        # One format tab governs one pane per period, so aria-controls lists
        # all three. Space separated ids are valid here.
        controls = " ".join(f"f-{pk}-{j}" for pk, _, _, _ in PERIODS)
        fmt_tabs.append(f'<button class="seg{on}" data-fmt="{j}" id="t-fmt-{j}" '
                        f'role="tab" aria-controls="{controls}" '
                        f'aria-selected="{str(j == 0).lower()}" '
                        f'tabindex="{0 if j == 0 else -1}">{label}</button>')

        for pkey, plabel, days, _prior in PERIODS:
            show = " is-on" if (j == 0 and pkey == "month") else ""
            if fmt is None:                                   # Stories pane
                sf = R.story_findings(CSV, days)
                st = ""
                if sf.get("enough"):
                    st = (f'<div class="stats">'
                          f'<div><span>{sf["completion"]:.0f}%</span>watch through</div>'
                          f'<div><span>{sf["reach_med"]:,.0f}</span>median reach</div>'
                          f'<div><span>{sf["passive"]:.0f}</span>likes &amp; stickers</div>'
                          f'<div><span>{sf["shares"]:.0f}</span>shares</div>'
                          f'<div><span>{sf["sets"]}</span>posted</div></div>')
                # A window we cannot fill gets a banner, not a footnote — the
                # numbers repeat across Month and Year and that reads as a bug
                # unless the limitation is stated up front. It clears itself:
                # `truncated` goes false once collection covers the window.
                # A window we cannot fill shows the banner and nothing else.
                # Partial numbers under a "Month" heading invite the wrong
                # conclusion, so we show no figures at all rather than figures
                # that only cover part of the period.
                if sf.get("truncated"):
                    what = "a full year" if days is None else f"a full {days} days"
                    panes.append(
                        f'<div class="pane{show}" id="f-{pkey}-{j}" role="tabpanel" '
                        f'aria-labelledby="t-fmt-{j}" tabindex="0">'
                        f'<p class="banner"><b>Instagram\u2019s API cannot give us '
                        f'this history.</b> Stories are only retrievable while they '
                        f'are still live, so anything posted before daily collection '
                        f'began on {esc(sf["since"])} is gone for good and cannot be '
                        f'recovered. There is not {what} of story data to show yet. '
                        f'The <b>Week</b> view has everything we do hold. This view '
                        f'fills in on its own by {esc(sf["complete_on"])}.</p></div>')
                    continue
                banner = ""
                span_s = "this year" if days is None else f"the last {days} days"
                # Say what the window actually covers, not just what was asked
                # for — collection began mid-year, so Month and Year overlap.
                if sf.get("truncated"):
                    span_s += f", which is all {sf['span_days']} days we hold so far"
                # Spell out frames vs stories: several frames posted back to
                # back are one story, and the raw frame count reads as if far
                # more was posted than actually was.
                detail = ""
                if sf.get("enough"):
                    detail = (f" That is {sf['sets']} "
                              f"stor{'y' if sf['sets'] == 1 else 'ies'} "
                              f"({sf['n']} frames) across {sf['days_active']} "
                              f"day{'' if sf['days_active'] == 1 else 's'}.")
                body = (banner + st
                        + f'<p class="line"><b>Collected daily</b>, since stories '
                        f'vanish after 24 hours. Showing {span_s}.{detail}</p><ul>'
                        + "".join(f"<li>{r}</li>" for r in R.story_recommendations(sf))
                        + "</ul>")
                panes.append(f'<div class="pane{show}" id="f-{pkey}-{j}" '
                             f'role="tabpanel" aria-labelledby="t-fmt-{j}" '
                             f'tabindex="0">{body}</div>')
                continue

            w = R.format_in_window(m, fmt, days)
            prof = R.format_profile(m, fmt)
            span = "this year" if days is None else f"the last {days} days"

            if not w["posts"]:
                body = (f'<p class="line">No {label.lower()} posted in {span}.</p>')
            else:
                warn = ""
                if w["concentrated"]:
                    warn = ('<p class="note">One post accounts for most of these '
                            'shares, so read this as a single result rather than '
                            'a pattern.</p>')
                elif w["thin"]:
                    warn = (f'<p class="note">Only {w["posts"]} post'
                            f'{"s" if w["posts"] != 1 else ""} in {span}, so treat '
                            f'this as directional '
                            f'at best.</p>')
                t = w["top"]
                body = (
                    f'<div class="stats">'
                    f'<div><span>{w["share_1k"]:.1f}</span>shares / 1k · {span}</div>'
                    f'<div><span>{w["reach_med"]:,.0f}</span>median reach</div>'
                    f'<div><span>{w["posts"]}</span>posts in {span}</div></div>'
                    + warn
                    + (f'<div class="best"><span class="bk">Best '
                       f'{label.lower()} of {span}</span>'
                       f'<a class="tlink" href="{esc(t["permalink"])}" '
                       f'target="_blank" rel="noopener">'
                       f'{esc(str(t["caption"])[:88])}…</a>'
                       f'<span class="bm">{t["shares"]:,.0f} shares · '
                       f'{t["reach"]:,.0f} reached</span></div>' if t else ""))

            # guidance that needs the full history
            bt = prof["best_time"] if prof else None
            when = (f'<b>{bt["day"]}'
                    + (f' around {hour_label(bt["hour"])}' if bt["hour"] is not None else "")
                    + f'</b> (median reach {bt["median_reach"]:,} across {bt["n"]} posts)'
                    ) if bt else "not enough posts to call a best time"
            caps = R.caption_recommendations(R.caption_findings(m, fmt))
            body += (f'<p class="line"><b>Post them:</b> {when}.</p>'
                     f'<p class="line"><b>Captions:</b></p><ul>'
                     + "".join(f"<li>{c}</li>" for c in caps) + "</ul>"
                     + f'<p class="allhist">Timing and caption guidance use all '
                       f'{prof["posts"]} {label.lower()}, too few in a single '
                       f'{"year" if days is None else "window"} to be reliable.</p>')
            panes.append(f'<div class="pane{show}" id="f-{pkey}-{j}" '
                         f'role="tabpanel" aria-labelledby="t-fmt-{j}" '
                         f'tabindex="0">{body}</div>')

    return ('<section class="block panel"><h2>By content type</h2>'
            '<p class="sub2">Follows the period you picked above.</p>'
            f'<div class="segs" role="tablist" aria-label="Content type">'
            f'<span class="segpill" aria-hidden="true"></span>'
            f'{"".join(fmt_tabs)}</div>'
            + f'<div class="stage" data-stage="f">{"".join(panes)}</div>'
            + "</section>")


def stories_section():
    sf = R.story_findings(CSV)
    recs = R.story_recommendations(sf)
    stats = ""
    if sf.get("enough"):
        stats = (f'<div class="stats">'
                 f'<div><span>{sf["completion"]:.0f}%</span>watch through</div>'
                 f'<div><span>{sf["reach_med"]:,.0f}</span>median reach</div>'
                 f'<div><span>{sf["n"]}</span>stories captured</div></div>')
    return ('<section class="block"><h2>Stories</h2>'
            '<p class="sub2">Collected daily, since stories disappear after 24 hours.</p>'
            + stats + "<ul>"
            + "".join(f"<li>{r}</li>" for r in recs) + "</ul></section>")


def topic_section(m):
    """What subjects to post next, ranked from the account's own history."""
    tf = TP.topic_findings(m)
    bullets = "".join(f"<li>{b}</li>" for b in TP.topic_recommendations(tf))
    table = ""
    if tf.get("enough"):
        # The subject name links to a real post, because "member spotlights"
        # means nothing until you can see one.
        cells = []
        for r in tf["rows"]:
            name = esc(r["topic"])
            eg = esc(r.get("example") or "")
            if r.get("link"):
                subject = (f'<a class="tlink" href="{esc(r["link"])}" target="_blank" '
                           f'rel="noopener">{name}'
                           + (f'<span class="eg">{eg}</span>' if eg else "")
                           + "</a>")
            else:
                subject = name
            marks = ""
            if r.get("skewed"):
                marks += ('<span class="skew" title="One post accounts for most '
                          "of this subject's shares\">*</span>")
            if r.get("thin"):
                marks += ('<span class="skew" title="Too few posts to trust the '
                          'rate">\u2020</span>')
            star = marks
            cells.append(
                f'<tr><td>{subject}</td><td class="n">{r["posts"]}</td>'
                f'<td class="n">{r["rate"]:.1f}{star}</td>'
                f'<td class="n {"up" if r["vs_avg"] > 0 else "down"}">'
                f'{r["vs_avg"]:+.0f}%</td>'
                f'<td class="n">{r["recent"]}</td></tr>')
        rows = "".join(cells)
        notes = []
        if any(r.get("skewed") for r in tf["rows"]):
            notes.append("* One post accounts for most of this subject's shares.")
        if any(r.get("thin") for r in tf["rows"]):
            notes.append("\u2020 Fewer than 8 posts, so the rate is not settled.")
        if notes:
            rows += (f'<tr><td colspan="5" class="foot">{" ".join(notes)} '
                     f'Marked subjects are shown but kept out of the advice '
                     f'above.</td></tr>')
        # Not a disclosure. Every other <details> on the page defaults closed,
        # and this one defaulting open made the same component behave two ways.
        # It is the answer to "what should we post", so it is just content.
        table = (f'<p class="sub2">Each subject links to a real example post. '
                 f'Ranked on your {esc(tf.get("scope", ""))} posts.</p>'
                 '<div class="tw"><table class="topics">'
                 '<thead><tr><th>Subject</th><th class="n">Posts</th>'
                 '<th class="n">Shares / 1k</th><th class="n">vs avg</th>'
                 '<th class="n">Last 30d</th></tr></thead>'
                 f'<tbody>{rows}</tbody></table></div>')
    return ('<section class="block panel"><h2>What to post next</h2>'
            '<p class="sub2">Ranked by what your own audience shares, since '
            'Instagram publishes nothing about what is trending.</p>'
            f'<ul class="csays">{bullets}</ul>{table}</section>')


def growth_chart(g, w=600, h=130, pad=10):
    """A plain line chart of follower counts. Inline SVG so it needs no
    library and no network request, and scales with the column."""
    pts = g["points"]
    ys = [v for _, v in pts]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1
    n = len(pts) - 1

    def xy(i, v):
        return (pad + i / n * (w - 2 * pad),
                h - pad - (v - lo) / span * (h - 2 * pad))

    coords = [xy(i, v) for i, (_, v) in enumerate(pts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = (f"M{coords[0][0]:.1f},{h - pad:.1f} L" + line
            + f" L{coords[-1][0]:.1f},{h - pad:.1f} Z")
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3"/>' for x, y in coords)
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Followers from {g["since"]:%d %b} to {g["until"]:%d %b}, '
        f'{g["points"][0][1]:,.0f} rising to {g["current"]:,.0f}">'
        f'<path class="ga" d="{area}"/>'
        f'<polyline class="gl" points="{line}"/>'
        f'<g class="gd">{dots}</g></svg>'
        f'<div class="gax"><span>{g["since"]:%d %b}</span>'
        f'<span>{g["until"]:%d %b}</span></div>')


def _growth_pane(i, key, days):
    """Follower movement for one period. Same control, same state."""
    g = AU.follower_growth(CSV, days)
    on = " is-on" if i == 1 else ""
    if not g.get("enough"):
        body = ('<p class="line">Not enough follower readings in this period '
                'yet.</p>')
    elif not g.get("reportable"):
        # Showing the numbers here would repeat the shorter window's figures
        # under a longer label, which reads as a bug rather than as a limit.
        what = "a full year" if days is None else f"a full {days} days"
        body = (f'<p class="banner"><b>Not enough history for this view yet.</b> '
                f'Daily follower tracking began '
                f'{g["collection_start"]:%d %b %Y}, so this holds '
                f'{g["days"]} days rather than {what}. Showing it would just '
                f'repeat the shorter period. Use <b>Month</b> until more '
                f'accumulates.</p>')
    else:
        up = g["change"] >= 0
        body = (
            '<div class="growth">'
            f'<div class="gchart">{growth_chart(g)}</div>'
            '<div class="gnums">'
            f'<div><span>{g["current"]:,.0f}</span>followers now</div>'
            f'<div><span class="{"up" if up else "down"}">{g["change"]:+,.0f}</span>'
            f'in {g["days"]} days</div>'
            f'<div><span>{g["per_week"]:+,.0f}</span>a week</div>'
            '</div></div>'
            + '<ul class="csays">'
            + "".join(f"<li>{n}</li>" for n in AU.growth_note(g)) + "</ul>")
    return (f'<div class="pane{on}" id="g-{key}" role="tabpanel" '
            f'aria-labelledby="t-{key}">{body}</div>')


def audience_section(part):
    """Who follows the account. The only part of the page not about posts.

    Returns one panel at a time so the dashboard grid can pair each with a
    section of matching height instead of leaving a column empty.
    """
    af = AU.audience_findings(CSV)
    if not af.get("enough"):
        return ""
    bars = ""
    age = af["parts"].get("age")
    if age:
        # A bar per age bracket: the shape of this is the finding, and a table
        # of percentages does not show a shape.
        top = max(p for _, _, p in age["segments"])
        rows = "".join(
            f'<div class="bar"><span class="bl">{esc(seg)}</span>'
            f'<span class="bt"><i style="width:{pct / top * 100:.1f}%"></i></span>'
            f'<span class="bv">{pct:.0f}%</span></div>'
            for seg, _, pct in sorted(age["segments"],
                                      key=lambda x: x[0]))
        bars = f'<div class="bars">{rows}</div>'
    growth = ('<div class="stage" data-stage="g">'
              + "".join(_growth_pane(i, k, d)
                        for i, (k, _l, d, _p) in enumerate(PERIODS))
              + '</div>')

    if part == "growth":
        return ('<section class="block panel"><h2>Followers</h2>'
                '<p class="sub2">How the audience is growing. Refreshed '
                'daily.</p>' + growth + '</section>')
    return ('<section class="block panel"><h2>Who they are</h2>'
            '<p class="sub2">Instagram reports this for followers only.</p>'
            + bars
            + '<ul class="csays">'
            + "".join(f"<li>{b}</li>" for b in AU.audience_recommendations(af))
            + "</ul></section>")


def charts_section(m):
    items = []
    for title, sheet in CHARTS:
        src = (f"https://public.tableau.com/views/{TABLEAU_WORKBOOK}/{sheet}"
               f"?:embed=y&:showVizHome=no&:toolbar=no&:tabs=no&:display_count=no")
        # A chart without a reading is just decoration. Both lines are computed
        # from the CSVs at build time, so they follow the data rather than
        # describing what it looked like the day they were written.
        note = CN.note_for(title, m)
        blurb = ""
        if note:
            what, bullets = note
            blurb = (f'<p class="cwhat">{what}</p><ul class="csays">'
                     + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>")
        # Height reserved up front so nothing below moves, and a titled card
        # underneath that doubles as a fallback if Tableau never paints.
        items.append(
            f'<h3>{esc(title)}</h3>{blurb}'
            f'<div class="viz" data-src="{src}" data-title="{esc(title)}">'
            f'<div class="viz-fb"><span class="vt">{esc(title)}</span>'
            f'<span class="vs">Loading the chart…</span>'
            f'<a href="{TABLEAU_HOME}" target="_blank" rel="noopener">'
            f'Open in Tableau</a></div></div>')
    return ('<section class="block"><details class="why">'
            '<summary><span class="chev">›</span> See the data behind these '
            'recommendations <em>(9 charts)</em></summary>'
            '<p class="sub2">These are the live Tableau views. They refresh on their '
            'own as new data arrives.</p>'
            + "".join(items) +
            f'<a class="explore" href="{TABLEAU_HOME}" target="_blank" rel="noopener">'
            f'Open in Tableau →</a></details></section>')


CSS = """
/* Follows the system theme. The Tableau embeds do render white, but that only
   matters inside the charts disclosure, which is closed by default and is one
   section of seven. Keeping the other six light to protect a section most
   visits never open is the wrong trade, so each embed gets a light well
   instead: a pale container with its own border and a deeper shadow, which is
   what a light surface inside a dark page is supposed to look like.

   Three decisions hold this sheet together:
     1. Five type sizes, assigned by role. Not by feel.
     2. Three surfaces, one per meaning: the answer, supporting detail, a
        caveat. Colour stopped carrying hierarchy once elevation did.
     3. Elevation is spent exactly once, on the primary card. */
:root{
  color-scheme:light dark;
  --bg:#fff;--fg:#15181e;--muted:#5d6675;--card:#f7f8fa;
  --line:#e5e8ef;--accent:#3d6bf5;--soft:#eef2fe;--soft-line:#d6e0fc;
  --good:#12855f;--bad:#a4472e;
  --warn-bg:#fff4e0;--warn-line:#efd3a3;--warn-bar:#d98c1f;--warn-fg:#6b4a12;

  --fs-micro:12px;   /* chips, table headers, footnotes, eyebrows */
  --fs-small:14px;   /* captions, notes, secondary lines          */
  --fs-body:16px;    /* everything you actually read              */
  --fs-lead:21px;    /* section headings, stat numbers            */
  --fs-title:36px;   /* the h1                                    */

  --track-title:-.022em; --lead-title:1.08;   /* 36px */
  --track-lead:-.012em;  --lead-lead:1.24;    /* 21px */
  --track-body:0em;      --lead-body:1.6;     /* 16px */
  --track-micro:.005em;                       /* 12-14px */
  --track-caps:.055em;                        /* 12px UPPERCASE */

  --r-sm:8px;        /* chips, notes, tables, media               */
  --r-lg:14px;       /* the primary card                          */

  --shadow:0 1px 2px rgba(17,21,28,.05), 0 8px 24px -12px rgba(17,21,28,.18);
  --chrome-bg:rgba(252,253,255,.72);
  --chrome-line:#e2e7f0;
  --well:#fff;--well-line:#e5e8ef;
  --on-accent:#fff;          /* text sitting on the accent fill */
}
/* One block, because the palette is fully tokenised. Nothing below this
   references a literal colour. */
@media (prefers-color-scheme:dark){
  :root{
    --bg:#12151a;--fg:#e7ebf2;--muted:#98a3b5;--card:#191d24;
    --line:#2a303a;--accent:#6f92ff;--soft:#1b2233;--soft-line:#2f3a52;
    --good:#3fbe8f;--bad:#e2795c;
    --warn-bg:#2a2116;--warn-line:#4a3b23;--warn-bar:#c68a34;--warn-fg:#f0d9b4;
    --chrome-bg:rgba(18,21,26,.72);
    --chrome-line:#2a303a;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 16px 40px -24px rgba(0,0,0,.85);
    /* The well the Tableau embeds sit in. */
    --well:#f7f8fa;--well-line:#3a4250;
    /* The dark accent is light, so white on it would not carry. */
    --on-accent:#0f1626;
  }
  .banner b{filter:none}
  .chrome{box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
  .spark .gd circle{fill:var(--card)}
  tr.crow.me td{background:var(--soft)}
  /* A light island: pale fill, its own edge, and a heavier shadow because a
     bigger surface should read as thicker. */
  .viz{background:var(--well);border-color:var(--well-line);
       box-shadow:0 2px 4px rgba(0,0,0,.35),0 20px 44px -26px rgba(0,0,0,.9)}
  .viz-fb{background:var(--well);color:#15181e}
  .viz-fb .vs{color:#5d6675}
}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
font:var(--fs-body)/var(--lead-body) system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:clamp(28px,5vw,52px) clamp(16px,4vw,24px) 80px}

h1{font-size:clamp(29px,4.4vw,var(--fs-title));line-height:var(--lead-title);
margin:0 0 6px;letter-spacing:var(--track-title);font-optical-sizing:auto;
text-wrap:balance}
h2{font-size:var(--fs-lead);margin:0;letter-spacing:-.01em;line-height:1.25}
h3{font-size:var(--fs-small);margin:26px 0 8px;color:var(--muted);font-weight:600}
.sub{color:var(--muted);margin:0 0 30px;font-size:var(--fs-small)}
.sub2{color:var(--muted);margin:6px 0 14px;font-size:var(--fs-small)}

/* ── the one page-level control ─────────────────────────────────────────── */
.chrome{position:sticky;top:0;z-index:40;margin:0 0 18px;
background:var(--chrome-bg);
-webkit-backdrop-filter:blur(22px) saturate(180%);
backdrop-filter:blur(22px) saturate(180%);
border-bottom:1px solid var(--chrome-line);
box-shadow:inset 0 1px 0 rgba(255,255,255,.65);
transition:box-shadow .2s ease,border-color .2s ease}
/* Scroll edge effect: no rule until content is actually passing underneath. */
.chrome:not(.is-stuck){border-bottom-color:transparent;box-shadow:none}
.chrome-sentinel{height:1px;margin-bottom:-1px}
.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;
padding:12px 0}
@media (prefers-reduced-transparency:reduce){
  .chrome{background:var(--bg);-webkit-backdrop-filter:none;backdrop-filter:none}
}
@media (prefers-contrast:more){
  :root{--line:#8b93a3;--chrome-line:#8b93a3}
  .chrome{background:var(--bg);backdrop-filter:none}
}
.tlabel{font-size:var(--fs-micro);font-weight:600;color:var(--muted);
text-transform:uppercase;letter-spacing:.02em}
.thint{font-size:var(--fs-micro);color:var(--muted)}

/* ── dashboard layout ───────────────────────────────────────────────────── */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
gap:12px;margin:0 0 22px}
.kpis-3{grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin:14px 0 16px}
.kpi{background:var(--bg);border:1px solid var(--line);border-radius:var(--r-lg);
padding:16px 18px;display:flex;flex-direction:column;gap:2px}
.kl{font-size:var(--fs-micro);color:var(--muted);font-weight:600;
letter-spacing:var(--track-caps);text-transform:uppercase}
.kv{font-size:var(--fs-title);font-weight:700;letter-spacing:-.03em;line-height:1.05;
font-variant-numeric:tabular-nums}
/* Must follow .kv: equal specificity, so source order decides. Declared
   before it, this lost, and 21px kept 36px's tracking and leading. */
.kvs{font-size:var(--fs-lead);letter-spacing:var(--track-lead);
line-height:var(--lead-lead)}
.kd{font-size:var(--fs-micro);color:var(--muted)}
.kd.up{color:var(--good);font-weight:600}
.kd.down{color:var(--bad);font-weight:600}

/* Two columns on a real screen, stacked on a phone. The point of a dashboard
   is seeing more than one thing at once. */
.grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);
gap:20px;align-items:stretch;margin:0 0 22px}
.grid > *{margin:0}
.panel{background:var(--bg);border:1px solid var(--line);border-radius:var(--r-lg);
padding:clamp(18px,2.5vw,24px)}

/* ── surface 1: the answer. The only raised thing on the page. ───────────── */
.decision{background:var(--bg);border:1px solid var(--line);border-radius:var(--r-lg);
box-shadow:var(--shadow);padding:clamp(20px,3.5vw,28px);margin:0 0 22px}
.decision-head{display:flex;flex-wrap:wrap;gap:12px;align-items:center;
justify-content:space-between;margin-bottom:16px}
.decision ol{margin:0;padding-left:20px}
.decision li{margin:0 0 12px}.decision li:last-child{margin:0}
.pane-meta{color:var(--muted);font-size:var(--fs-micro);margin:0 0 12px}

/* ── surface 2: supporting detail. Flat, recessive, one look. ────────────── */
.surface{background:var(--card);border:1px solid var(--line);
border-radius:var(--r-sm)}
.csays{background:var(--card);border:1px solid var(--line);
border-radius:var(--r-sm);padding:12px 14px 12px 30px;margin:0 0 12px;
font-size:var(--fs-small);line-height:1.55}
.csays li{margin:0 0 6px}
.csays li:last-child{margin:0}
.cwhat{color:var(--muted);font-size:var(--fs-small);margin:0 0 6px;line-height:1.55}

/* ── surface 3: a caveat. Amber, and it means one thing. ─────────────────── */
.banner,.note{background:var(--warn-bg);border:1px solid var(--warn-line);
border-left:4px solid var(--warn-bar);border-radius:var(--r-sm);
color:var(--warn-fg);font-size:var(--fs-small);line-height:1.55}
.banner{padding:12px 14px;margin:0 0 16px}
.note{padding:10px 12px;margin:10px 0}
.banner b{color:var(--warn-fg);filter:brightness(.82)}

/* ── controls ───────────────────────────────────────────────────────────── */
.segs{position:relative;display:inline-flex;background:var(--card);
border:1px solid var(--line);border-radius:var(--r-sm);padding:3px;gap:2px;
touch-action:pan-y;user-select:none;-webkit-user-select:none}
.segpill{position:absolute;top:3px;left:0;height:calc(100% - 6px);
border-radius:calc(var(--r-sm) - 2px);background:var(--accent);
pointer-events:none;opacity:0;will-change:transform,width}
.segs.ready .segpill{opacity:1}
.segs.dragging{cursor:grabbing}
/* The pill is absolutely positioned, so it paints above static siblings
   whatever the source order. The labels have to be lifted over it. */
.seg{position:relative;z-index:1;
border:0;background:none;font:inherit;font-size:var(--fs-small);font-weight:600;
color:var(--muted);padding:11px 14px;min-height:44px;
border-radius:calc(var(--r-sm) - 2px);cursor:pointer;
transition:background .15s ease,color .15s ease,transform .1s ease}
.seg:hover{color:var(--fg)}
.seg:active{transform:scale(.97)}
.seg:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);
outline-offset:3px;border-radius:4px}
/* The pill is the selection now, so the button only changes colour. */
.seg.is-on{color:var(--on-accent)}

/* A stage owns its height so the column below it does not jolt on a switch. */
.stage{position:relative}
.stage.is-moving{overflow:hidden;will-change:height}
.pane{display:none}
.pane.is-on{display:block}
.stage.is-moving .pane.is-out{display:block;position:absolute;inset:0 0 auto 0;
pointer-events:none}
.pane:focus{outline:none}

.block{margin:0 0 34px}
.line{margin:0 0 10px}
.block ul{margin:4px 0 14px;padding-left:20px}
.block li{margin:0 0 8px}
.dim{color:var(--muted);font-size:var(--fs-micro)}
.allhist{color:var(--muted);font-size:var(--fs-micro);margin:10px 0 0;font-style:italic}

/* ── disclosures. One component, one default: closed. ────────────────────── */
.why-mini{margin:14px 0 0;border-top:1px solid var(--line);padding-top:10px}
.why-mini summary{cursor:pointer;list-style:none;font-weight:600;
font-size:var(--fs-small);color:var(--accent);display:flex;align-items:center;
gap:6px;padding:8px 0;min-height:44px}
.why-mini summary::-webkit-details-marker{display:none}

.why-mini .line{font-size:var(--fs-small);margin:8px 0}
.why{border:1px solid var(--line);border-radius:var(--r-sm);background:var(--card);
padding:0 18px}
.why summary{cursor:pointer;padding:16px 0;font-weight:600;list-style:none;
display:flex;align-items:center;gap:8px;min-height:44px}
.why summary::-webkit-details-marker{display:none}
.why summary em{color:var(--muted);font-style:normal;font-weight:400;
font-size:var(--fs-small)}

.chev{display:inline-block;color:var(--accent);font-size:var(--fs-lead);line-height:1;
transition:transform .28s cubic-bezier(.32,.72,0,1)}
.d-body{overflow:hidden}
details.is-open > summary .chev{transform:rotate(90deg)}

/* ── weak-post diagnostics ──────────────────────────────────────────────── */
ul.weak{margin:6px 0 4px;padding-left:20px;font-size:var(--fs-small)}
ul.weak li{margin:0 0 14px}
.diag,.fix{display:block;font-size:var(--fs-small);margin-top:4px;line-height:1.5}
.diag{color:var(--muted)}
.fix{color:var(--good);font-weight:500}

/* ── stat tiles. The first figure is the argument; the rest are context. ─── */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;
margin:14px 0 18px}
.stats div{background:var(--bg);border:1px solid var(--line);
border-radius:var(--r-lg);padding:16px 18px;font-size:var(--fs-micro);
color:var(--muted);line-height:1.35}
.stats span{display:block;font-size:var(--fs-lead);font-weight:700;color:var(--fg);
letter-spacing:-.02em;margin-bottom:2px;font-variant-numeric:tabular-nums}

/* The best performing post, styled like a subject row rather than a sentence
   with a long link wrapping through it. */
.best{background:var(--card);border:1px solid var(--line);border-radius:var(--r-sm);
padding:12px 14px;margin:0 0 14px}
.bk{display:block;font-size:var(--fs-micro);font-weight:600;color:var(--muted);
text-transform:uppercase;letter-spacing:var(--track-caps);margin-bottom:4px}
.best .tlink{font-size:var(--fs-small)}
.bm{display:block;font-size:var(--fs-micro);color:var(--muted);margin-top:4px;
font-variant-numeric:tabular-nums}

/* ── the subject table ──────────────────────────────────────────────────── */
.tw{overflow-x:auto;
-webkit-mask-image:linear-gradient(to right,#000 calc(100% - 48px),transparent);
mask-image:linear-gradient(to right,#000 calc(100% - 48px),transparent)}
.tw.at-end,.tw.no-overflow{-webkit-mask-image:none;mask-image:none}
table.topics{border-collapse:collapse;width:100%;font-size:var(--fs-small);margin:6px 0 0}
table.topics th{text-align:left;font-weight:600;color:var(--muted);
font-size:var(--fs-micro);padding:6px 10px 6px 0;border-bottom:1px solid var(--line);
line-height:1.25;white-space:nowrap}
/* Matches the specificity of the rule above; `th.n` alone lost to it and the
   headers sat left over right-aligned numbers. */
table.topics th.n{text-align:right}
table.topics td{padding:8px 10px 8px 0;border-bottom:1px solid var(--line)}
table.topics td:first-child{font-weight:500;min-width:190px}
table.compact td{padding:5px 10px 5px 0;font-size:var(--fs-micro)}
table.compact td:first-child{min-width:0}
table.compact .tlink{font-size:var(--fs-small)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;padding-right:0}
table.topics .skew{color:var(--muted);font-weight:400}
table.topics td.foot{color:var(--muted);font-size:var(--fs-micro);line-height:1.45;
padding-top:9px;border-bottom:0;text-align:left}
table.topics .up{color:var(--good);font-weight:600}
table.topics .down{color:var(--bad);font-weight:600}
a.tlink{color:var(--accent);text-decoration:none;display:block}
a.tlink:hover{text-decoration:underline}
tr.crow.me td{background:var(--soft)}
tr.crow.me td:first-child{border-radius:var(--r-sm) 0 0 var(--r-sm)}
tr.crow.me td:last-child{border-radius:0 var(--r-sm) var(--r-sm) 0}
a.tlink .eg{display:block;color:var(--muted);font-weight:400;
font-size:var(--fs-micro);line-height:1.35;margin-top:2px;text-decoration:none}

/* ── follower growth ────────────────────────────────────────────────────── */
.growth{display:grid;grid-template-columns:1fr 150px;gap:20px;align-items:center;
margin:14px 0 16px}
.gchart{min-width:0}
.spark{width:100%;height:auto;display:block;overflow:visible}
.spark .ga{fill:var(--accent);opacity:.10}
.spark .gl{fill:none;stroke:var(--accent);stroke-width:2.5;
stroke-linejoin:round;stroke-linecap:round}
.spark .gd circle{fill:var(--bg);stroke:var(--accent);stroke-width:2}
.gax{display:flex;justify-content:space-between;color:var(--muted);
font-size:var(--fs-micro);margin-top:4px}
.gnums div{margin:0 0 12px;font-size:var(--fs-micro);color:var(--muted);
line-height:1.3}
.gnums div:last-child{margin:0}
.gnums span{display:block;font-size:var(--fs-lead);font-weight:700;color:var(--fg);
letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.gnums .up{color:var(--good)}.gnums .down{color:var(--bad)}
/* The negative margin closes a gap under the heading row. Under a tab row
   there is no gap to close, and it pulled the text into the buttons. */
.head-sub{margin:0 0 14px}
.decision-head + .head-sub{margin-top:-8px}
.segs + .head-sub{margin-top:12px}

/* ── audience bars ──────────────────────────────────────────────────────── */
.bars{margin:14px 0 16px}
.bar{display:grid;grid-template-columns:minmax(56px,auto) 1fr 52px;align-items:center;gap:10px;
margin:0 0 6px;font-size:var(--fs-micro);color:var(--muted)}
.bl{font-variant-numeric:tabular-nums}
.bt{background:var(--card);border:1px solid var(--line);border-radius:var(--r-sm);
height:14px;overflow:hidden}
.bt i{display:block;height:100%;background:var(--accent);opacity:.85}
.bar.me .bl,.bar.me .bv{color:var(--fg);font-weight:700}
.bar.me .bt i{opacity:1}
.bar.me .bt{border-color:var(--soft-line)}
.bv{text-align:right;font-variant-numeric:tabular-nums;color:var(--fg);font-weight:600}

/* ── charts ─────────────────────────────────────────────────────────────── */
.viz{position:relative;height:520px;overflow:hidden;border:1px solid var(--line);
border-radius:var(--r-sm);background:var(--bg);margin-bottom:6px}
.viz iframe{position:absolute;inset:0;width:100%;height:100%;border:0;
opacity:0;transition:opacity .3s ease}
.viz.is-live iframe{opacity:1}
.viz.is-live .viz-fb{opacity:0;pointer-events:none}
.viz-fb{position:absolute;inset:0;display:flex;flex-direction:column;
align-items:center;justify-content:center;gap:8px;text-align:center;
padding:20px;transition:opacity .3s ease;background:var(--card)}
.vt{font-weight:600;font-size:var(--fs-small)}
.vs{font-size:var(--fs-micro);color:var(--muted)}
.viz.is-dead .vs{color:var(--bad)}
.explore{display:inline-block;margin:18px 0 22px;padding:13px 20px;
border-radius:var(--r-sm);background:var(--accent);color:var(--on-accent);text-decoration:none;
font-size:var(--fs-small);font-weight:600;min-height:44px;
transition:filter .15s ease,transform .1s ease}
.explore:hover{filter:brightness(1.07)}.explore:active{transform:scale(.97)}
.explore:focus-visible{outline:2px solid var(--accent);outline-offset:3px}

a{color:var(--accent)}
footer{margin-top:56px;padding-top:22px;border-top:1px solid var(--line);
color:var(--muted);font-size:var(--fs-small)}
footer p{margin:0}
.sig{font-size:var(--fs-body);color:var(--fg);letter-spacing:var(--track-body)}
.sig b{font-weight:600}
.fmeta{margin-top:6px!important;font-size:var(--fs-small)}
.build{margin-top:10px!important;font-size:var(--fs-micro);opacity:.7;
font-variant-numeric:tabular-nums}
/* Reduced motion means no vestibular motion: travel, parallax, large
   surfaces sliding. Colour and opacity feedback are comprehension aids and
   should survive. The springs read the query at runtime. */
@media (prefers-reduced-motion:reduce){
  *{transition-property:opacity,color,background-color,border-color!important;
    transition-duration:.12s!important}
  .chev{transition:none!important}
}
@media (max-width:900px){
  .grid{grid-template-columns:1fr}
}
@media (max-width:520px){
  .decision-head{flex-direction:column;align-items:flex-start}
  .kpis{grid-template-columns:repeat(2,1fr);gap:10px}
  .kpi{padding:13px 14px}
  .kv{font-size:var(--fs-lead)}
  .growth{grid-template-columns:1fr;gap:14px}
  .gnums{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
  .gnums div{margin:0}
}

/* Dark component overrides live at the end on purpose. They target the same
   single-class selectors as the light rules above, so source order decides
   which wins; declared earlier they silently lost. */
@media (prefers-color-scheme:dark){
  .banner b{filter:none}
  .chrome{box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
  .spark .gd circle{fill:var(--card)}
  /* A light island for each embed: pale fill, its own edge, and a heavier
     shadow, because a bigger surface should read as thicker. */
  .viz{background:var(--well);border-color:var(--well-line);
  box-shadow:0 2px 4px rgba(0,0,0,.35),0 20px 44px -26px rgba(0,0,0,.9)}
  .viz-fb{background:var(--well);color:#15181e}
  .viz-fb .vs{color:#5d6675}
}
"""

JS = """
// One period drives the whole page: the KPI strip, the recommendations, the
// follower panel and the content-type panes. Content type is chosen
// independently, so the visible pane is (period, content type).
//
// Everything below is one spring engine and three things built on it: a
// selection pill that travels, stages that animate their own height so the
// page does not jolt, and disclosures that open at the same speed their
// chevron turns. No dependencies.
(function () {
  'use strict';

  // ── reduced motion, read live ─────────────────────────────────────────
  // Someone can change this with the page open, and CSS transitions are not
  // what is moving any more, so the query has to be listened to rather than
  // read once at load.
  var rmq = matchMedia('(prefers-reduced-motion: reduce)');
  var reduced = rmq.matches;
  if (rmq.addEventListener) rmq.addEventListener('change', function (e) {
    reduced = e.matches;
  });

  // ── spring ────────────────────────────────────────────────────────────
  // Critically damped: damping 1.0, so nothing overshoots. Bounce is earned
  // by momentum, and a pane that merely changed has not earned it.
  var pool = [], raf = null, last = 0;
  function frame(now) {
    var dt = Math.min((now - last) / 1000, 1 / 15); last = now;
    for (var i = 0; i < pool.length; i++) pool[i].step(dt);
    pool = pool.filter(function (s) { return !s.done; });
    raf = pool.length ? requestAnimationFrame(frame) : null;
  }
  function Spring(v, response, onPaint) {
    this.value = v; this.target = v; this.velocity = 0; this.done = true;
    this.response = response || 0.36; this.onPaint = onPaint || null;
  }
  Spring.prototype.step = function (dt) {
    var w = 2 * Math.PI / this.response,
        n = Math.max(1, Math.ceil(dt * 240)), h = dt / n;
    for (var i = 0; i < n; i++) {
      this.velocity += (-w * w * (this.value - this.target)
                        - 2 * w * this.velocity) * h;
      this.value += this.velocity * h;
    }
    if (Math.abs(this.value - this.target) < 0.12 &&
        Math.abs(this.velocity) < 0.5) {
      this.value = this.target; this.velocity = 0; this.done = true;
    }
    if (this.onPaint) this.onPaint(this);
  };
  Spring.prototype.set = function (t, vel) {
    this.target = t;
    if (vel != null) this.velocity = vel;
    // requestAnimationFrame is paused in a background tab, which would leave a
    // spring stalled mid-flight and a disclosure open at zero height. Nobody
    // is watching an animation they cannot see, so settle it immediately.
    if (reduced || document.hidden) {
      this.value = t; this.velocity = 0; this.done = true;
      if (this.onPaint) this.onPaint(this);
      return;
    }
    this.done = false;
    if (pool.indexOf(this) < 0) pool.push(this);
    if (raf === null) { last = performance.now(); raf = requestAnimationFrame(frame); }
  };
  Spring.prototype.jump = function (v) {
    this.value = v; this.target = v; this.velocity = 0; this.done = true;
    if (this.onPaint) this.onPaint(this);
  };

  function project(v) { return (v / 1000) * 0.998 / (1 - 0.998); }
  function rubber(o, d) { return (o * d * 0.55) / (d + 0.55 * Math.abs(o)); }

  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) return;
    for (var i = pool.length - 1; i >= 0; i--) {
      var sp = pool[i];
      sp.value = sp.target; sp.velocity = 0; sp.done = true;
      if (sp.onPaint) sp.onPaint(sp);
    }
    pool = [];
  });

  var state = { period: 'month', fmt: '0' };

  // ── stages: animate height so the column below does not jolt ──────────
  function Stage(el) {
    var self = this;
    this.el = el;
    this.h = new Spring(0, 0.42, function (sp) {
      self.el.style.height = sp.value + 'px';
      if (sp.done) {
        self.el.style.height = '';
        self.el.classList.remove('is-moving');
        var out = self.el.querySelector('.pane.is-out');
        if (out) out.classList.remove('is-out');
      }
    });
  }
  Stage.prototype.to = function (id, dir) {
    var next = this.el.querySelector('#' + CSS.escape(id));
    var cur = this.el.querySelector('.pane.is-on');
    if (!next || next === cur) return;
    // The presentation value, not the logical one. Starting from what is
    // actually on screen is what lets a fast reversal redirect rather than
    // hit a brick wall.
    var from = this.el.getBoundingClientRect().height;
    this.el.classList.add('is-moving');
    this.el.style.height = from + 'px';
    if (cur) cur.classList.replace('is-on', 'is-out');
    next.classList.add('is-on');
    var to = next.getBoundingClientRect().height;
    if (cur) slide(cur, 0, -dir * 14);
    slide(next, 1, dir * 14, true);
    // Deliberately not resetting velocity mid-flight.
    if (this.h.done) { this.h.value = from; this.h.velocity = 0; }
    this.h.set(to);
  };
  function slide(el, opacity, dx, incoming) {
    if (reduced) { el.style.opacity = ''; el.style.transform = ''; return; }
    if (incoming) {
      el.style.transition = 'none';
      el.style.opacity = '0';
      el.style.transform = 'translate3d(' + dx + 'px,0,0)';
      el.getBoundingClientRect();
      el.style.transition = 'opacity .22s ease, transform .26s ease';
      el.style.opacity = '1';
      el.style.transform = 'translate3d(0,0,0)';
    } else {
      el.style.transition = 'opacity .18s ease, transform .26s ease';
      el.style.opacity = '0';
      el.style.transform = 'translate3d(' + dx + 'px,0,0)';
    }
  }

  var stages = [].slice.call(document.querySelectorAll('.stage')).map(function (el) {
    var st = new Stage(el);
    st.key = el.getAttribute('data-stage');
    return st;
  });
  var ORDER = ['week', 'month', 'year'];

  function apply(dir) {
    stages.forEach(function (st) {
      var id = st.key === 'f' ? 'f-' + state.period + '-' + state.fmt
                              : st.key + '-' + state.period;
      st.to(id, dir);
    });
  }

  // ── the pill: one object that travels, and that you can grab ──────────
  function Pill(root) {
    var self = this;
    this.root = root;
    this.pill = root.querySelector('.segpill');
    this.segs = [].slice.call(root.querySelectorAll('.seg'));
    if (!this.pill || !this.segs.length) return;
    this.idx = Math.max(0, this.segs.findIndex(function (b) {
      return b.classList.contains('is-on');
    }));
    var paint = function () { self.paint(); };
    // Two springs. A single spring over position and width desynchronises
    // the moment the two axes carry different velocities.
    this.sx = new Spring(0, 0.36, paint);
    this.sw = new Spring(0, 0.36, paint);
    this.measure();
    this.wire();
  }
  Pill.prototype.paint = function () {
    this.pill.style.transform = 'translate3d(' + this.sx.value + 'px,0,0)';
    this.pill.style.width = this.sw.value + 'px';
    var c = this.sx.value + this.sw.value / 2;
    for (var i = 0; i < this.segs.length; i++) {
      this.segs[i].classList.toggle('is-on',
        c >= this.segs[i].offsetLeft &&
        c < this.segs[i].offsetLeft + this.segs[i].offsetWidth);
    }
  };
  Pill.prototype.measure = function () {
    var s = this.segs[this.idx];
    if (!s || !s.offsetWidth) return;
    this.sx.jump(s.offsetLeft); this.sw.jump(s.offsetWidth);
    this.root.classList.add('ready');
  };
  Pill.prototype.nearest = function (c) {
    var b = 0, bd = Infinity;
    for (var i = 0; i < this.segs.length; i++) {
      var d = Math.abs(this.segs[i].offsetLeft
                       + this.segs[i].offsetWidth / 2 - c);
      if (d < bd) { bd = d; b = i; }
    }
    return b;
  };
  Pill.prototype.goTo = function (i, vel, focus) {
    i = Math.max(0, Math.min(this.segs.length - 1, i));
    var dir = i > this.idx ? 1 : i < this.idx ? -1 : 0;
    this.idx = i;
    for (var j = 0; j < this.segs.length; j++) {
      this.segs[j].setAttribute('aria-selected', j === i ? 'true' : 'false');
      this.segs[j].tabIndex = j === i ? 0 : -1;
    }
    this.sw.set(this.segs[i].offsetWidth);
    this.sx.set(this.segs[i].offsetLeft, vel);
    var btn = this.segs[i];
    if (btn.dataset.period) state.period = btn.dataset.period;
    if (btn.dataset.fmt) state.fmt = btn.dataset.fmt;
    if (focus) btn.focus();
    apply(dir || 1);
  };
  Pill.prototype.wire = function () {
    var self = this, drag = null;
    this.root.addEventListener('pointerdown', function (e) {
      if (e.button) return;
      var px = e.clientX - self.root.getBoundingClientRect().left;
      var seg = e.target.closest ? e.target.closest('.seg') : null;
      var hit = seg ? self.segs.indexOf(seg) : -1;
      var onPill = px >= self.sx.value && px <= self.sx.value + self.sw.value;
      if (!onPill && hit >= 0 && hit !== self.idx) self.goTo(hit);
      // A pointer press has handled this; the click that follows must not
      // handle it a second time.
      self.viaPointer = true;
      setTimeout(function () { self.viaPointer = false; }, 400);
      try { self.root.setPointerCapture(e.pointerId); } catch (err) {}
      drag = { id: e.pointerId, startX: px, grab: 0, moved: false,
               hist: [{ x: px, t: performance.now() }] };
    });
    this.root.addEventListener('pointermove', function (e) {
      if (!drag || e.pointerId !== drag.id) return;
      var px = e.clientX - self.root.getBoundingClientRect().left;
      drag.hist.push({ x: px, t: performance.now() });
      if (drag.hist.length > 6) drag.hist.shift();
      if (!drag.moved) {
        if (Math.abs(px - drag.startX) < 10) return;   // hysteresis: a sloppy tap stays a tap
        drag.moved = true;
        drag.grab = px - self.sx.value;
        self.root.classList.add('dragging');
      }
      var lo = self.segs[0].offsetLeft, lastSeg = self.segs[self.segs.length - 1];
      var hi = lastSeg.offsetLeft + lastSeg.offsetWidth - self.sw.value;
      var want = px - drag.grab;
      if (want < lo) want = lo - rubber(lo - want, self.root.offsetWidth);
      else if (want > hi) want = hi + rubber(want - hi, self.root.offsetWidth);
      self.sx.jump(want);
      self.sw.set(self.segs[self.nearest(self.sx.value + self.sw.value / 2)].offsetWidth);
    });
    function release(e) {
      if (!drag || e.pointerId !== drag.id) return;
      var moved = drag.moved, h = drag.hist;
      self.root.classList.remove('dragging'); drag = null;
      if (!moved) return;
      var v = 0, a = h[0], b = h[h.length - 1], dt = (b.t - a.t) / 1000;
      if (dt > 0.004) v = (b.x - a.x) / dt;
      // Land where the gesture was heading, not where it stopped.
      self.goTo(self.nearest(self.sx.value + self.sw.value / 2 + project(v)), v);
    }
    this.root.addEventListener('pointerup', release);
    this.root.addEventListener('pointercancel', release);
    // Enter and Space on a focused tab fire click, not pointerdown, and so do
    // screen readers and .click(). Without this the keyboard cannot select.
    this.root.addEventListener('click', function (e) {
      if (self.viaPointer) return;
      var seg = e.target.closest ? e.target.closest('.seg') : null;
      var i = seg ? self.segs.indexOf(seg) : -1;
      if (i >= 0 && i !== self.idx) self.goTo(i);
    });
    this.root.addEventListener('keydown', function (e) {
      var seg = e.target.closest ? e.target.closest('.seg') : null;
      if (!seg) return;
      var i = self.segs.indexOf(seg), n = null;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') n = (i - 1 + self.segs.length) % self.segs.length;
      else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') n = (i + 1) % self.segs.length;
      else if (e.key === 'Home') n = 0;
      else if (e.key === 'End') n = self.segs.length - 1;
      if (n === null) return;
      e.preventDefault();
      self.goTo(n, null, true);
    });
    if (window.ResizeObserver) {
      new ResizeObserver(function () { if (!drag) self.measure(); }).observe(this.root);
    }
  };

  var pills = [].slice.call(document.querySelectorAll('.segs')).map(function (el) {
    return new Pill(el);
  });
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () {
      pills.forEach(function (p) { if (p.measure) p.measure(); });
    });
  }

  // ── disclosures open at the speed their chevron turns ─────────────────
  [].slice.call(document.querySelectorAll('details')).forEach(function (d) {
    var body = document.createElement('div');
    body.className = 'd-body';
    while (d.children.length > 1) body.appendChild(d.children[1]);
    d.appendChild(body);
    var sp = new Spring(0, 0.34, function (s) {
      body.style.height = s.value + 'px';
      if (s.done) {
        body.style.height = s.target ? '' : '0px';
        if (!s.target) d.open = false;      // stay open until the spring lands
      }
    });
    d.querySelector('summary').addEventListener('click', function (e) {
      e.preventDefault();
      var opening = !d.classList.contains('is-open');
      d.classList.toggle('is-open', opening);
      if (opening) {
        d.open = true;
        body.style.height = 'auto';
        var to = body.getBoundingClientRect().height;
        body.style.height = sp.value + 'px';
        sp.set(to);
      } else {
        if (sp.done) sp.value = body.getBoundingClientRect().height;
        sp.set(0);
      }
    });
  });

  // ── scroll edge: the rule only earns its keep once content is under it ──
  var chrome = document.querySelector('.chrome');
  if (chrome && chrome.parentNode) {
    // A sentinel above the bar rather than a scroll listener: no rAF, no
    // per-frame work, and it keeps working in a background tab.
    var sentinel = document.createElement('div');
    sentinel.className = 'chrome-sentinel';
    chrome.parentNode.insertBefore(sentinel, chrome);
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) {
        chrome.classList.toggle('is-stuck', !es[0].isIntersecting);
      }, { threshold: 0 }).observe(sentinel);
    } else {
      addEventListener('scroll', function () {
        chrome.classList.toggle('is-stuck',
          chrome.getBoundingClientRect().top <= 0.5);
      }, { passive: true });
    }
  }

  // ── tables: fade the overflowing edge, and lift it at the end ───────────
  [].slice.call(document.querySelectorAll('.tw')).forEach(function (tw) {
    var upd = function () {
      var over = tw.scrollWidth - tw.clientWidth;
      tw.classList.toggle('no-overflow', over <= 1);
      tw.classList.toggle('at-end', over > 1 && tw.scrollLeft >= over - 1);
    };
    tw.addEventListener('scroll', upd, { passive: true });
    if (window.ResizeObserver) new ResizeObserver(upd).observe(tw);
    upd();
  });

  // ── charts: mount as each nears the viewport, not nine at once ─────────
  var vizzes = [].slice.call(document.querySelectorAll('.viz[data-src]'));
  function mount(v) {
    if (v.dataset.mounted) return;
    v.dataset.mounted = '1';
    var f = document.createElement('iframe');
    f.setAttribute('title', v.dataset.title || 'Chart');
    f.setAttribute('loading', 'lazy');
    var dead = setTimeout(function () {
      if (!v.classList.contains('is-live')) {
        v.classList.add('is-dead');
        var s2 = v.querySelector('.vs');
        if (s2) s2.textContent = 'This chart could not load here.';
      }
    }, 6000);
    f.addEventListener('load', function () {
      clearTimeout(dead);
      v.classList.add('is-live');
    });
    f.src = v.dataset.src;
    v.appendChild(f);
  }
  if (vizzes.length) {
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (es) {
        es.forEach(function (e) {
          if (!e.isIntersecting) return;
          io.unobserve(e.target);
          mount(e.target);
        });
      }, { rootMargin: '500px 0px' });
      vizzes.forEach(function (v) { io.observe(v); });
    } else {
      vizzes.forEach(mount);
    }
  }

  apply(1);
})();
"""


def build(m):
    newest = m["d"].max().date()
    P = ['<div class="wrap">',
         "<h1>INIT FIU · Instagram</h1>",
         f'<p class="sub">Updated automatically · {len(m):,} posts analysed · '
         f'latest post {newest:%b %d, %Y}</p>',
         period_bar(),
         kpi_panes(m),
         guidance_card(m),
         format_section(m),
         # Full width, not raised beside a flat panel of the same size. Its
         # rank is that it is the answer, and width says that structurally
         # where a shadow was only saying it tonally.
         decision_card(m),
         '<div class="grid">',
         topic_section(m),
         audience_section("growth"),
         audience_section("who"),
         competitor_section(m),
         "</div>",
         charts_section(m),
         # The build stamp stays, quietly. Without it a stale deploy is
         # indistinguishable from a bug in the page.
         f'<footer><p class="sig">Built by <b>Claudia</b></p>'
         f'<p class="fmeta">Generated from the Instagram API · data through '
         f'{newest:%B %-d, %Y} · updates itself every week</p>'
         f'<p class="build">Page built '
         f'{dt.datetime.now():%-d %b %Y, %H:%M}</p></footer>',
         "</div>"]
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<title>INIT FIU · Instagram</title>"
            f"<style>{CSS}</style></head><body>"
            + "".join(P)
            + f"<script>{JS}</script></body></html>")


def main():
    m = load()
    (OUT / "index.html").write_text(build(m), encoding="utf-8")
    print(f"✅ site/index.html — {len(m)} posts, newest {m['d'].max().date()}")


if __name__ == "__main__":
    main()
