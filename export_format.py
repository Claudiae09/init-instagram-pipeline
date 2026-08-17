#!/usr/bin/env python3
"""
Build a table that mirrors Instagram's official "Content" export schema, so
existing Tableau workbooks built on that export work unchanged.

Data sources, combined and deduped on Post ID:
  - 2024 and earlier  -> your original Instagram export files in ./seed
                         (captured when posts were fresh = accurate reach).
  - 2025 onward        -> live API pull (media_performance.csv), which the
                         weekly job keeps current.

The live API returns degraded reach for very old (2024) posts, so we prefer the
static seed for that period and live data for everything recent.

Output: csv/instagram_export.csv with the exact export columns/order.
Run:  python3 export_format.py   (also called by run_pull.sh)
"""
import datetime as dt
import glob
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

HERE = Path(__file__).resolve().parent
CSV_DIR = HERE / "csv"
SEED_DIR = HERE / "seed"
EST = ZoneInfo("America/New_York")

LIVE_FROM_YEAR = 2025          # live API used for this year and later
ACCOUNT_ID = "17841406860905948"
ACCOUNT_USERNAME = "init.fiu"
ACCOUNT_NAME = "INIT FIU"

EXPORT_COLUMNS = [
    "Post ID", "Account ID", "Account username", "Account name", "Description",
    "Duration (sec)", "Publish time", "Permalink", "Post type", "Data comment",
    "Date", "Views", "Reach", "Likes", "Shares", "Follows", "Comments", "Saves",
]


def fmt_publish_time(ts):
    if not isinstance(ts, str) or not ts:
        return ""
    d = dt.datetime.fromisoformat(ts.replace("+0000", "+00:00")).astimezone(EST)
    return d.strftime("%m/%d/%Y %H:%M")


def num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return 0
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return 0


def year_of(publish_time):
    # 'MM/DD/YYYY HH:MM' -> int year
    try:
        return int(str(publish_time)[6:10])
    except (ValueError, TypeError):
        return 0


def build_live():
    """Live API media -> export schema (kept for LIVE_FROM_YEAR and later)."""
    src = CSV_DIR / "media_performance.csv"
    if not src.exists():
        return pd.DataFrame(columns=EXPORT_COLUMNS)
    df = pd.read_csv(src, dtype={"media_id": str})
    out = pd.DataFrame()
    out["Post ID"] = df["media_id"].astype(str)
    out["Account ID"] = ACCOUNT_ID
    out["Account username"] = ACCOUNT_USERNAME
    out["Account name"] = ACCOUNT_NAME
    out["Description"] = df.get("caption", "").fillna("")
    out["Duration (sec)"] = 0
    out["Publish time"] = df["timestamp"].apply(fmt_publish_time)
    out["Permalink"] = df.get("permalink", "").fillna("")
    out["Post type"] = df["post_type"]
    out["Data comment"] = ""
    out["Date"] = "Lifetime"
    out["Views"] = df.get("views").apply(num) if "views" in df else 0
    out["Reach"] = df.get("reach").apply(num) if "reach" in df else 0
    likes = df["likes"] if "likes" in df else df.get("like_count")
    comments = df["comments"] if "comments" in df else df.get("comments_count")
    out["Likes"] = likes.apply(num)
    out["Shares"] = df.get("shares").apply(num) if "shares" in df else 0
    out["Follows"] = df.get("follows").apply(num) if "follows" in df else 0
    out["Comments"] = comments.apply(num)
    out["Saves"] = df.get("saved").apply(num) if "saved" in df else 0
    out = out[EXPORT_COLUMNS]
    return out[out["Publish time"].apply(year_of) >= LIVE_FROM_YEAR]


def load_seed():
    """Original Instagram export files -> rows before LIVE_FROM_YEAR."""
    files = glob.glob(str(SEED_DIR / "*.csv"))
    if not files:
        return pd.DataFrame(columns=EXPORT_COLUMNS)
    frames = [pd.read_csv(f, dtype=str, encoding="utf-8-sig") for f in files]
    seed = pd.concat(frames, ignore_index=True)
    seed = seed[[c for c in EXPORT_COLUMNS if c in seed.columns]]
    for c in EXPORT_COLUMNS:
        if c not in seed.columns:
            seed[c] = ""
    seed = seed[EXPORT_COLUMNS]
    seed = seed[seed["Publish time"].apply(year_of) < LIVE_FROM_YEAR]
    return seed


def main():
    live = build_live()
    seed = load_seed()
    combined = pd.concat([seed, live], ignore_index=True)
    # Prefer live on any Post ID overlap (keep='last' since live is appended last).
    combined = combined.drop_duplicates(subset="Post ID", keep="last")
    dest = CSV_DIR / "instagram_export.csv"
    combined.to_csv(dest, index=False)
    yrs = combined["Publish time"].apply(year_of)
    by_year = yrs.value_counts().sort_index().to_dict()
    print(f"✅ instagram_export.csv: {len(combined)} rows "
          f"(seed 2024-: {len(seed)}, live {LIVE_FROM_YEAR}+: {len(live)}) | by year: {by_year}")


if __name__ == "__main__":
    main()
