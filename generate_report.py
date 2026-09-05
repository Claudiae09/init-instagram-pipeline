#!/usr/bin/env python3
"""
Generate a self-contained HTML dashboard from the pulled Instagram data.

Fully autonomous: reads csv/, computes the insights, writes site/index.html with
a plain-language TL;DR, its own inline-SVG charts (no external libraries), and a
"what this means" note under every chart. Designed to be deployed to Cloudflare
Pages by the weekly GitHub Actions run.

Run:  python3 generate_report.py
"""
import datetime as dt
import html
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CSV = HERE / "csv"
OUT = HERE / "site"
OUT.mkdir(exist_ok=True)

# Published Tableau Public workbook. Each section embeds the matching sheet;
# the narrative around it is still computed from the data below.
TABLEAU_WORKBOOK = "Init-Instagram"
TABLEAU_PROFILE = "claudia.espinosa3716"
TABLEAU_HOME = (f"https://public.tableau.com/app/profile/{TABLEAU_PROFILE}"
                f"/viz/{TABLEAU_WORKBOOK}/Sheet1")


def tableau(sheet, height=560):
    """Embed one published Tableau sheet."""
    src = (f"https://public.tableau.com/views/{TABLEAU_WORKBOOK}/{sheet}"
           f"?:embed=y&:showVizHome=no&:toolbar=no&:tabs=no&:display_count=no")
    return (f'<div class="viz"><iframe src="{src}" height="{height}" loading="lazy" '
            f'title="{sheet}" referrerpolicy="no-referrer-when-downgrade"></iframe></div>')


NUMERIC = ["reach", "shares", "saved", "total_interactions", "likes", "comments",
           "views", "avg_watch_time_sec", "total_watch_time_sec", "follows",
           "profile_visits", "engagement_rate"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# Brand-neutral palette, readable in light and dark
C = {"carousel": "#4f7cff", "reel": "#f0913a", "image": "#8b93a7",
     "accent": "#4f7cff", "warn": "#d9534f", "good": "#2f9e6b", "grid": "#c9cedb"}


# ── data ────────────────────────────────────────────────────────────────────
def load():
    m = pd.read_csv(CSV / "media_performance.csv")
    for c in NUMERIC:
        if c in m.columns:
            m[c] = pd.to_numeric(m[c], errors="coerce")
    m["d"] = pd.to_datetime(m["publish_date_est"], errors="coerce")
    m = m.dropna(subset=["d"])
    m["month"] = m["d"].dt.to_period("M")
    return m


def rate(df, col, per=1000):
    """Aggregate rate: total col / total reach. Avoids tiny-reach posts skewing."""
    r = df["reach"].sum()
    return (df[col].sum() / r * per) if r else 0.0


def by_type(m):
    rows = []
    for t, d in m.groupby("post_type"):
        rows.append({
            "type": t, "posts": len(d),
            "reach_med": d["reach"].median(),
            "share_1k": rate(d, "shares"),
            "saves_1k": rate(d, "saved"),
            "er": rate(d, "total_interactions", 100),
        })
    return sorted(rows, key=lambda r: -r["share_1k"])


def monthly(m, n=12):
    g = m.groupby("month").agg(posts=("reach", "size"),
                               reach_med=("reach", "median"),
                               inter=("total_interactions", "sum"),
                               reach_sum=("reach", "sum")).tail(n)
    g["er"] = g["inter"] / g["reach_sum"] * 100
    return g.reset_index()


def best_slots(m, min_posts=3, top=5):
    g = m.groupby(["publish_weekday", "publish_hour_est"]).agg(
        n=("reach", "size"), med=("reach", "median"))
    g = g[g["n"] >= min_posts].sort_values("med", ascending=False).head(top)
    return [(w, int(h), int(r["med"]), int(r["n"])) for (w, h), r in g.iterrows()]



def fmt_val(v):
    """2831.0 -> '2,831'; 8.778 -> '8.8'. Integers never show a decimal."""
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 and abs(v) >= 100 else f"{v:,.1f}"


def nice_max(v):
    """Round an axis maximum up to a human number (1k, 2.5k, 3k) not 3341."""
    if v <= 0:
        return 1
    import math
    mag = 10 ** math.floor(math.log10(v))
    for step in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= step * mag:
            return step * mag
    return 10 * mag


# ── tiny SVG chart helpers (no libraries, theme-safe) ───────────────────────
def svg_open(w, h, extra=""):
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" height="auto" '
            f'preserveAspectRatio="xMidYMid meet" role="img" {extra}>')


