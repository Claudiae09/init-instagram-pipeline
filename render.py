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
    for i, (key, label, days, prior) in enumerate(PERIODS):
        p = R.compare_periods(m, days, label, prior)
        recs = R.period_recommendations(p)
        active = " is-on" if i == 1 else ""          # default to Month
        tabs.append(f'<button class="seg{active}" data-period="{key}" '
                    f'role="tab" aria-selected="{str(i == 1).lower()}">{label}</button>')
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
            f'<div class="pane{active}" id="p-{key}" role="tabpanel">'
            f'<p class="pane-meta">{meta}</p><ol>'
            + "".join(f"<li>{r}</li>" for r in recs) + "</ol>" + why + "</div>")
    return (
        '<section class="decision">'
        '<div class="decision-head"><h2>What to do next</h2>'
        f'<div class="segs" role="tablist">{"".join(tabs)}</div></div>'
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
        fmt_tabs.append(f'<button class="seg{on}" data-fmt="{j}" role="tab" '
                        f'aria-selected="{str(j == 0).lower()}">{label}</button>')

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
                        f'<div class="pane{show}" id="f-{pkey}-{j}" role="tabpanel">'
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
                             f'role="tabpanel">{body}</div>')
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
                         f'role="tabpanel">{body}</div>')

    return ('<section class="block"><h2>By format</h2>'
            '<p class="sub2">Follows the period you picked above.</p>'
            f'<div class="segs" role="tablist">{"".join(fmt_tabs)}</div>'
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
        rows = "".join(
            f'<tr><td>{esc(r["topic"])}</td><td>{r["posts"]}</td>'
            f'<td>{r["rate"]:.1f}</td>'
            f'<td class="{"up" if r["vs_avg"] > 0 else "down"}">'
            f'{r["vs_avg"]:+.0f}%</td><td>{r["recent"]}</td></tr>'
            for r in tf["rows"])
        table = ('<details class="why-mini"><summary><span class="chev">›</span> '
                 'See every subject</summary><div class="tw"><table class="topics">'
                 '<thead><tr><th>Subject</th><th>Posts</th><th>Shares<br>per 1k</th>'
                 '<th>vs your<br>average</th><th>Last<br>30 days</th></tr></thead>'
                 f'<tbody>{rows}</tbody></table></div></details>')
    return ('<section class="block"><h2>What to post next</h2>'
            '<p class="sub2">Ranked by what your own audience shares, since '
            'Instagram publishes nothing about what is trending.</p>'
            f'<ul class="csays">{bullets}</ul>{table}</section>')


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
   frame each one as a bright slab. */
:root{color-scheme:light;--bg:#fff;--fg:#15181e;--muted:#5d6675;--card:#f7f8fa;
--line:#e5e8ef;--accent:#3d6bf5;--soft:#eef2fe;--soft-line:#d6e0fc;--good:#12855f}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:clamp(28px,5vw,52px) clamp(16px,4vw,24px) 80px}
h1{font-size:clamp(1.55rem,4.4vw,2.25rem);line-height:1.14;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:clamp(1.1rem,2.6vw,1.35rem);margin:0;letter-spacing:-.01em}
h3{font-size:.95rem;margin:26px 0 8px;color:var(--muted);font-weight:600}
.sub{color:var(--muted);margin:0 0 30px;font-size:.93rem}
.sub2{color:var(--muted);margin:6px 0 14px;font-size:.9rem}

/* the one card that matters */
.decision{background:var(--soft);border:1px solid var(--soft-line);border-radius:16px;
padding:clamp(18px,3.5vw,26px);margin:0 0 34px}
.decision-head{display:flex;flex-wrap:wrap;gap:12px;align-items:center;
justify-content:space-between;margin-bottom:14px}
.decision ol{margin:0;padding-left:20px}
.decision li{margin:0 0 12px}.decision li:last-child{margin:0}
.pane-meta{color:var(--muted);font-size:.82rem;margin:0 0 12px}

.segs{display:inline-flex;background:#fff;border:1px solid var(--soft-line);
border-radius:10px;padding:3px;gap:2px}
.seg{border:0;background:none;font:inherit;font-size:.85rem;font-weight:600;
color:var(--muted);padding:6px 14px;border-radius:8px;cursor:pointer;
transition:background .15s ease,color .15s ease,transform .1s ease}
.seg:hover{color:var(--fg)}
.seg:active{transform:scale(.97)}
.seg:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.seg.is-on{background:var(--accent);color:#fff}
.pane{display:none}.pane.is-on{display:block}

.block{margin:0 0 34px}
.why-mini{margin:14px 0 0;border-top:1px solid var(--soft-line);padding-top:10px}
.why-mini summary{cursor:pointer;list-style:none;font-weight:600;font-size:.9rem;
color:var(--accent);display:flex;align-items:center;gap:6px;padding:4px 0}
.why-mini summary::-webkit-details-marker{display:none}
.why-mini[open] .chev{transform:rotate(90deg)}
.why-mini .line{font-size:.92rem;margin:8px 0}
ul.weak{margin:6px 0 4px;padding-left:20px;font-size:.9rem}
ul.weak li{margin:0 0 6px}
.dim{color:var(--muted);font-size:.85em}
.note{background:#fff8e6;border:1px solid #f0e0b8;border-radius:8px;padding:9px 12px;
margin:10px 0;font-size:.87rem;color:#6b5518}
.allhist{color:var(--muted);font-size:.82rem;margin:10px 0 0;font-style:italic}
.cwhat{color:var(--muted);font-size:.87rem;margin:0 0 6px;line-height:1.55}
.csays{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:8px;padding:11px 14px 11px 30px;margin:0 0 12px;font-size:.88rem;
line-height:1.55}
.csays li{margin:0 0 6px}
.tw{overflow-x:auto}
table.topics{border-collapse:collapse;width:100%;font-size:.85rem;margin:6px 0 0}
table.topics th{text-align:left;font-weight:600;color:var(--muted);font-size:.76rem;
padding:6px 10px 6px 0;border-bottom:1px solid var(--line);line-height:1.25}
table.topics td{padding:7px 10px 7px 0;border-bottom:1px solid var(--line)}
table.topics td:first-child{font-weight:500}
table.topics .up{color:var(--good);font-weight:600}
table.topics .down{color:#a4472e;font-weight:600}
.csays li:last-child{margin:0}
.banner{background:#fff4e0;border:1px solid #efd3a3;border-left:4px solid #d98c1f;
border-radius:8px;padding:12px 14px;margin:0 0 16px;font-size:.88rem;
color:#6b4a12;line-height:1.55}
.banner b{color:#5a3d0d}
.diag,.fix{display:block;font-size:.87rem;margin-top:4px;line-height:1.5}
.diag{color:var(--muted)}
.fix{color:var(--good);font-weight:500}
ul.weak li{margin:0 0 14px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;
margin:14px 0 18px}
.stats div{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 14px;font-size:.78rem;color:var(--muted);line-height:1.35}
.stats span{display:block;font-size:1.32rem;font-weight:700;color:var(--fg);
letter-spacing:-.02em;margin-bottom:2px}
.line{margin:0 0 10px}
.block ul{margin:4px 0 14px;padding-left:20px}
.block li{margin:0 0 8px}

.why{border:1px solid var(--line);border-radius:12px;background:var(--card);
padding:0 18px}
.why summary{cursor:pointer;padding:16px 0;font-weight:600;list-style:none;
display:flex;align-items:center;gap:8px}
.why summary::-webkit-details-marker{display:none}
.why summary em{color:var(--muted);font-style:normal;font-weight:400;font-size:.88rem}
.why[open] .chev{transform:rotate(90deg)}
.chev{display:inline-block;color:var(--accent);font-size:1.2rem;line-height:1;
transition:transform .18s ease}
.viz{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff;
margin-bottom:6px}
.viz iframe{width:100%;border:0;display:block}

.explore{display:inline-block;margin:18px 0 22px;padding:11px 20px;border-radius:10px;
background:var(--accent);color:#fff;text-decoration:none;font-size:.9rem;font-weight:600;
transition:filter .15s ease,transform .1s ease}
.explore:hover{filter:brightness(1.07)}.explore:active{transform:scale(.97)}
.explore:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
a{color:var(--accent)}
footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);
color:var(--muted);font-size:.84rem}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
@media (max-width:520px){.decision-head{flex-direction:column;align-items:flex-start}}
"""

JS = """
// One period drives the whole page: the recommendations pane and the format
// panes. Format choice is independent, so the visible pane is (period, format).
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

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.seg');
    if (!btn) return;
    var group = btn.parentElement;
    group.querySelectorAll('.seg').forEach(function (b) {
      b.classList.toggle('is-on', b === btn);
      b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
    });
    if (btn.dataset.period) state.period = btn.dataset.period;
    if (btn.dataset.fmt) state.fmt = btn.dataset.fmt;
    apply();
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
         charts_section(m),
         f'<footer>Generated from the Instagram API. Data through '
         f'{newest:%B %d, %Y}; the page rebuilds itself every week.</footer>',
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
