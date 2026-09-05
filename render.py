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
import chart_notes as CN
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
    ("Share rate by format", "Sheet1"),
    ("Reach trend by month", "Sheet2"),
    ("Posting volume vs engagement", "Sheet4"),
    ("Best day and time to post", "Sheet5"),
    ("Saves vs shares by format", "Sheet7"),
    ("Most-shared posts", "Sheet8"),
    ("Reel watch time", "Sheet9"),
    ("Reach vs share rate, per post", "Sheet3"),
    ("Engagement rate by format", "Sheet6"),
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
def decision_card(m):
    """The one thing at the top: recommendations, switchable by period."""
    tabs, panes = [], []
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
        sel = (i == 1)
        tabs.append(f'<button class="seg{active}" data-period="{key}" id="t-{key}" '
                    f'role="tab" aria-controls="p-{key}" '
                    f'aria-selected="{str(sel).lower()}" '
                    f'tabindex="{0 if sel else -1}">{label}</button>')
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
        '<div class="decision-head"><h2>What to do next</h2>'
        f'<div class="segs" role="tablist" aria-label="Time period">'
        f'{"".join(tabs)}</div></div>'
        + "".join(panes) + "</section>")


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
                    + (f'<p class="line"><b>Best {label.lower()} of {span}:</b> '
                       f'<a href="{esc(t["permalink"])}" target="_blank" rel="noopener">'
                       f'{esc(str(t["caption"])[:100])}…</a> with {t["shares"]:,.0f} shares, '
                       f'{t["reach"]:,.0f} reached.</p>' if t else ""))

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

    return ('<section class="block"><h2>By format</h2>'
            '<p class="sub2">Follows the period you picked above.</p>'
            f'<div class="segs" role="tablist" aria-label="Post format">'
            f'{"".join(fmt_tabs)}</div>'
            + "".join(panes) + "</section>")


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
    return ('<section class="block"><h2>What to post next</h2>'
            '<p class="sub2">Ranked by what your own audience shares, since '
            'Instagram publishes nothing about what is trending.</p>'
            f'<ul class="csays">{bullets}</ul>{table}</section>')


