#!/usr/bin/env python3
"""
Lightweight daily pull: stories + account insights only.

Why this exists separately from instagram_pull.py:
  - Stories expire after ~24h and the API only returns ACTIVE ones, so a weekly
    job misses six days out of seven. Running daily catches nearly all of them.
  - Account insights are a daily-grain metric (followers, reach split by
    follower/non-follower). Weekly sampling gives one point a week; daily gives
    a real trend line.

It deliberately skips the 350-post media pull, which is slow (~700 API calls)
and only needs to run weekly. Takes about 20 seconds.

Run:  python3 daily_pull.py
"""
from instagram_pull import (get_account, pull_account_insights, pull_stories,
                            CSV_DIR, fail)


def main():
    try:
        uid, profile = get_account()
    except Exception as e:
        fail(f"Auth failed: {e}")
    print(f"Daily pull — @{profile.get('username')} "
          f"({profile.get('followers_count')} followers)")
    pull_account_insights(uid, profile)
    pull_stories(uid)
    print(f"✅ Daily pull done. CSVs in {CSV_DIR}")


if __name__ == "__main__":
    main()
