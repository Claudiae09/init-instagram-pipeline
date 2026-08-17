# Moving the weekly pull to GitHub Actions

Everything on this side is done and committed. These are the steps that need
your GitHub login. ~15 minutes.

## 1. Create a PRIVATE repo
github.com → **New repository** → name it e.g. `init-instagram-pipeline`
→ **Private** → do NOT add a README/gitignore (this folder already has them)
→ **Create repository**

## 2. Push this folder to it
GitHub will show you the commands; they are:

```bash
cd ~/init-instagram-pipeline
git remote add origin https://github.com/YOUR-USERNAME/init-instagram-pipeline.git
git push -u origin main
```

## 3. Create a Personal Access Token (so the workflow can store the refreshed token)
github.com → your avatar → **Settings** → **Developer settings**
→ **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
- Repository access: **Only select repositories** → pick this repo
- Permissions → Repository permissions → **Secrets: Read and write**
- Also set **Contents: Read and write** (so it can commit the CSVs back)
- Generate, then **copy the token** (shown once)

## 4. Add 5 repository secrets
In the repo → **Settings** → **Secrets and variables** → **Actions**
→ **New repository secret**, once per row:

| Secret name | Value |
|---|---|
| `IG_ACCESS_TOKEN` | the `IG_ACCESS_TOKEN=` value from your local `.env` |
| `IG_APP_SECRET` | the `IG_APP_SECRET=` value from `.env` |
| `GSHEET_ID` | `1tbzJwI_0nD9g9e9g2RM79TuOUBrzD2h5vH6iIue74BY` |
| `GOOGLE_SA_JSON` | the **entire contents** of `service_account.json` (open it, copy all) |
| `GH_PAT` | the token you just created in step 3 |

## 5. Test it
Repo → **Actions** tab → **Weekly Instagram pull** → **Run workflow** → Run.
Watch it go green. Then check the Google Sheet's `status` tab — `last_updated`
should show the current time.

## 6. Turn off the local Mac job (optional, once Actions is proven)
```bash
launchctl unload ~/Library/LaunchAgents/com.initfiu.instagrampull.plist
```
Leave it running for a week or two as a backup if you prefer — running both is
harmless (they write the same data to the same Sheet).

---

## How it behaves once live
- Runs **Mondays 13:00 UTC** (9am EDT / 8am EST — GitHub cron ignores DST)
- Also runnable on demand from the Actions tab
- If any step fails, the run shows **red** and GitHub **emails you** — so it
  cannot stall silently the way the local job did
- The refreshed Instagram token is written back to the `IG_ACCESS_TOKEN` secret
  each run, so it never expires as long as the workflow runs at least every 60 days
- Updated CSVs are committed back to the repo, preserving the append-only
  `account_insights` history across runs

## Note about the schedule
GitHub's scheduled runs can be delayed during peak load (sometimes 15–60 min).
For a weekly job that is irrelevant, but it is why the run may not start exactly
on the hour.
