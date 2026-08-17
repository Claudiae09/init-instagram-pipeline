# Instagram → Master CSV → Tableau

Pulls @init.fiu Instagram analytics (via the Instagram-Login API) into master CSV
files that Tableau connects to. Re-running keeps the masters current — account
insights append per day, posts/stories upsert by id, demographics snapshot per day.

## Files produced (in `./csv`)
| File | Grain | Notes |
|------|-------|-------|
| `account_insights.csv` | one row / day | reach, profile_views, website_clicks, interactions, likes, comments, saves, shares, followers/follows/media counts |
| `media_performance.csv` | one row / post | likes, comments, saves, shares, reach, interactions, Reels views, profile visits + caption/permalink |
| `stories.csv` | one row / active story | reach, replies, shares, navigation (only while live ~24h) |
| `audience_demographics.csv` | snapshot / day / segment | follower breakdown by age, gender, city, country |

## Scripts
- `instagram_pull.py` — pull all four datasets into the CSVs.
- `refresh_token.py` — extend the 60-day token (writes new token back to `.env`).
- `run_pull.sh` — refresh token + pull, logging to `run.log` (used by the scheduler).

## Setup
1. Credentials already in `.env` (token + Instagram app secret). Never commit it.
2. Deps installed in `./venv`. To reinstall: `./venv/bin/pip install -r requirements.txt`
3. Manual run: `./venv/bin/python instagram_pull.py`

## Automatic weekly run
Scheduled via macOS launchd: **Mondays 9:00 AM**.
- Definition: `~/Library/LaunchAgents/com.initfiu.instagrampull.plist`
- Runs `run_pull.sh`; output in `run.log`, `launchd.out.log`, `launchd.err.log`.
- Runs at next wake if the Mac was asleep at 9 AM Monday.
- Change schedule: edit the plist's `StartCalendarInterval`, then
  `launchctl unload <plist> && launchctl load <plist>`.
- Disable: `launchctl unload ~/Library/LaunchAgents/com.initfiu.instagrampull.plist`

## Connect Tableau
Tableau Desktop → Connect → **Text file** → pick a CSV in `./csv`.
Re-running the script (or the weekly job) refreshes these files; in Tableau,
refresh the extract/data source to pull the latest.

## Notes
- @init.fiu is a Business account; token has `instagram_business_manage_insights`.
- Account `day` metrics reflect the current day only; weekly runs capture a weekly snapshot.
- Media pull capped at 200 most-recent posts (of ~2,482). Raise `limit_media` in
  `instagram_pull.py` for more history.
- Stories disappear after ~24h — only active ones are captured at run time.
