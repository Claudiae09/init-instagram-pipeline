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

import report_sections as R

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
           ("year", "Year", 365, "last year")]

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
        tabs.append(f'<button class="seg{active}" data-tab="p-{key}" '
                    f'role="tab" aria-selected="{str(i == 1).lower()}">{label}</button>')
        meta = (f"{p['posts']} posts in the last {days} days"
                if p.get("enough") else "not enough posts yet")
        panes.append(
            f'<div class="pane{active}" id="p-{key}" role="tabpanel">'
            f'<p class="pane-meta">{meta}</p><ol>'
            + "".join(f"<li>{r}</li>" for r in recs) + "</ol></div>")
    return (
        '<section class="decision">'
        '<div class="decision-head"><h2>What to do next</h2>'
        f'<div class="segs" role="tablist">{"".join(tabs)}</div></div>'
        + "".join(panes) + "</section>")


def format_section(m):
    tabs, panes = [], []
    for i, fmt in enumerate(R.FORMATS):
        prof = R.format_profile(m, fmt)
        if not prof:
            continue
        label = FORMAT_LABEL.get(fmt, fmt)
        active = " is-on" if i == 0 else ""
        tabs.append(f'<button class="seg{active}" data-tab="f-{i}" role="tab" '
                    f'aria-selected="{str(i == 0).lower()}">{label}</button>')

        bt = prof["best_time"]
        when = (f"<b>{bt['day']}"
                + (f" around {hour_label(bt['hour'])}" if bt["hour"] is not None else "")
                + f"</b> — median reach {bt['median_reach']:,} across {bt['n']} posts"
                ) if bt else "not enough posts to call a best time yet"

        vs = prof["share_vs_avg"]
        verdict = ("shares better than your average"
                   if vs > 5 else "shares worse than your average"
                   if vs < -5 else "shares about average")

        caps = R.caption_recommendations(R.caption_findings(m, fmt))
        top = prof["top_post"]
        top_cap = esc(str(top["caption"])[:110]) if top else ""

        panes.append(
            f'<div class="pane{active}" id="f-{i}" role="tabpanel">'
            f'<div class="stats">'
            f'<div><span>{prof["share_1k"]:.1f}</span>shares / 1k reached</div>'
            f'<div><span>{prof["reach_med"]:,.0f}</span>median reach</div>'
            f'<div><span>{prof["er"]:.1f}%</span>engagement</div>'
            f'<div><span>{prof["posts"]}</span>posts</div></div>'
            f'<p class="line"><b>Verdict.</b> {label} {verdict} '
            f'({vs:+.0f}% vs all formats).</p>'
            f'<p class="line"><b>Post them:</b> {when}.</p>'
            f'<p class="line"><b>Captions:</b></p><ul>'
            + "".join(f"<li>{c}</li>" for c in caps) + "</ul>"
            + (f'<p class="line"><b>Best performer ({prof["top_scope"]}):</b> '
               f'<a href="{esc(top["permalink"])}" target="_blank" rel="noopener">'
               f'{top_cap}…</a> — {top["shares"]:,.0f} shares, '
               f'{top["reach"]:,.0f} reached.</p>' if top else "")
            + "</div>")
    # Stories are a format too — same tab strip, different metrics.
    sf = R.story_findings(CSV)
    i = len(tabs)
    tabs.append(f'<button class="seg" data-tab="f-{i}" role="tab" '
                f'aria-selected="false">Stories</button>')
    if sf.get("enough"):
        st = (f'<div class="stats">'
              f'<div><span>{sf["completion"]:.0f}%</span>watch through</div>'
              f'<div><span>{sf["reach_med"]:,.0f}</span>median reach</div>'
              f'<div><span>{sf["n"]}</span>collected</div></div>')
    else:
        st = ""
    panes.append(
        f'<div class="pane" id="f-{i}" role="tabpanel">{st}'
        '<p class="line"><b>Collected daily</b>, since stories vanish after 24 hours.</p>'
        "<ul>" + "".join(f"<li>{r}</li>" for r in R.story_recommendations(sf))
        + "</ul></div>")

    return ('<section class="block"><h2>By format</h2>'
            '<p class="sub2">What each format is for, when to post it, and how to '
            'write it.</p>'
            f'<div class="segs" role="tablist">{"".join(tabs)}</div>'
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


def charts_section():
    items = []
    for title, sheet in CHARTS:
        src = (f"https://public.tableau.com/views/{TABLEAU_WORKBOOK}/{sheet}"
               f"?:embed=y&:showVizHome=no&:toolbar=no&:tabs=no&:display_count=no")
        items.append(
            f'<h3>{esc(title)}</h3>'
            f'<div class="viz"><iframe src="{src}" height="520" loading="lazy" '
            f'title="{esc(title)}"></iframe></div>')
    return ('<section class="block"><details class="why">'
            '<summary><span class="chev">›</span> See the data behind these '
            'recommendations <em>— 9 charts</em></summary>'
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
document.querySelectorAll('.segs').forEach(function(group){
  group.addEventListener('click', function(e){
    var btn = e.target.closest('.seg'); if(!btn) return;
    var panes = [];
    group.querySelectorAll('.seg').forEach(function(b){
      b.classList.toggle('is-on', b === btn);
      b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
      panes.push(b.dataset.tab);
    });
    panes.forEach(function(id){
      var el = document.getElementById(id);
      if(el) el.classList.toggle('is-on', id === btn.dataset.tab);
    });
  });
});
"""


def build(m):
    newest = m["d"].max().date()
    P = ['<div class="wrap">',
         "<h1>INIT FIU · Instagram</h1>",
         f'<p class="sub">Updated automatically · {len(m):,} posts analysed · '
         f'latest post {newest:%b %d, %Y}</p>',
         decision_card(m),
         format_section(m),
         charts_section(),
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
