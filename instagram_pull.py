#!/usr/bin/env python3
"""
Instagram API (with Instagram Login) -> master CSV puller (for Tableau).

Uses graph.instagram.com (Instagram Login path) — logs in directly as the
Instagram professional account, no Facebook Page / Business portfolio needed.

Maintains append/upsert "master" CSV files in ./csv:
  - account_insights.csv      (one row per day; deduped by date)
  - media_performance.csv     (one row per post/reel; upserted by media id)
  - stories.csv               (one row per active story; upserted by story id)
  - audience_demographics.csv (one snapshot per pull date + breakdown)

Run:  python3 instagram_pull.py
Config comes from the .env file next to this script.
"""

import os
import sys
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import pandas as pd
from dotenv import load_dotenv

EST = ZoneInfo("America/New_York")  # publish-time analysis is done in Eastern time

# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
CSV_DIR = HERE / "csv"
CSV_DIR.mkdir(exist_ok=True)
load_dotenv(HERE / ".env")

ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip()
API_VERSION = os.getenv("GRAPH_API_VERSION", "v23.0").strip()
BASE = f"https://graph.instagram.com/{API_VERSION}"

# History depth for the media pull:
#   IG_MEDIA_SINCE — only pull posts published on/after this YYYY-MM-DD (newest-first,
#                    stops once it reaches older posts). Blank = ignore date.
#   IG_MEDIA_LIMIT — hard cap on number of posts.
MEDIA_SINCE = os.getenv("IG_MEDIA_SINCE", "").strip()
MEDIA_LIMIT = int(os.getenv("IG_MEDIA_LIMIT", "200"))

TODAY = dt.date.today().isoformat()
NOW = dt.datetime.now().isoformat(timespec="seconds")


def fail(msg: str):
    print(f"\n❌ {msg}", file=sys.stderr)
    sys.exit(1)


if not ACCESS_TOKEN:
    fail("Missing IG_ACCESS_TOKEN. Fill in the .env file.")


# --------------------------------------------------------------------------- #
def api_get(path: str, params: dict | None = None) -> dict:
    params = dict(params or {})
    params["access_token"] = ACCESS_TOKEN
    url = f"{BASE}/{path.lstrip('/')}"
    r = requests.get(url, params=params, timeout=60)
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except Exception:
            msg = r.text
        raise RuntimeError(f"API {r.status_code} on /{path}: {msg}")
    return r.json()


def paged(path: str, params: dict | None = None, max_pages: int = 50):
    params = dict(params or {})
    page = 0
    while True:
        data = api_get(path, params)
        for item in data.get("data", []):
            yield item
        after = data.get("paging", {}).get("cursors", {}).get("after")
        page += 1
        if not data.get("paging", {}).get("next") or not after or page >= max_pages:
            break
        params["after"] = after


def metric_value(m: dict):
    tv = m.get("total_value", {})
    if "value" in tv:
        return tv["value"]
    if m.get("values"):
        return m["values"][-1].get("value")
    return None


def breakdown_results(resp, metric_name):
    """Return the per-dimension results list for a breakdown insight call."""
    for m in resp.get("data", []):
        if m.get("name") == metric_name:
            bds = m.get("total_value", {}).get("breakdowns", [])
            if bds:
                return bds[0].get("results", [])
    return []


def upsert_csv(filename: str, new_df: pd.DataFrame, key_cols: list[str]):
    path = CSV_DIR / filename
    if new_df.empty:
        print(f"   (no rows for {filename})")
        return
    if path.exists():
        combined = pd.concat([pd.read_csv(path), new_df], ignore_index=True)
    else:
        combined = new_df
    # Coerce key columns to str so e.g. an int media_id read from CSV matches a
    # str media_id from the API — otherwise rows duplicate on every run.
    for k in key_cols:
        combined[k] = combined[k].astype(str)
    combined = combined.drop_duplicates(subset=key_cols, keep="last")
    sort_cols = [c for c in ("date", "timestamp", "pull_date") if c in combined.columns]
    if sort_cols:
        combined = combined.sort_values(sort_cols)
    combined.to_csv(path, index=False)
    print(f"   ✅ {filename}: {len(new_df)} new/updated, {len(combined)} total rows")


# --------------------------------------------------------------------------- #
def get_account():
    """Return (user_id, profile_dict) for the logged-in Instagram account."""
    me = api_get("me", {"fields": "user_id,username,account_type,"
                                   "followers_count,follows_count,media_count"})
    uid = me.get("user_id") or me.get("id")
    return uid, me