def bar_chart(labels, values, colors, unit="", w=680, h=260):
    if not values:
        return "<p class='muted'>No data.</p>"
    pad_l, pad_b, pad_t = 54, 42, 14
    mx = nice_max(max(values))
    bw = (w - pad_l - 16) / len(values)
    s = [svg_open(w, h)]
    for i in range(5):                                     # gridlines
        y = pad_t + (h - pad_t - pad_b) * i / 4
        val = mx * (1 - i / 4)
        s.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w-8}" y2="{y:.0f}" '
                 f'stroke="{C["grid"]}" stroke-width="1" opacity=".35"/>')
        s.append(f'<text x="{pad_l-8}" y="{y+4:.0f}" text-anchor="end" '
                 f'class="ax">{fmt_val(val)}</text>')
    for i, (lab, v, col) in enumerate(zip(labels, values, colors)):
        bh = (h - pad_t - pad_b) * (v / mx)
        x = pad_l + i * bw + bw * 0.18
        y = h - pad_b - bh
        s.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{bw*0.64:.0f}" '
                 f'height="{bh:.0f}" rx="4" fill="{col}"/>')
        s.append(f'<text x="{x+bw*0.32:.0f}" y="{y-6:.0f}" text-anchor="middle" '
                 f'class="val">{fmt_val(v)}{unit}</text>')
        s.append(f'<text x="{x+bw*0.32:.0f}" y="{h-pad_b+18:.0f}" '
                 f'text-anchor="middle" class="ax">{html.escape(str(lab))}</text>')
    s.append("</svg>")
    return "".join(s)


