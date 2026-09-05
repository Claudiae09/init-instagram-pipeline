# Tableau build guide — 10 decision charts

Data source: the **`media_performance`** tab of the `INIT Instagram Data` Google Sheet
(except chart 10, which uses `audience_demographics`).

## One-time setup

### 1. Fix field types
Google Sheets imports every column as text. In the Data pane, click each field's
`Abc` icon and set:

- **Number (decimal)**: Reach, Shares, Saved, Likes, Comments, Total Interactions,
  Views, Follows, Profile Visits, Avg Watch Time Sec, Engagement Rate, Publish Hour Est
- **Date**: Publish Date Est

Then right-click each numeric field → **Convert to Measure**.

### 2. Calculated fields (Analysis → Create Calculated Field)
| Name | Formula |
|------|---------|
| `Share Rate per 1k` | `SUM([Shares]) / SUM([Reach]) * 1000` |
| `Saves per 1k` | `SUM([Saved]) / SUM([Reach]) * 1000` |
| `ER by Reach` | `SUM([Total Interactions]) / SUM([Reach]) * 100` |

Use SUM/SUM, not AVG of a per-post rate — averaging rates lets tiny-reach posts
distort the result.

## The charts

| # | Chart | Columns | Rows | Marks / extras |
|---|-------|---------|------|----------------|
| 1 | Share rate by post type (**primary decision chart**) | Post Type | Share Rate per 1k | bar, sort desc |
| 2 | Reach trend by month | Publish Date Est → Month (continuous) | Reach → **Median** | line |
| 3 | Reach vs share rate | SUM(Reach) | Share Rate per 1k | Detail: Media Id · Color: Post Type · Tooltip: Caption, Permalink |
| 4 | Post volume vs avg ER by month | Publish Date Est → Month | CNT(Media Id) + ER by Reach | **Dual axis**, un-synchronize; bars + line |
| 5 | Weekday × hour heatmap | Publish Hour Est (discrete) | Publish Weekday | Marks **Square**, Color: AVG(Reach); sort weekday manually Mon→Sun |
| 6 | ER by post type (label sheet "ER (diagnostic)") | Post Type | ER by Reach | bar |
| 7 | Saves + shares per 1k | Post Type | Saves per 1k **and** Share Rate per 1k | two row pills = side-by-side panes |
| 8 | Top / bottom 15 posts | — | Caption, Post Type, Permalink | Measure Values: Reach, Share Rate per 1k, ER by Reach; Filter → Top 15 by Share Rate per 1k; add URL action on Permalink |
| 9 | Reel watch time vs ER | AVG(Avg Watch Time Sec) | ER by Reach | Filter Post Type = IG reel; Detail: Media Id |
| 10 | Audience demographics | Segment | SUM(Follower Count) | **uses `audience_demographics` tab**; filter Breakdown = age/gender/city/country |

### URL action for chart 8
Worksheet → **Actions** → **Add Action** → **Go to URL** → URL: `<Permalink>` →
Run action on: **Select**. Clicking a row opens that Instagram post.

## Notes / caveats
- **Chart 5 (heatmap)** has complete data — no caveats.
- **Chart 6 (ER)** is a diagnostic, not a KPI — ER by reach moves with reach, so a
  post that escapes your follower bubble can show *lower* ER while performing better.
  That is why share rate is the primary chart.
- **Chart 9** only has data for reels (watch time is reels-only in the API).
- **Follows per post** is unavailable for reels (API limitation), so any
  follows-based view is partial for that format.

## Publishing
File → **Save to Tableau Public** once. After that Tableau Public re-reads the
Google Sheet on its own (~daily), so the weekly pipeline updates flow through
without republishing. Re-publish only when you change the design.