def pull_account_insights(uid: str, profile: dict):
    print("\n[1/4] Account-level insights…")
    row = {"date": TODAY, "pull_timestamp": NOW,
           "username": profile.get("username"),
           "followers_count": profile.get("followers_count"),
           "follows_count": profile.get("follows_count"),
           "media_count": profile.get("media_count")}
    # 'day' period metrics (request individually so one bad metric doesn't sink the rest)
    for metric in ["reach", "profile_views", "website_clicks",
                   "accounts_engaged", "total_interactions", "likes",
                   "comments", "saves", "shares", "follows_and_unfollows"]:
        try:
            resp = api_get(f"{uid}/insights",
                           {"metric": metric, "period": "day",
                            "metric_type": "total_value"})
            row[metric] = next((metric_value(m) for m in resp.get("data", [])), None)
        except Exception as e:
            row[metric] = None
            print(f"   ⚠️  {metric}: {e}")
    # Non-follower reach (account level, day): reach split by follower type.
    # Non-follower reach % = reach_non_follower / (reach_follower + reach_non_follower) * 100
    try:
        rb = api_get(f"{uid}/insights", {"metric": "reach", "period": "day",
                                         "metric_type": "total_value",
                                         "breakdown": "follow_type"})
        for entry in breakdown_results(rb, "reach"):
            dim = (entry.get("dimension_values") or [""])[0]
            if dim == "FOLLOWER":
                row["reach_follower"] = entry.get("value")
            elif dim == "NON_FOLLOWER":
                row["reach_non_follower"] = entry.get("value")
    except Exception as e:
        print(f"   ⚠️  reach follow_type: {e}")

    upsert_csv("account_insights.csv", pd.DataFrame([row]), key_cols=["date"])


def post_type_label(media_type, product_type):
    if product_type == "REELS":
        return "IG reel"
    if media_type == "CAROUSEL_ALBUM":
        return "IG carousel"
    if media_type == "IMAGE":
        return "IG image"
    if media_type == "VIDEO":
        return "IG video"
    return media_type


def derive_post_fields(rec, followers):
    """Add the computed columns the Tableau analyses rely on."""
    rec["post_type"] = post_type_label(rec.get("media_type"), rec.get("product_type"))

    # Publish time decomposed in Eastern time (for day/hour heatmaps & monthly trends)
    ts = rec.get("timestamp")
    if ts:
        d = dt.datetime.fromisoformat(ts.replace("+0000", "+00:00")).astimezone(EST)
        rec["publish_date_est"] = d.date().isoformat()
        rec["publish_year"] = d.year
        rec["publish_month"] = d.month
        rec["publish_month_name"] = d.strftime("%B")
        rec["publish_weekday"] = d.strftime("%A")
        rec["publish_hour_est"] = d.hour
        rec["publish_time_label"] = d.strftime("%-I %p")  # e.g. "11 AM"

    # Engagement rate. Prefer total_interactions; fall back to summing components.
    reach = rec.get("reach") or 0
    inter = rec.get("total_interactions")
    if inter is None:
        inter = sum(rec.get(k) or 0 for k in ("likes", "comments", "saved", "shares"))
        rec["total_interactions"] = inter
    rec["engagement_rate"] = round(inter / reach * 100, 3) if reach else None
    rec["engagement_rate_followers"] = round(inter / followers * 100, 3) if followers else None

    # Rewatch rate (video only): plays/views relative to reach.
    views = rec.get("views")
    rec["rewatch_rate"] = round(views / reach, 3) if (views and reach) else None
    return rec


def pull_media_performance(uid: str, followers: int,
                           limit_media: int = MEDIA_LIMIT, since: str = MEDIA_SINCE):
    print("\n[2/4] Post / media performance…")
    if since:
        print(f"   (pulling posts since {since}, up to {limit_media})")
    fields = ("id,caption,media_type,media_product_type,permalink,timestamp,"
              "like_count,comments_count")
    rows, count = [], 0
    for media in paged(f"{uid}/media", {"fields": fields, "limit": 50}, max_pages=200):
        if count >= limit_media:
            break
        # Posts come newest-first; stop once we pass the 'since' cutoff date.
        ts = media.get("timestamp")
        if since and ts and ts[:10] < since:
            break
        count += 1
        rec = {
            "media_id": media.get("id"),
            "pull_date": TODAY,
            "caption": (media.get("caption") or "").replace("\n", " ").strip(),
            "media_type": media.get("media_type"),
            "product_type": media.get("media_product_type"),
            "permalink": media.get("permalink"),
            "timestamp": media.get("timestamp"),
            "like_count": media.get("like_count"),
            "comments_count": media.get("comments_count"),
        }
        if media.get("media_product_type") == "REELS":
            metrics = "reach,likes,comments,saved,shares,total_interactions,views"
        else:
            metrics = "reach,likes,comments,saved,shares,total_interactions,profile_visits,views"
        try:
            ins = api_get(f"{media['id']}/insights", {"metric": metrics})
            for m in ins.get("data", []):
                rec[m.get("name")] = metric_value(m)
        except Exception as e:
            print(f"   ⚠️  insights for {media.get('id')}: {e}")
        # 'follows' (new followers from this post) is only supported for some media
        # types (not Reels) — fetch separately so it can't drop the core metrics.
        try:
            fol = api_get(f"{media['id']}/insights", {"metric": "follows"})
            for m in fol.get("data", []):
                rec[m.get("name")] = metric_value(m)
        except Exception:
            pass
        # Reel watch time (ms -> sec). Completion rate = avg_watch_time_sec / video
        # length; video length isn't exposed by the API (it's in your export's
        # "Duration (sec)" column), so pair these with that for completion.
        if media.get("media_product_type") == "REELS":
            try:
                w = api_get(f"{media['id']}/insights",
                            {"metric": "ig_reels_avg_watch_time,ig_reels_video_view_total_time"})
                for m in w.get("data", []):
                    v = metric_value(m)
                    if v is None:
                        continue
                    if m.get("name") == "ig_reels_avg_watch_time":
                        rec["avg_watch_time_sec"] = round(v / 1000, 2)
                    elif m.get("name") == "ig_reels_video_view_total_time":
                        rec["total_watch_time_sec"] = round(v / 1000, 2)
            except Exception:
                pass
        derive_post_fields(rec, followers)
        rows.append(rec)
    n_follows = sum(1 for r in rows if r.get("follows") is not None)
    print(f"   pulled {len(rows)} media items ({n_follows} with per-post follows)")
    upsert_csv("media_performance.csv", pd.DataFrame(rows), key_cols=["media_id"])


