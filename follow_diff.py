#!/usr/bin/env python3
"""
Compare who follows @init.fiu against who it follows.

The API cannot do this: /followers, /follows and /following are all rejected
on the Instagram Login host, which returns counts and nothing else. The only
legitimate source of the two lists is Instagram's own data export, which is
free and needs no third-party app or password.

    Profile -> Settings and Privacy -> Accounts Center
      -> Your Information and Permissions -> Export Your Information
      -> Create Export -> Export to Device
      -> Customize: tick only "Followers and Following", All Time, JSON

Then point this at the ZIP or the unzipped folder:

    python follow_diff.py ~/Downloads/instagram-export.zip
"""
import csv
import json
import sys
import zipfile
from pathlib import Path


def _names(blob):
    """Instagram nests usernames the same way in both files, but wraps the
    following list in a key and leaves the followers list bare."""
    if isinstance(blob, dict):
        for k in ("relationships_following", "relationships_followers"):
            if k in blob:
                blob = blob[k]
                break
        else:
            blob = next((v for v in blob.values() if isinstance(v, list)), [])
    out = set()
    for entry in blob or []:
        for item in (entry or {}).get("string_list_data", []):
            if item.get("value"):
                out.add(item["value"].strip().lower())
    return out


def _load(src: Path):
    """Read followers and following out of a ZIP or an unzipped folder."""
    followers, following = set(), set()
    if src.is_file() and src.suffix == ".zip":
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                base = Path(n).name.lower()
                if not base.endswith(".json"):
                    continue
                if base.startswith("followers"):
                    followers |= _names(json.loads(z.read(n)))
                elif base.startswith("following"):
                    following |= _names(json.loads(z.read(n)))
    else:
        for f in src.rglob("*.json"):
            base = f.name.lower()
            if base.startswith("followers"):
                followers |= _names(json.loads(f.read_text()))
            elif base.startswith("following"):
                following |= _names(json.loads(f.read_text()))
    return followers, following


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python follow_diff.py <export.zip | export folder>")
    src = Path(sys.argv[1]).expanduser()
    if not src.exists():
        sys.exit(f"not found: {src}")

    followers, following = _load(src)
    if not followers and not following:
        sys.exit("No followers/following JSON found. Did the export include "
                 "'Followers and Following', in JSON rather than HTML?")

    not_back = sorted(following - followers)   # you follow them, they don't follow you
    not_followed = sorted(followers - following)  # they follow you, you don't follow back
    mutual = followers & following

    print(f"followers        {len(followers):,}")
    print(f"following        {len(following):,}")
    print(f"mutual           {len(mutual):,}")
    print(f"\nyou follow, they don't follow back   {len(not_back):,}")
    print(f"they follow, you don't follow back   {len(not_followed):,}")

    out = Path("csv/follow_gap.csv")
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["username", "relationship", "profile"])
        for u in not_back:
            w.writerow([u, "you follow, no follow back",
                        f"https://www.instagram.com/{u}/"])
        for u in not_followed:
            w.writerow([u, "follows you, you don't follow back",
                        f"https://www.instagram.com/{u}/"])
    print(f"\nwritten to {out}  ({len(not_back) + len(not_followed):,} rows)")
    if not_back:
        print("\nfirst 15 who don't follow back:")
        for u in not_back[:15]:
            print(f"   @{u}")


if __name__ == "__main__":
    main()
