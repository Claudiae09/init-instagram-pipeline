# INIT FIU · Instagram pipeline

Pulls @init.fiu Instagram analytics into master CSVs, pushes them to a Google
Sheet for Tableau, and builds a static dashboard that explains what the numbers
mean. Everything runs on GitHub Actions and deploys itself. Nothing needs a
laptop to be awake.

**Live dashboard:** <https://init-instagram.claudiae092004.workers.dev/>

---

## How it runs

Two scheduled workflows. Neither needs anything from you.

| Workflow | When | What it does |
|---|---|---|
| `daily-stories.yml` | 12:00 UTC daily | Stories + account insights, then rebuilds the page |
| `weekly-pull.yml` | 13:00 UTC Mondays | Refreshes the token, pulls all posts, rebuilds everything |

Stories need the daily run: the API only returns stories that are still live, so
a weekly job would miss six days in seven.

Each run commits the updated CSVs and `site/index.html` back to the repo, and
Cloudflare redeploys from that commit within about a minute.

**Checking a deploy landed:** the dashboard footer carries a build timestamp. If
it does not match the time of the last commit, you are looking at a cached page.

---

## The dashboard

`render.py` writes `site/index.html` — one self-contained file, no build step,
no framework. Sections, in order:

1. **When and how often to post** — best day and hour, and the weekly posting
   cadence that actually performs. Deliberately not period-scoped.
2. **By content type** — carousels / reels / graphics / stories
3. **What changed** — this period against the one before, and why
4. **What to post next** — subjects ranked by share rate, each linking to a real example
5. **Followers** — growth chart and rate
6. **Who they are** — age, location, gender
7. **How you compare** — competitor follower counts
8. The nine Tableau charts, collapsed, each with a written reading

A single period control at the top drives sections 3 through 5 and section 2.

### Analysis modules

Each returns plain data; nothing but `render.py` writes HTML.

| Module | Answers |
|---|---|
| `report_sections.py` | Period comparisons, per-content-type guidance, caption findings, weak-post diagnostics |
| `topics.py` | Which subjects earn shares, and which are being under-used |
| `timing.py` | Best day and hour, and how often to post |
| `audience.py` | Follower growth, age/location/gender |
| `competitors.py` | Where the account sits against peers |
| `chart_notes.py` | A written reading for each Tableau chart |

### Guards

Small samples caused three separate wrong recommendations during development, so
every ranking applies the same two rules, and says on the page when they fire:

- a minimum number of posts before something can be called a winner
- no single post may account for more than 45% of a group's shares

Windows that cannot be filled show a banner instead of numbers borrowed from a
shorter period. Engagement moves under 0.5 points do not carry a prescription.

---

## Data

Written to `./csv`, and mirrored to the Google Sheet as one tab per file.

| File | Grain |
|---|---|
| `account_insights.csv` | one row per day |
| `media_performance.csv` | one row per post |
| `stories.csv` | one row per story frame, collected daily |
| `audience_demographics.csv` | one snapshot per day per segment |
| `instagram_export.csv` | mirrors Instagram's own Content export schema |
| `competitors.csv` | one row per reading, entered by hand (see below) |

Tableau reads the Google Sheet, not these files, so it refreshes without anyone
republishing.

---

## What the API will not give us

Verified by testing, not assumed:

- **Competitor follower counts.** `business_discovery` is the only endpoint for
  them and it does not exist on `graph.instagram.com`. It needs Instagram API
  with *Facebook* Login, which needs admin on the Facebook Page behind the
  account. So competitor numbers are typed into the **Competitors** tab of the
  Google Sheet. The job stamps a dated row monthly with our own count
  pre-filled; a person fills in the rest. Handles live in that sheet's header
  row, so accounts can be added or renamed without touching code.
- **Trending content and hashtag search.** Same Facebook Login requirement.
- **Story sticker detail.** Poll votes, quiz answers and question replies are
  app-only. `total_interactions` minus replies and shares approximates likes and
  sticker taps, which is the closest available read.

If the org ever gets admin on that Facebook Page, competitor tracking and
hashtag trends both become automatic.

---

## Running it locally

```bash
./venv/bin/python instagram_pull.py     # full pull
./venv/bin/python daily_pull.py         # stories + account only, ~20s
./venv/bin/python render.py             # rebuild site/index.html
```

Credentials live in `.env` (never committed). Dependencies: `./venv/bin/pip
install -r requirements.txt`.

### Secrets the workflows need

`IG_ACCESS_TOKEN` · `IG_APP_SECRET` · `GSHEET_ID` · `GOOGLE_SA_JSON`

The token is long-lived and `refresh_token.py` extends it weekly, writing the new
one back to repo secrets. If a run fails on auth, that is the thing to check.

---

## Deployment

`wrangler.jsonc` serves `./site` as a Cloudflare static site. A commit that
touches `site/` triggers a redeploy. There is no build step.

---

## Housekeeping

Two things worth cleaning up:

- **A launchd agent is still loaded** on Claudia's Mac
  (`~/Library/LaunchAgents/com.initfiu.instagrampull.plist`) running
  `run_pull.sh` weekly. GitHub Actions took this over; the local job is
  redundant and pulls with the same token. Remove with:
  `launchctl unload ~/Library/LaunchAgents/com.initfiu.instagrampull.plist`
- **`generate_report.py` is dead.** `render.py` replaced it and no workflow
  references it.

Also outstanding: Tableau **Sheet1** and **Sheet6** still carry an
`Is Current Year` filter, which makes 8 image posts outrank 71 carousels. The
chart notes warn about it, but the fix is in the workbook.

---

## Notes

- @init.fiu is a Business account on the Instagram Login path
  (`graph.instagram.com`), not the Facebook Login path. That decision shapes
  everything under "What the API will not give us".
- The dashboard is public to anyone with the URL. If it should be private,
  Cloudflare Access can put an email policy in front of it.