def audience_section():
    """Who follows the account. The only part of the page not about posts."""
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
    return ('<section class="block"><h2>Who follows you</h2>'
            '<p class="sub2">Instagram reports this for followers, refreshed '
            'weekly.</p>'
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
        items.append(
            f'<h3>{esc(title)}</h3>{blurb}'
            f'<div class="viz"><iframe src="{src}" height="520" loading="lazy" '
            f'title="{esc(title)}"></iframe></div>')
    return ('<section class="block"><details class="why">'
            '<summary><span class="chev">›</span> See the data behind these '
            'recommendations <em>(9 charts)</em></summary>'
            '<p class="sub2">These are the live Tableau views. They refresh on their '
            'own as new data arrives.</p>'
            + "".join(items) +
            f'<a class="explore" href="{TABLEAU_HOME}" target="_blank" rel="noopener">'
            f'Open in Tableau →</a></details></section>')


CSS = """
/* Light-only: the embedded Tableau views render white, so a dark page would
   frame each one as a bright slab.

   Three decisions hold this sheet together:
     1. Five type sizes, assigned by role. Not by feel.
     2. Three surfaces, one per meaning: the answer, supporting detail, a
        caveat. Colour stopped carrying hierarchy once elevation did.
     3. Elevation is spent exactly once, on the primary card. */
:root{
  color-scheme:light;
  --bg:#fff;--fg:#15181e;--muted:#5d6675;--card:#f7f8fa;
  --line:#e5e8ef;--accent:#3d6bf5;--soft:#eef2fe;--soft-line:#d6e0fc;
  --good:#12855f;--bad:#a4472e;
  --warn-bg:#fff4e0;--warn-line:#efd3a3;--warn-bar:#d98c1f;--warn-fg:#6b4a12;

  --fs-micro:12px;   /* chips, table headers, footnotes, eyebrows */
  --fs-small:14px;   /* captions, notes, secondary lines          */
  --fs-body:16px;    /* everything you actually read              */
  --fs-lead:21px;    /* section headings, stat numbers            */
  --fs-title:36px;   /* the h1                                    */

  --r-sm:8px;        /* chips, notes, tables, media               */
  --r-lg:14px;       /* the primary card                          */

  --shadow:0 1px 2px rgba(17,21,28,.05), 0 8px 24px -12px rgba(17,21,28,.18);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
font:var(--fs-body)/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:clamp(28px,5vw,52px) clamp(16px,4vw,24px) 80px}

h1{font-size:clamp(25px,4.4vw,var(--fs-title));line-height:1.14;margin:0 0 6px;
letter-spacing:-.02em}
h2{font-size:var(--fs-lead);margin:0;letter-spacing:-.01em;line-height:1.25}
h3{font-size:var(--fs-small);margin:26px 0 8px;color:var(--muted);font-weight:600}
.sub{color:var(--muted);margin:0 0 30px;font-size:var(--fs-small)}
.sub2{color:var(--muted);margin:6px 0 14px;font-size:var(--fs-small)}

/* ── surface 1: the answer. The only raised thing on the page. ───────────── */
.decision{background:var(--bg);border:1px solid var(--line);border-radius:var(--r-lg);
box-shadow:var(--shadow);padding:clamp(20px,3.5vw,28px);margin:0 0 34px}
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
.banner b{color:#5a3d0d}

/* ── controls ───────────────────────────────────────────────────────────── */
.segs{display:inline-flex;flex-wrap:wrap;background:var(--card);
border:1px solid var(--line);border-radius:var(--r-sm);padding:3px;gap:2px}
.seg{border:0;background:none;font:inherit;font-size:var(--fs-small);font-weight:600;
color:var(--muted);padding:11px 14px;min-height:44px;
border-radius:calc(var(--r-sm) - 2px);cursor:pointer;
transition:background .15s ease,color .15s ease,transform .1s ease}
.seg:hover{color:var(--fg)}
.seg:active{transform:scale(.97)}
.seg:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.seg.is-on{background:var(--accent);color:#fff}
.pane{display:none}.pane.is-on{display:block}
.pane:focus{outline:none}

.block{margin:0 0 34px}
.line{margin:0 0 10px}
.block ul{margin:4px 0 14px;padding-left:20px}
.block li{margin:0 0 8px}
.dim{color:var(--muted);font-size:var(--fs-micro)}
.build{opacity:.75}
.allhist{color:var(--muted);font-size:var(--fs-micro);margin:10px 0 0;font-style:italic}

/* ── disclosures. One component, one default: closed. ────────────────────── */
.why-mini{margin:14px 0 0;border-top:1px solid var(--line);padding-top:10px}
.why-mini summary{cursor:pointer;list-style:none;font-weight:600;
font-size:var(--fs-small);color:var(--accent);display:flex;align-items:center;
gap:6px;padding:8px 0;min-height:44px}
.why-mini summary::-webkit-details-marker{display:none}
.why-mini[open] .chev{transform:rotate(90deg)}
.why-mini .line{font-size:var(--fs-small);margin:8px 0}
.why{border:1px solid var(--line);border-radius:var(--r-sm);background:var(--card);
padding:0 18px}
.why summary{cursor:pointer;padding:16px 0;font-weight:600;list-style:none;
display:flex;align-items:center;gap:8px;min-height:44px}
.why summary::-webkit-details-marker{display:none}
.why summary em{color:var(--muted);font-style:normal;font-weight:400;
font-size:var(--fs-small)}
.why[open] .chev{transform:rotate(90deg)}
.chev{display:inline-block;color:var(--accent);font-size:var(--fs-lead);line-height:1;
transition:transform .18s ease}

/* ── weak-post diagnostics ──────────────────────────────────────────────── */
ul.weak{margin:6px 0 4px;padding-left:20px;font-size:var(--fs-small)}
ul.weak li{margin:0 0 14px}
.diag,.fix{display:block;font-size:var(--fs-small);margin-top:4px;line-height:1.5}
.diag{color:var(--muted)}
.fix{color:var(--good);font-weight:500}

/* ── stat tiles. The first figure is the argument; the rest are context. ─── */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;
margin:14px 0 18px}
.stats div{background:var(--card);border:1px solid var(--line);
border-radius:var(--r-sm);padding:12px 14px;font-size:var(--fs-micro);
color:var(--muted);line-height:1.35}
.stats span{display:block;font-size:var(--fs-body);font-weight:700;color:var(--fg);
letter-spacing:-.02em;margin-bottom:2px}
.stats div:first-child span{font-size:var(--fs-lead)}

/* ── the subject table ──────────────────────────────────────────────────── */
.tw{overflow-x:auto}
table.topics{border-collapse:collapse;width:100%;font-size:var(--fs-small);margin:6px 0 0}
table.topics th{text-align:left;font-weight:600;color:var(--muted);
font-size:var(--fs-micro);padding:6px 10px 6px 0;border-bottom:1px solid var(--line);
line-height:1.25;white-space:nowrap}
table.topics td{padding:8px 10px 8px 0;border-bottom:1px solid var(--line)}
table.topics td:first-child{font-weight:500;min-width:190px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;padding-right:0}
table.topics .skew{color:var(--muted);font-weight:400}
table.topics td.foot{color:var(--muted);font-size:var(--fs-micro);line-height:1.45;
padding-top:9px;border-bottom:0;text-align:left}
table.topics .up{color:var(--good);font-weight:600}
table.topics .down{color:var(--bad);font-weight:600}
a.tlink{color:var(--accent);text-decoration:none;display:block}
a.tlink:hover{text-decoration:underline}
a.tlink .eg{display:block;color:var(--muted);font-weight:400;
font-size:var(--fs-micro);line-height:1.35;margin-top:2px;text-decoration:none}

/* ── audience bars ──────────────────────────────────────────────────────── */
.bars{margin:14px 0 16px}
.bar{display:grid;grid-template-columns:56px 1fr 44px;align-items:center;gap:10px;
margin:0 0 6px;font-size:var(--fs-micro);color:var(--muted)}
.bl{font-variant-numeric:tabular-nums}
.bt{background:var(--card);border:1px solid var(--line);border-radius:var(--r-sm);
height:14px;overflow:hidden}
.bt i{display:block;height:100%;background:var(--accent);opacity:.85}
.bv{text-align:right;font-variant-numeric:tabular-nums;color:var(--fg);font-weight:600}

/* ── charts ─────────────────────────────────────────────────────────────── */
.viz{border:1px solid var(--line);border-radius:var(--r-sm);overflow:hidden;
background:var(--bg);margin-bottom:6px}
.viz iframe{width:100%;border:0;display:block}
.explore{display:inline-block;margin:18px 0 22px;padding:13px 20px;
border-radius:var(--r-sm);background:var(--accent);color:#fff;text-decoration:none;
font-size:var(--fs-small);font-weight:600;min-height:44px;
transition:filter .15s ease,transform .1s ease}
.explore:hover{filter:brightness(1.07)}.explore:active{transform:scale(.97)}
.explore:focus-visible{outline:2px solid var(--accent);outline-offset:3px}

a{color:var(--accent)}
footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);
color:var(--muted);font-size:var(--fs-small)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
@media (max-width:520px){.decision-head{flex-direction:column;align-items:flex-start}}
"""

JS = """
// One period drives the whole page: the recommendations pane and the format
// panes. Format choice is independent, so the visible pane is (period, format).
//
// The tabs declare role="tab", which is a promise that arrow keys work and that
// only the selected tab is in the tab order. Both are implemented below; a
// half-kept promise is worse for a screen reader than no roles at all.
(function () {
  var state = { period: 'month', fmt: '0' };

  function apply() {
    document.querySelectorAll('[id^="p-"].pane').forEach(function (el) {
      el.classList.toggle('is-on', el.id === 'p-' + state.period);
    });
    document.querySelectorAll('[id^="f-"].pane').forEach(function (el) {
      el.classList.toggle('is-on', el.id === 'f-' + state.period + '-' + state.fmt);
    });
  }

  function select(btn, focus) {
    var group = btn.parentElement;
    group.querySelectorAll('.seg').forEach(function (b) {
      var on = b === btn;
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;          // roving tabindex
    });
    if (btn.dataset.period) state.period = btn.dataset.period;
    if (btn.dataset.fmt) state.fmt = btn.dataset.fmt;
    if (focus) btn.focus();
    apply();
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.seg');
    if (btn) select(btn, false);
  });

  document.addEventListener('keydown', function (e) {
    var btn = e.target.closest('.seg');
    if (!btn) return;
    var keys = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 };
    var segs = Array.prototype.slice.call(btn.parentElement.querySelectorAll('.seg'));
    var i = segs.indexOf(btn), next = null;
    if (e.key in keys) next = segs[(i + keys[e.key] + segs.length) % segs.length];
    else if (e.key === 'Home') next = segs[0];
    else if (e.key === 'End') next = segs[segs.length - 1];
    if (!next) return;
    e.preventDefault();
    select(next, true);
  });

  apply();
})();
"""


def build(m):
    newest = m["d"].max().date()
    P = ['<div class="wrap">',
         "<h1>INIT FIU · Instagram</h1>",
         f'<p class="sub">Updated automatically · {len(m):,} posts analysed · '
         f'latest post {newest:%b %d, %Y}</p>',
         decision_card(m),
         topic_section(m),
         format_section(m),
         audience_section(),
         charts_section(m),
         # Build stamp so it is obvious at a glance whether the deployed page
         # is the current one. Without it, a stale deploy is indistinguishable
         # from a bug in the page itself.
         f'<footer>Generated from the Instagram API. Data through '
         f'{newest:%B %d, %Y}; the page rebuilds itself every week.<br>'
         f'<span class="build">Page built '
         f'{dt.datetime.now():%d %b %Y, %H:%M} local</span></footer>',
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
