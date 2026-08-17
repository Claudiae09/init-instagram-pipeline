#!/usr/bin/env python3
"""
Push the master CSVs to a Google Sheet (one tab per file) so Tableau Public
can auto-refresh from it.

Requires (in .env):
  GSHEET_ID       — the spreadsheet id (from its URL: /spreadsheets/d/<THIS>/edit)
  GOOGLE_SA_KEY   — path to the service-account JSON key (default: service_account.json)

The service account email (found inside the JSON, "client_email") must be added
as an Editor on the Google Sheet.

Run:  python3 push_to_sheets.py   (also called automatically by run_pull.sh)
"""
import os
import math
from pathlib import Path

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Columns kept as text so big numeric ids don't lose precision / become numbers.
TEXT_ID_COLS = ("media_id", "story_id", "Post ID", "Account ID")


def load_credentials():
    """Google creds from either a local key file or the GOOGLE_SA_JSON env var.

    Locally we read service_account.json; in CI (GitHub Actions) the same JSON is
    supplied as a secret in GOOGLE_SA_JSON, so there is no file on disk.
    """
    import json
    raw = os.getenv("GOOGLE_SA_JSON", "").strip()
    if raw:
        return Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    key_path = (HERE / SA_KEY) if not os.path.isabs(SA_KEY) else Path(SA_KEY)
    if not key_path.exists():
        raise SystemExit(f"No GOOGLE_SA_JSON env var and key file not found: {key_path}")
    return Credentials.from_service_account_file(str(key_path), scopes=SCOPES)


def to_cell(v):
    """Numpy/NaN-safe cell value: numbers stay numbers, NaN -> blank."""
    if v is None:
        return ""
    if hasattr(v, "item"):           # numpy scalar -> native python
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        return ""
    return v

HERE = Path(__file__).resolve().parent
CSV_DIR = HERE / "csv"
load_dotenv(HERE / ".env")

GSHEET_ID = os.getenv("GSHEET_ID", "").strip()
SA_KEY = os.getenv("GOOGLE_SA_KEY", "service_account.json").strip()
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# CSV file -> worksheet/tab name
TABS = {
    "instagram_export.csv": "instagram_export",   # mirrors Instagram's export schema
    "media_performance.csv": "media_performance",
    "account_insights.csv": "account_insights",
    "audience_demographics.csv": "audience_demographics",
    "stories.csv": "stories",
}


def main():
    if not GSHEET_ID:
        raise SystemExit("Set GSHEET_ID in .env (the spreadsheet id from its URL).")
    creds = load_credentials()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GSHEET_ID)

    for filename, tab in TABS.items():
        path = CSV_DIR / filename
        if not path.exists():
            print(f"   skip {filename} (no file yet)")
            continue
        df = pd.read_csv(path)
        # Keep id columns as text (full precision); other columns keep native
        # numeric types so Tableau reads them as measures, not text.
        for idc in TEXT_ID_COLS:
            if idc in df.columns:
                df[idc] = df[idc].astype(str)
        header = df.columns.tolist()
        rows = [[to_cell(v) for v in row]
                for row in df.itertuples(index=False, name=None)]
        values = [header] + rows
        try:
            ws = sh.worksheet(tab)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=tab, rows=max(len(values) + 10, 100),
                                  cols=max(len(df.columns) + 2, 26))
        ws.update(values, value_input_option="RAW")
        print(f"   ✅ {tab}: {len(df)} rows pushed")

    print("✅ Google Sheet updated.")


if __name__ == "__main__":
    main()
