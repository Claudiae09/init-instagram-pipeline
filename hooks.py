#!/usr/bin/env python3
"""
Which opening lines earn shares.

The hook is the first 80 characters or so, which is roughly what a reader sees
before Instagram folds the caption. Styles are matched on that opening only:
matching the whole caption would credit a hook for words that appear four
paragraphs down.

Same guards as everywhere else on this page. A style needs enough posts behind
it, and it is marked when one post carries most of its shares.
"""
import re

import report_sections as R

HOOK_CHARS = 80
MIN_POSTS = 20          # a style needs this many posts before it is advice
SINCE_YEAR = 2025

STYLES = {
    "open with an emoji": r"^[^\w\s,.!?'\"]",
    "put a word in CAPS": r"\b[A-Z]{4,}\b",
    "announce something": r"\b(is here|is back|now open|introducing|announcing|meet)\b",
    "create urgency": r"\b(today|tonight|last chance|closes|deadline|tomorrow|final)\b",
    "ask a question": r"\?",
    "name a number": r"\d",
}
CASE_SENSITIVE = {"put a word in CAPS", "open with an emoji"}


def hook_findings(m):
    m = m[m["caption"].notna() & (m["reach"] > 0)
          & (m["d"].dt.year >= SINCE_YEAR)].copy()
    if len(m) < 40:
        return {"enough": False}
    m["hook"] = (m["caption"].astype(str).str.strip()
                 .str.replace(r"\s+", " ", regex=True).str[:HOOK_CHARS])
    # How many styles each hook matches. A hook that is emoji, caps, an
    # announcement and a number all at once illustrates none of them well.
    def _hits(h):
        return sum(bool(re.search(pat, h, 0 if n in CASE_SENSITIVE else re.I))
                   for n, pat in STYLES.items())
    m["_styles"] = m["hook"].apply(_hits)

    base = m["shares"].sum() / m["reach"].sum() * 1000
    rows = []
    for name, pat in STYLES.items():
        flags = 0 if name in CASE_SENSITIVE else re.I
        hit = m[m["hook"].apply(lambda h: bool(re.search(pat, h, flags)))]
        if len(hit) < MIN_POSTS or not hit["reach"].sum():
            continue
        tot = hit["shares"].sum()
        conc = (hit["shares"].max() / tot) if tot else 0
        rate = tot / hit["reach"].sum() * 1000
        rows.append({"style": name, "posts": len(hit), "rate": rate,
                     "vs_avg": R.pct_change(base, rate),
                     "skewed": conc > R.MAX_POST_CONCENTRATION,
                     "example": _example(hit)})
    if not rows:
        return {"enough": False}
    rows.sort(key=lambda r: -r["rate"])
    return {"enough": True, "rows": rows, "base": base, "posts": len(m),
            "solid": [r for r in rows if not r["skewed"]]}


def _example(g):
    """The best performing hook in this style, as something to copy."""
    pool = g[g["reach"] >= 200]
    if not len(pool):
        pool = g
    # Prefer a hook that is mostly about this one style
    for limit in (1, 2, 3):
        focused = pool[pool["_styles"] <= limit]
        if len(focused) >= 3:
            pool = focused
            break
    best = pool.assign(_r=pool["shares"] / pool["reach"] * 1000) \
               .sort_values("_r", ascending=False).iloc[0]
    h = str(best["hook"]).strip()
    return {"text": h[:70] + ("…" if len(h) > 70 else ""),
            "link": best.get("permalink") or ""}


def hook_recommendations(hf):
    if not hf.get("enough"):
        return ["Not enough captions yet to tell which openings work."]
    solid = hf.get("solid") or hf["rows"]
    out = []
    best = solid[0]
    out.append(f"<b>Working:</b> hooks that {best['style']} earn "
               f"{best['rate']:.1f} shares per 1,000, "
               f"{best['vs_avg']:+.0f}% on your average, across "
               f"{best['posts']} posts.")
    if len(solid) > 1:
        second = solid[1]
        out.append(f"<b>Also working:</b> hooks that {second['style']}, at "
                   f"{second['rate']:.1f} ({second['vs_avg']:+.0f}%).")
    flat = [r for r in solid if abs(r["vs_avg"]) < 8]
    if flat:
        names = " and ".join(r["style"] for r in flat[:2])
        out.append(f"<b>Makes no difference:</b> hooks that {names}. Common "
                   f"advice, but "
                   f"your audience does not respond to it either way.")
    out.append(f"<i>Measured on the first {HOOK_CHARS} characters, which is "
               f"roughly what shows before the caption folds.</i>")
    return out
