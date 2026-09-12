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
import datetime as dt
import html as _html
import json
import re
import sys
import zipfile
from pathlib import Path

# The export picker offers JSON or HTML and defaults to HTML, so both shapes
# have to be read. In HTML each account is one anchor to its profile.
# followers_1.html links straight at the profile; following.html uses the
# /_u/ deep-link form. Both appear, so both are matched.
_PROFILE_URL = re.compile(
    r'instagram\.com/(?:_u/)?([A-Za-z0-9._]+)/?$', re.I)
_PROFILE = re.compile(
    r'href="https://(?:www\.)?instagram\.com/(?:_u/)?([A-Za-z0-9._]+)/?"', re.I)


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
    # The two files disagree on where the username lives. followers_1.json
    # puts it in string_list_data[].value; following.json omits value entirely
    # and carries it in the entry's title, with the href in /_u/ form. Read
    # all three so neither file silently yields nothing.
    out = {}
    for entry in blob or []:
        entry = entry or {}
        got = None
        for item in entry.get("string_list_data", []):
            if item.get("value"):
                got = item["value"]
                break
            m = _PROFILE_URL.search(item.get("href", "") or "")
            if m:
                got = m.group(1)
                break
        if not got and entry.get("title"):
            got = entry["title"]
        if got:
            ts = next((i.get("timestamp") for i in entry.get("string_list_data", [])
                       if i.get("timestamp")), None)
            out[got.strip().lower()] = ts
    return out


def _names_html(text):
    """Usernames out of an HTML export. Anchors in the page header point at
    Instagram's help pages rather than profiles, so matching the profile URL
    shape is enough to keep them out."""
    body = text.split("<main", 1)[-1]          # skip the header block
    return {_html.unescape(u).strip().lower(): None for u in _PROFILE.findall(body)}


def _parse(name, data):
    """Dispatch on extension; returns a set of usernames."""
    if name.endswith(".json"):
        return _names(json.loads(data))
    return _names_html(data.decode("utf-8", "replace")
                       if isinstance(data, bytes) else data)


def _load(src: Path):
    """Read followers and following out of a ZIP or an unzipped folder."""
    followers, following = {}, {}
    if src.is_file() and src.suffix == ".zip":
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                base = Path(n).name.lower()
                if not base.endswith((".json", ".html")):
                    continue
                if base.startswith("followers"):
                    followers.update(_parse(base, z.read(n)))
                elif base.startswith("following"):
                    following.update(_parse(base, z.read(n)))
    else:
        for f in src.rglob("*"):
            base = f.name.lower()
            if not base.endswith((".json", ".html")):
                continue
            if base.startswith("followers"):
                followers.update(_parse(base, f.read_bytes()))
            elif base.startswith("following"):
                following.update(_parse(base, f.read_bytes()))
    return followers, following


def _when(ts):
    """Unix timestamp to a plain date, or blank when the export omits one."""
    if not ts:
        return ""
    return dt.datetime.fromtimestamp(int(ts)).strftime("%d %b %Y")


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python follow_diff.py <export.zip | export folder>")
    src = Path(sys.argv[1]).expanduser()
    if not src.exists():
        sys.exit(f"not found: {src}")

    followers, following = _load(src)
    if not followers and not following:
        sys.exit("No followers/following files found. Did the export include "
                 "'Followers and Following'?")

    fset, gset = set(followers), set(following)
    # Oldest first: an account you followed two years ago and that still has
    # not followed back is a safer unfollow than one from last week.
    def by_age(names, src):
        return sorted(names, key=lambda u: (src.get(u) or 0))
    not_back = by_age(gset - fset, following)
    not_followed = by_age(fset - gset, followers)
    mutual = fset & gset

    print(f"followers        {len(followers):,}")
    print(f"following        {len(following):,}")
    print(f"mutual           {len(mutual):,}")
    print(f"\nyou follow, they don't follow back   {len(not_back):,}")
    print(f"they follow, you don't follow back   {len(not_followed):,}")

    out = Path("csv/follow_gap.csv")
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["username", "relationship", "since", "profile"])
        for u in not_back:
            w.writerow([u, "you follow, no follow back", _when(following.get(u)),
                        f"https://www.instagram.com/{u}/"])
        for u in not_followed:
            w.writerow([u, "follows you, you don't follow back",
                        _when(followers.get(u)), f"https://www.instagram.com/{u}/"])
    print(f"\nwritten to {out}  ({len(not_back) + len(not_followed):,} rows)")
    if not_back:
        print("\nlongest-standing 15 you follow who don't follow back:")
        for u in not_back[:15]:
            print(f"   @{u:28} since {_when(following.get(u)) or '?'}")


if __name__ == "__main__":
    main()
