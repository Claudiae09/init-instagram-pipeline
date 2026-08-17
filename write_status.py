#!/usr/bin/env python3
"""
Write a freshness stamp into the Google Sheet ("status" tab) so staleness is
visible at a glance — in the Sheet and on any Tableau dashboard.

Shows when the pull last ran, the newest post captured, and row counts.
Run:  python3 write_status.py   (called by run_pull.sh after the push)
"""
import datetime as dt
from pathlib import Path

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os

HERE = Path(__file__).resolve().parent
CSV_DIR = HERE / "csv"
load_dotenv(HERE / ".env")

GSHEET_ID = os.getenv("GSHEET_ID", "").strip()
SA_KEY = os.getenv("GOOGLE_SA_KEY", "service_account.json").strip()
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def main():
    now = dt.datetime.now()
    rows = [["metric", "value"]]
    rows.append(["last_updated", now.strftime("%Y-%m-%d %H:%M:%S")])
    rows.append(["last_updated_date", now.strftime("%Y-%m-%d")])

    mp = CSV_DIR / "media_performance.csv"
    if mp.exists():
        df = pd.read_csv(mp)
        rows.append(["posts_in_media_performance", len(df)])
        if "publish_date_est" in df.columns and len(df):
            newest = df["publish_date_est"].max()
            rows.append(["newest_post_date", str(newest)])
            try:
                age = (now.date() - dt.date.fromisoformat(str(newest))).days
                rows.append(["days_since_newest_post", age])
            except ValueError:
                pass

    exp = CSV_DIR / "instagram_export.csv"
    if exp.exists():
        rows.append(["rows_in_instagram_export", len(pd.read_csv(exp))])

    # Creds from the local key file, or from GOOGLE_SA_JSON when running in CI.
    import json
    raw = os.getenv("GOOGLE_SA_JSON", "").strip()
    if raw:
        creds = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(str(HERE / SA_KEY), scopes=SCOPES)
    sh = gspread.authorize(creds).open_by_key(GSHEET_ID)
    try:
        ws = sh.worksheet("status")
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="status", rows=20, cols=4)
    ws.update(rows, value_input_option="RAW")
    print(f"✅ status tab updated — last_updated {rows[1][1]}")


if __name__ == "__main__":
    main()
