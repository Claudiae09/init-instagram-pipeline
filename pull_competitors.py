#!/usr/bin/env python3
"""
Sync the Competitors tab of the Google Sheet into csv/competitors.csv.

Runs before the page is rendered. It also does the two things that make the
weekly habit as small as possible:

  1. creates the tab, with the handles in the header row, if it is missing
  2. stamps a fresh dated row each week with our own follower count filled in,
     so a person only has to type the competitors' numbers

The sheet is the source of truth for which accounts are tracked: edit the header
row to add or rename one, no code change needed.
"""
import datetime as dt
import os
import sys

import pandas as pd

from push_to_sheets import load_credentials

TAB = "Competitors"
SEED_HANDLES = ["init.fiu", "knighthacks", "ufswamphacks",
                "codecrunchworldwide", "hackabull", "fiu_cec", "alpfafiu"]
CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "csv",
                   "competitors.csv")


def _our_followers():
    try:
        from instagram_pull import get_account
        _uid, profile = get_account()
        return profile.get("followers_count")
    except Exception as e:
        print(f"  (could not read our own follower count: {e})")
        return None


def main():
    sheet_id = os.getenv("GSHEET_ID", "").strip()
    if not sheet_id:
        print("GSHEET_ID not set; leaving competitors.csv untouched.")
        return
    import gspread
    gc = gspread.authorize(load_credentials())
    sh = gc.open_by_key(sheet_id)

    try:
        ws = sh.worksheet(TAB)
        created = False
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=TAB, rows=200, cols=len(SEED_HANDLES) + 2)
        ws.update([["date"] + SEED_HANDLES], "A1")
        created = True
        print(f"  created the {TAB} tab with {len(SEED_HANDLES)} handles")

    values = ws.get_all_values()
    header = [h.strip() for h in values[0]] if values else []
    if not header or header[0].lower() != "date":
        print(f"  {TAB} tab has no 'date' header; skipping.")
        return
    rows = [r for r in values[1:] if any(c.strip() for c in r)]

    # one row per week: add today's if the newest is a week old or older
    today = dt.date.today()
    newest = None
    for r in rows:
        try:
            newest = max(newest or dt.date.min,
                         dt.date.fromisoformat(r[0].strip()[:10]))
        except Exception:
            continue
    if created or newest is None or (today - newest).days >= 7:
        line = [today.isoformat()] + [""] * (len(header) - 1
                                             )
        ours = _our_followers()
        if ours and "init.fiu" in header:
            line[header.index("init.fiu")] = str(ours)
        ws.append_row(line, value_input_option="USER_ENTERED")
        rows.append(line)
        print(f"  added a row for {today} (our count pre-filled)")
    else:
        print(f"  newest row is {newest}; no new row needed yet")

    df = pd.DataFrame(rows, columns=header)
    os.makedirs(os.path.dirname(CSV), exist_ok=True)
    df.to_csv(CSV, index=False)
    filled = sum(1 for _, r in df.iloc[-1:].iterrows()
                 for c in header[1:] if str(r[c]).strip())
    print(f"✅ {TAB}: {len(df)} rows, {len(header) - 1} accounts, "
          f"{filled} filled in the latest row")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # never let this stop the weekly run
        print(f"competitor sync failed: {e}", file=sys.stderr)
