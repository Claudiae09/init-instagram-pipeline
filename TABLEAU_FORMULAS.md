# Tableau Calculated Fields — Growth Metrics

Create each via **Analysis → Create Calculated Field**, paste the formula, name it.
`FLOAT(...)` converts the (text-imported) Google-Sheets fields to numbers inline,
so these work even if you haven't changed the field types.

## On the `media_performance` data source
| Name | Formula |
|------|---------|
| Eng Rate by Reach | `FLOAT([Total Interactions]) / FLOAT([Reach]) * 100` |
| Save Rate % | `FLOAT([Saved]) / FLOAT([Reach]) * 100` |
| Share Rate % | `FLOAT([Shares]) / FLOAT([Reach]) * 100` |
| Visit-to-Follow % | `FLOAT([Follows]) / FLOAT([Profile Visits]) * 100` |
| Follows (num) | `FLOAT([Follows])` |
| Avg Watch Time (s) | `FLOAT([Avg Watch Time Sec])` |
| Total Watch Time (s) | `FLOAT([Total Watch Time Sec])` |

## On the `account_insights` data source
| Name | Formula |
|------|---------|
| Non-follower Reach % | `FLOAT([Reach Non Follower]) / (FLOAT([Reach Follower]) + FLOAT([Reach Non Follower])) * 100` |
| Net Follower Growth % | `(FLOAT([Followers Count]) - LOOKUP(FLOAT([Followers Count]),-1)) / LOOKUP(FLOAT([Followers Count]),-1) * 100` (table calc; sort by date; compute along Date) |

## On the `stories` data source (populates when a Story is live)
| Name | Formula |
|------|---------|
| Story Completion % | `(1 - FLOAT([Nav Tap Exit]) / FLOAT([Reach])) * 100` |
| Sticker Interactions | not exposed by the Instagram API (app-only) |

## Reel completion rate (cross-tab)
Watch time is in `media_performance` (`Avg Watch Time Sec`); video length is in
`instagram_export` (`Duration (sec)`). Completion = avg watch time / duration * 100.
Either compute on the export tab, or ask to add a `duration_sec` column to
`media_performance` so it's all in one place.

## Notes
- The pipeline pulls everything Instagram's API exposes. Not available via API:
  shares split DM-vs-Story, per-post follows on Reels, sticker-level interactions.
- These fields grow weekly automatically (Mon 9 AM job). account_insights and
  stories build history over time, so Non-follower Reach %, Net Follower Growth,
  and Story Completion get richer each week.