def line_chart(labels, values, w=680, h=250, color=None, unit=""):
    if len(values) < 2:
        return "<p class='muted'>Not enough data yet.</p>"
    color = color or C["accent"]
    pad_l, pad_b, pad_t = 54, 42, 14
    mx, mn = nice_max(max(values)), 0
    iw, ih = w - pad_l - 16, h - pad_t - pad_b
    pts = [(pad_l + iw * i / (len(values) - 1),
            pad_t + ih * (1 - (v - mn) / (mx - mn or 1))) for i, v in enumerate(values)]
    s = [svg_open(w, h)]
    for i in range(5):
        y = pad_t + ih * i / 4
        s.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w-8}" y2="{y:.0f}" '
                 f'stroke="{C["grid"]}" stroke-width="1" opacity=".35"/>')
        s.append(f'<text x="{pad_l-8}" y="{y+4:.0f}" text-anchor="end" class="ax">'
                 f'{mx*(1-i/4):.0f}</text>')
    s.append('<polyline fill="none" stroke="%s" stroke-width="2.5" points="%s"/>'
             % (color, " ".join(f"{x:.0f},{y:.0f}" for x, y in pts)))
    for (x, y), v in zip(pts, values):
        s.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3.5" fill="{color}"/>')
    step = max(1, len(labels) // 8)
    for i, lab in enumerate(labels):
        if i % step == 0 or i == len(labels) - 1:
            s.append(f'<text x="{pts[i][0]:.0f}" y="{h-pad_b+18:.0f}" '
                     f'text-anchor="middle" class="ax">{html.escape(str(lab))}</text>')
    s.append("</svg>")
    return "".join(s)


def combo_chart(labels, bars, line, w=680, h=270):
    """Bars (post volume) + line (engagement rate) on independent scales."""
    if not bars:
        return "<p class='muted'>No data.</p>"
    pad_l, pad_r, pad_b, pad_t = 48, 48, 42, 14
    bmx, lmx = max(bars) * 1.2 or 1, max(line) * 1.3 or 1
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    bw = iw / len(bars)
    s = [svg_open(w, h)]
    for i in range(5):
        y = pad_t + ih * i / 4
        s.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w-pad_r}" y2="{y:.0f}" '
                 f'stroke="{C["grid"]}" stroke-width="1" opacity=".3"/>')
        s.append(f'<text x="{pad_l-8}" y="{y+4:.0f}" text-anchor="end" class="ax">'
                 f'{bmx*(1-i/4):.0f}</text>')
        s.append(f'<text x="{w-pad_r+8}" y="{y+4:.0f}" class="ax" fill="{C["warn"]}">'
                 f'{lmx*(1-i/4):.1f}</text>')
    for i, v in enumerate(bars):
        bh = ih * (v / bmx)
        s.append(f'<rect x="{pad_l+i*bw+bw*0.2:.0f}" y="{pad_t+ih-bh:.0f}" '
                 f'width="{bw*0.6:.0f}" height="{bh:.0f}" rx="3" '
                 f'fill="{C["accent"]}" opacity=".55"/>')
    lp = [(pad_l + i * bw + bw / 2, pad_t + ih * (1 - v / lmx)) for i, v in enumerate(line)]
    s.append('<polyline fill="none" stroke="%s" stroke-width="2.5" points="%s"/>'
             % (C["warn"], " ".join(f"{x:.0f},{y:.0f}" for x, y in lp)))
    for x, y in lp:
        s.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3.2" fill="{C["warn"]}"/>')
    step = max(1, len(labels) // 8)
    for i, lab in enumerate(labels):
        if i % step == 0 or i == len(labels) - 1:
            s.append(f'<text x="{lp[i][0]:.0f}" y="{h-pad_b+18:.0f}" '
                     f'text-anchor="middle" class="ax">{html.escape(str(lab))}</text>')
    s.append("</svg>")
    return "".join(s)


def heatmap(m, w=680):
    hours = sorted(h for h in m["publish_hour_est"].dropna().unique())
    if not hours:
        return "<p class='muted'>No data.</p>"
    hours = [int(h) for h in hours]
    piv = m.pivot_table(index="publish_weekday", columns="publish_hour_est",
                        values="reach", aggfunc="median")
    mx = piv.max().max() or 1
    cw, ch, pad_l, pad_t = (w - 80) / len(hours), 30, 76, 24
    h_total = pad_t + ch * 7 + 26
    s = [svg_open(w, h_total)]
    for j, hr in enumerate(hours):
        lab = f"{hr%12 or 12}{'a' if hr<12 else 'p'}"
        s.append(f'<text x="{pad_l+j*cw+cw/2:.0f}" y="{pad_t-8}" '
                 f'text-anchor="middle" class="ax">{lab}</text>')
    for i, day in enumerate(WEEKDAYS):
        y = pad_t + i * ch
        s.append(f'<text x="{pad_l-8}" y="{y+ch/2+4:.0f}" text-anchor="end" '
                 f'class="ax">{day[:3]}</text>')
        for j, hr in enumerate(hours):
            v = piv.loc[day, hr] if (day in piv.index and hr in piv.columns) else None
            if pd.isna(v) if v is not None else True:
                fill, op = "none", 0
            else:
                fill, op = C["accent"], 0.12 + 0.88 * (v / mx)
            s.append(f'<rect x="{pad_l+j*cw:.0f}" y="{y:.0f}" width="{cw-2:.0f}" '
                     f'height="{ch-2:.0f}" rx="3" fill="{fill}" opacity="{op:.2f}" '
                     f'stroke="{C["grid"]}" stroke-opacity=".25"/>')
    s.append("</svg>")
    return "".join(s)


# ── narrative ───────────────────────────────────────────────────────────────
def pct_change(a, b):
    return ((b - a) / a * 100) if a else 0.0


def build_tldr(m, types, mon, slots):
    """Plain-language recommendations, computed — no hand-written conclusions."""
    recs = []
    best, worst = types[0], types[-1]
    recs.append(
        f"<b>Lead with {best['type']}s.</b> They earn "
        f"<b>{best['share_1k']:.1f} shares per 1,000 people reached</b> — the strongest "
        f"of any format — versus {worst['share_1k']:.1f} for {worst['type']}s. Shares are "
        f"how you reach people who don't follow you yet, so this is the format that grows you.")

    reach = m.groupby("post_type")["reach"].median().sort_values(ascending=False)
    top_reach = reach.index[0]
    if top_reach != best["type"]:
        recs.append(
            f"<b>Use {top_reach}s for awareness, {best['type']}s for action.</b> "
            f"{top_reach}s reach the most people (median <b>{reach.iloc[0]:,.0f}</b> vs "
            f"{reach.get(best['type'], 0):,.0f}), but {best['type']}s convert that attention "
            f"into shares and saves at a higher rate. Pair them: {top_reach}s to get seen, "
            f"{best['type']}s to get acted on.")

    if len(worst) and worst["er"] < best["er"] * 0.75:
        recs.append(
            f"<b>Cut back on {worst['type']}s.</b> They engage at "
            f"<b>{worst['er']:.1f}%</b> against {best['er']:.1f}% for {best['type']}s — "
            f"roughly {(1-worst['er']/best['er'])*100:.0f}% weaker. That posting slot is "
            f"better spent on a stronger format.")

    if len(mon) >= 4:
        recent = mon.tail(3)["reach_med"].mean()
        prior = mon.tail(6).head(3)["reach_med"].mean()
        ch = pct_change(prior, recent)
        if abs(ch) >= 12:
            direction = "up" if ch > 0 else "down"
            recs.append(
                f"<b>Reach is trending {direction} {abs(ch):.0f}% over 3 months.</b> Median "
                f"reach per post for the last 3 months is <b>{recent:,.0f}</b>, against "
                f"{prior:,.0f} in the 3 months before. " +
                ("Keep doing what changed." if ch > 0 else
                 "Worth reviewing what shifted — content mix, timing, or posting frequency.") +
                " <i>(3-month window — the month-by-month chart below can move differently.)</i>")

    if len(mon) >= 6:
        hi = mon.loc[mon["posts"].idxmax()]
        med_er = mon["er"].median()
        # Only claim a gap if the two numbers actually differ once rounded to the
        # precision we print — otherwise it reads "fell to 5.7%, below 5.7%".
        if round(hi["er"], 1) < round(med_er, 1):
            recs.append(
                f"<b>More posts didn't mean more engagement.</b> {hi['month']} was your "
                f"heaviest month (<b>{int(hi['posts'])} posts</b>) but engagement fell to "
                f"{hi['er']:.1f}%, below the {med_er:.1f}% typical month. "
                f"Volume alone isn't working — quality per post matters more.")

    if slots:
        top3 = ", ".join(f"{w} {h%12 or 12}{'am' if h<12 else 'pm'}" for w, h, _, _ in slots[:3])
        recs.append(f"<b>Best posting windows: {top3}.</b> These slots have produced the "
                    f"highest median reach across your history.")
    return recs


# ── page ────────────────────────────────────────────────────────────────────
CSS = """
/* Light-only on purpose: the embedded Tableau views render on a white canvas,
   so a dark page would frame them as bright slabs. One theme = one look. */
:root{color-scheme:light;
--bg:#ffffff;--fg:#16181d;--muted:#5b6472;--card:#f7f8fa;--line:#e4e7ee;
--accent:#3d6bf5;--accent-soft:#eef2fe}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:clamp(24px,5vw,48px) clamp(16px,4vw,24px) 72px}
h1{font-size:clamp(1.6rem,4.5vw,2.4rem);line-height:1.12;margin:0 0 8px;letter-spacing:-.02em}
h2{font-size:clamp(1.05rem,2.6vw,1.3rem);margin:48px 0 8px;letter-spacing:-.01em;line-height:1.3}
h3{font-size:1rem;margin:26px 0 6px;color:var(--muted);font-weight:600}
.sub{color:var(--muted);margin:0 0 34px;font-size:.94rem}
.tldr{background:var(--accent-soft);border:1px solid #d7e0fb;border-radius:14px;
padding:clamp(18px,4vw,26px);margin:0 0 10px}
.tldr h2{margin:0 0 14px;font-size:.78rem;text-transform:uppercase;letter-spacing:.09em;
color:var(--accent);font-weight:700}
.tldr ol{margin:0;padding-left:22px}
.tldr li{margin:0 0 13px}.tldr li:last-child{margin-bottom:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px;margin:14px 0 0;overflow-x:auto}
.viz{margin:14px 0 0;border:1px solid var(--line);border-radius:12px;overflow:hidden;
background:#fff;box-shadow:0 1px 2px rgba(16,24,40,.04)}
.viz iframe{width:100%;border:0;display:block}
.means{border-left:3px solid var(--line);padding:2px 0 2px 15px;margin:16px 0 0;
color:var(--muted);font-size:.94rem}
.means b{color:var(--fg)}
.rec{margin:12px 0 0;padding:14px 16px;background:var(--accent-soft);
border:1px solid #d7e0fb;border-radius:10px;font-size:.94rem}
.rec span{display:inline-block;font-size:.68rem;font-weight:700;letter-spacing:.09em;
text-transform:uppercase;color:var(--accent);margin-right:8px}
a{color:var(--accent)}
.explore{display:inline-block;margin:26px 0 0;padding:11px 20px;border-radius:10px;
background:var(--accent);color:#fff;text-decoration:none;font-size:.92rem;font-weight:600;
transition:transform .1s ease,filter .15s ease}
.explore:hover{filter:brightness(1.07)}
.explore:active{transform:scale(.97)}
.explore:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.ax{font-size:11px;fill:var(--muted)}
.val{font-size:11.5px;fill:var(--fg);font-weight:600}
.muted{color:var(--muted)}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:.85rem;color:var(--muted);margin-top:10px}
.dot{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}
footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--line);
color:var(--muted);font-size:.85rem}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""


def section(title, chart, means, extra="", rec=""):
    rec_html = f"<p class='rec'><span>Do this</span> {rec}</p>" if rec else ""
    return (f"<h2>{title}</h2>{extra}<div class='card'>{chart}</div>"
            f"<p class='means'>{means}</p>{rec_html}")


def build(m):
    types = by_type(m)
    mon = monthly(m)
    slots = best_slots(m)
    recs = build_tldr(m, types, mon, slots)
    newest = m["d"].max().date()
    today = dt.date.today()

    P = [f"<!-- generated {dt.datetime.now():%Y-%m-%d %H:%M} -->",
         "<div class='wrap'>",
         "<h1>INIT FIU · Instagram performance</h1>",
         f"<p class='sub'>Updated automatically · {len(m):,} posts analysed "
         f"({m['d'].min():%b %Y} – {m['d'].max():%b %Y}) · most recent post "
         f"{newest:%b %d, %Y}</p>"]

    # TL;DR
    P.append("<div class='tldr'><h2>What to do next</h2><ol>")
    P += [f"<li>{r}</li>" for r in recs]
    P.append("</ol></div>")
    P.append("<p class='means'>Everything below is computed from the last "
             f"{len(m):,} posts and refreshes on its own each week. "
             "Each chart has a plain-language note explaining what it shows.</p>")

    # 1. share rate by type
    cols = [C.get(t["type"].split()[-1], C["accent"]) for t in types]
    P.append(section(
        "1 · Which format gets shared most",
        tableau("Sheet1", 520),
        f"<b>Shares per 1,000 people reached.</b> This is the most important chart here: "
        f"a share puts your post in front of someone who doesn't follow you. "
        f"<b>{types[0]['type']}s lead at {types[0]['share_1k']:.1f}</b>, "
        f"{types[-1]['type']}s trail at {types[-1]['share_1k']:.1f}. "
        f"Higher bar = better at reaching new people. "
        f"<b>These figures cover all {len(m):,} posts</b> — the embedded chart may be "
        f"filtered to the current year, where a single high-performing post can flip the "
        f"ranking. Judge formats on the full history.",
        rec=f"Shift your posting mix toward <b>{types[0]['type']}s</b>. If you make one "
            f"change this week, make it this one — they spread "
            f"{types[0]['share_1k']/types[-1]['share_1k']:.1f}× better than "
            f"{types[-1]['type']}s."))

    # 2. reach trend
    P.append(section(
        "2 · Are we reaching more people over time?",
        tableau("Sheet2", 520),
        f"<b>Median people reached per post, by month.</b> Median (not average) so one viral "
        f"post can't distort the trend. Latest month: "
        f"<b>{mon.iloc[-1]['reach_med']:,.0f}</b> per post. "
        f"Rising = your content is escaping your existing follower base.",
        rec=(f"The most recent month ({mon.iloc[-1]['reach_med']:,.0f}) is "
             + ("at or above" if mon.iloc[-1]["reach_med"] >= mon["reach_med"].median()
                else "below")
             + f" your typical month ({mon['reach_med'].median():,.0f}). "
             + ("Keep the current mix and rhythm."
                if mon.iloc[-1]["reach_med"] >= mon["reach_med"].median() else
                "Review what changed — format mix, posting times, or a posting gap.")
             + " <i>(single-month comparison; the 3-month trend above answers a different "
               "question and can point the other way.)</i>")))

    # 3. volume vs ER
    P.append(section(
        "3 · Does posting more actually help?",
        tableau("Sheet4", 540),
        "<b>Bars = number of posts. Line = engagement rate.</b> If the bars go up while the "
        "line goes down, you're posting more and getting less back per post — a signal to "
        "slow down and raise quality rather than volume.",
        extra="<div class='legend'><span><span class='dot' style='background:%s;opacity:.55'>"
        "</span>Posts published</span><span><span class='dot' style='background:%s'></span>"
        "Engagement rate %%</span></div>" % (C["accent"], C["warn"]),
        rec=("Your heaviest posting month had below-average engagement — treat post count "
             "as a ceiling, not a target. Fewer, stronger posts beat more, weaker ones."
             if mon.loc[mon["posts"].idxmax()]["er"] < mon["er"].median() else
             "Volume and engagement are moving together — your current cadence is working. "
             "Keep it.")))

    # 4. heatmap
    slot_txt = ", ".join(f"<b>{w} {h%12 or 12}{'am' if h<12 else 'pm'}</b>"
                         for w, h, _, _ in slots[:3]) or "not enough data yet"
    P.append(section(
        "4 · When should we post?",
        tableau("Sheet5", 560),
        f"<b>Darker = more people reached.</b> Each square is a day-and-hour slot; shading is "
        f"the median reach of posts published then. Your strongest windows: {slot_txt}. "
        f"Blank squares are times you haven't posted.",
        rec=(f"Schedule your most important posts for {slots[0][0]} around "
             f"{slots[0][1]%12 or 12}{'am' if slots[0][1]<12 else 'pm'} — it's your "
             f"highest-reach slot ({slots[0][2]:,} median). Save low-stakes posts for "
             f"the lighter squares." if slots else
             "Keep posting across varied days and times so this fills in.")))

    # 5. saves + shares by type
    P.append(section(
        "5 · Saves vs shares by format",
        tableau("Sheet7", 540),
        "<b>Per 1,000 reached.</b> Saves mean people want to come back to it — useful for "
        "deadlines, opportunities, how-tos. Shares mean they're spreading it. Saves show "
        "value; shares show growth. Both matter, for different goals.",
        rec=f"Shares outrun saves roughly "
            f"{sum(t['share_1k'] for t in types)/max(sum(t['saves_1k'] for t in types),.01):.1f}× "
            f"across every format — your audience spreads content more than it bookmarks it. "
            f"Lean into community and identity posts over pure reference material."))

    # 6. top posts
    top = m.nlargest(10, "shares")[["caption", "post_type", "reach", "shares",
                                    "saved", "permalink"]]
    rows = []
    for _, r in top.iterrows():
        cap = html.escape(str(r["caption"])[:90]) or "(no caption)"
        link = html.escape(str(r["permalink"]))
        rows.append(
            f"<tr><td class='cap'><a href='{link}' target='_blank' rel='noopener'>{cap}</a></td>"
            f"<td>{html.escape(str(r['post_type']).replace('IG ',''))}</td>"
            f"<td class='n'>{r['reach']:,.0f}</td><td class='n'>{r['shares']:,.0f}</td>"
            f"<td class='n'>{r['saved']:,.0f}</td></tr>")
    P.append(section(
        "6 · Your 10 most-shared posts",
        tableau("Sheet8", 600),
        "<b>Ranked by shares.</b> These are the posts that travelled furthest beyond your "
        "followers — the closest thing to a template for what to make more of. "
        "Click any caption to open the post."))

    # 7. reels watch time
    reels = m[(m["post_type"] == "IG reel") & m["avg_watch_time_sec"].notna()]
    if len(reels) >= 3:
        rm = reels.groupby(reels["d"].dt.to_period("M"))["avg_watch_time_sec"].median().tail(12)
        P.append(section(
            "7 · How long people watch our reels",
            tableau("Sheet9", 520),
            f"<b>Median seconds watched per reel, by month.</b> Currently "
            f"<b>{rm.iloc[-1]:.1f}s</b>. Watch time is the main thing Instagram's algorithm "
            f"rewards for reels — longer watch time means more distribution. "
            f"Across all {len(reels)} reels the median is {reels['avg_watch_time_sec'].median():.1f}s."))

    # 6b. reach vs share rate scatter (Tableau Sheet3)
    P.append(section(
        "8 · Which individual posts actually worked",
        tableau("Sheet3", 560),
        "<b>Each dot is one post.</b> Across = how many people it reached; up = how often "
        "it got shared per 1,000 reached. Top-right are your winners. <b>Top-left is the "
        "interesting corner</b>: strong content that didn't get distribution — worth "
        "reposting or boosting. Hover a dot to see which post it was.",
        rec="Find your top-left dots and repost that content at a stronger time slot — "
            "it already proved people want to share it, it just didn't get seen."))

    # 6c. ER diagnostic (Tableau Sheet6)
    P.append(section(
        "9 · Engagement rate by format (diagnostic)",
        tableau("Sheet6", 500),
        "<b>Read this one carefully.</b> Engagement rate is interactions divided by reach, "
        "so it <i>falls</i> as reach grows — a post that escapes your follower bubble "
        "reaches people who scroll past, which lowers the percentage. A lower rate on a "
        "high-reach post is not a failure.",
        rec="Use this to judge whether the people who saw a post cared — not whether it "
            "grew you. For growth, look at share rate at the top of this page."))

    # 8. demographics
    dpath = CSV / "audience_demographics.csv"
    if dpath.exists():
        dg = pd.read_csv(dpath)
        dg["follower_count"] = pd.to_numeric(dg["follower_count"], errors="coerce")
        latest = dg[dg["pull_date"] == dg["pull_date"].max()]
        blocks = []
        for bd, title in [("age", "Age"), ("gender", "Gender"), ("city", "Top cities")]:
            sub = latest[latest["breakdown"] == bd].nlargest(6, "follower_count")
            if not len(sub):
                continue
            blocks.append(f"<h2 style='font-size:1rem;margin-top:24px'>{title}</h2>"
                          f"<div class='card'>" +
                          bar_chart(list(sub["segment"].astype(str)),
                                    list(sub["follower_count"]),
                                    [C["accent"]] * len(sub), w=680, h=210) + "</div>")
        if blocks:
            P.append("<h2>10 · Who follows us</h2>" + "".join(blocks) +
                     "<p class='means'><b>Follower counts by segment.</b> Use this to sanity-check "
                     "who you're actually talking to — if your content targets a group that "
                     "barely appears here, that's a gap worth closing.</p>")

    P.append(f'<a class="explore" href="{TABLEAU_HOME}" target="_blank" rel="noopener">Explore the full data in Tableau →</a>')
    P.append(f"<footer>Generated automatically from the Instagram API · "
             f"data through {newest:%B %d, %Y} · page built {today:%B %d, %Y}. "
             f"No manual steps — this refreshes every week.</footer></div>")

    # Full document. charset MUST come first or every '·' and '–' renders as
    # mojibake; viewport is required or the page is unusable on phones.
    return ("<!doctype html><html lang=\"en\"><head>"
            "<meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>INIT FIU · Instagram performance</title>"
            f"<style>{CSS}</style></head><body>" + "".join(P) + "</body></html>")


def main():
    m = load()
    (OUT / "index.html").write_text(build(m), encoding="utf-8")
    print(f"✅ site/index.html written — {len(m)} posts, "
          f"newest {m['d'].max().date()}")


if __name__ == "__main__":
    main()
