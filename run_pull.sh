#!/bin/bash
# Daily runner: refresh the token (keeps it alive) then pull data into the CSVs.
# Logs to run.log next to this script. Used by the scheduler (launchd/cron).

cd "$(dirname "$0")" || exit 1
PY="./venv/bin/python"

{
  echo "=================================================="
  echo "Run started: $(date)"
  # Refresh token (token must be >24h old; ignore failure if too new)
  $PY refresh_token.py 2>&1 || echo "(token refresh skipped/failed — continuing)"
  # Pull data
  $PY instagram_pull.py 2>&1
  # Build the Instagram-export-format table (for existing Tableau dashboards)
  $PY export_format.py 2>&1 || echo "(export_format build failed)"
  # Push the fresh CSVs to Google Sheets (so Tableau Public auto-refreshes)
  $PY push_to_sheets.py 2>&1 || echo "(Google Sheets push failed — CSVs still updated)"
  # Stamp freshness into the Sheet's "status" tab so staleness is visible
  $PY write_status.py 2>&1 || echo "(status stamp failed)"
  echo "Run finished: $(date)"
} >> run.log 2>&1