def pull_stories(uid: str):
    print("\n[3/4] Stories (active only)…")
    rows = []
    try:
        stories = list(paged(f"{uid}/stories",
                             {"fields": "id,media_type,permalink,timestamp"}))
    except Exception as e:
        print(f"   ⚠️  stories list: {e}")
        stories = []
    for s in stories:
        rec = {"story_id": s.get("id"), "pull_date": TODAY,
               "media_type": s.get("media_type"), "permalink": s.get("permalink"),
               "timestamp": s.get("timestamp")}
        try:
            # Everything the story endpoint actually supports (verified against
            # the API). Sticker-level data — poll votes, quiz answers, question
            # replies — is NOT exposed; total_interactions is the only signal
            # that captures likes and sticker taps, so we derive those below.
            ins = api_get(f"{s['id']}/insights",
                          {"metric": "reach,replies,shares,follows,profile_visits,"
                                     "profile_activity,total_interactions,navigation"})
            for m in ins.get("data", []):
                rec[m.get("name")] = metric_value(m)
        except Exception as e:
            print(f"   ⚠️  story insights {s.get('id')}: {e}")
        # Navigation breakdown (tap_forward, tap_back, tap_exit, swipe_forward...)
        # -> story completion ≈ 1 - tap_exit / reach.
        try:
            nav = api_get(f"{s['id']}/insights",
                          {"metric": "navigation",
                           "breakdown": "story_navigation_action_type"})
            for entry in breakdown_results(nav, "navigation"):
                dim = (entry.get("dimension_values") or [""])[0]
                if dim:
                    rec[f"nav_{dim}"] = entry.get("value")
        except Exception:
            pass
        rows.append(rec)
    print(f"   pulled {len(rows)} active stories")
    upsert_csv("stories.csv", pd.DataFrame(rows), key_cols=["story_id"])


def pull_demographics(uid: str):
    print("\n[4/4] Audience demographics…")
    rows = []
    for breakdown in ("age", "gender", "city", "country"):
        try:
            resp = api_get(f"{uid}/insights", {
                "metric": "follower_demographics",
                "period": "lifetime",
                "metric_type": "total_value",
                "timeframe": "last_30_days",
                "breakdown": breakdown,
            })
            for m in resp.get("data", []):
                results = (m.get("total_value", {})
                            .get("breakdowns", [{}])[0].get("results", []))
                for entry in results:
                    dims = entry.get("dimension_values", [])
                    rows.append({"pull_date": TODAY, "breakdown": breakdown,
                                 "segment": dims[0] if dims else None,
                                 "follower_count": entry.get("value")})
        except Exception as e:
            print(f"   ⚠️  demographics ({breakdown}): {e}")
    print(f"   pulled {len(rows)} demographic segments")
    upsert_csv("audience_demographics.csv", pd.DataFrame(rows),
               key_cols=["pull_date", "breakdown", "segment"])


# --------------------------------------------------------------------------- #
def main():
    print(f"Instagram pull — {NOW}  |  API {API_VERSION}")
    try:
        uid, profile = get_account()
    except Exception as e:
        fail(f"Auth/connection check failed: {e}")
    print(f"Authenticated as @{profile.get('username')} "
          f"(id {uid}, {profile.get('followers_count')} followers)")

    followers = profile.get("followers_count") or 0
    pull_account_insights(uid, profile)
    pull_media_performance(uid, followers)
    pull_stories(uid)
    pull_demographics(uid)
    print(f"\n✅ Done. Master CSVs are in: {CSV_DIR}")


if __name__ == "__main__":
    main()
