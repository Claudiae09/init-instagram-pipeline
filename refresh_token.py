#!/usr/bin/env python3
"""
Refresh the long-lived Instagram token for another ~60 days, then persist it.

Instagram-Login long-lived tokens are refreshed with grant_type=ig_refresh_token
(no app secret needed). Each refresh returns a NEW token string, so it must be
stored or the next run would keep using the old one and eventually expire.

Where the new token gets stored:
  - Locally  -> rewritten into .env
  - GitHub Actions -> written back to the repo's IG_ACCESS_TOKEN secret
    (needs GH_PAT with "Secrets: read and write" on the repo)

Run:  python3 refresh_token.py
"""
import os
import re
import base64
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
ENV = HERE / ".env"
load_dotenv(ENV)

TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("No IG_ACCESS_TOKEN set")


def save_to_env(new_token: str) -> bool:
    if not ENV.exists():
        return False
    text = ENV.read_text()
    text = re.sub(r"^IG_ACCESS_TOKEN=.*$", f"IG_ACCESS_TOKEN={new_token}",
                  text, flags=re.MULTILINE)
    ENV.write_text(text)
    return True


def save_to_github_secret(new_token: str) -> bool:
    """Update the repo's IG_ACCESS_TOKEN secret so the next CI run uses it."""
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()   # "owner/repo", set by Actions
    pat = os.getenv("GH_PAT", "").strip()
    if not (repo and pat):
        return False
    try:
        from nacl import encoding, public
    except ImportError:
        print("   ⚠️  PyNaCl not installed — cannot update GitHub secret")
        return False

    h = {"Authorization": f"Bearer {pat}",
         "Accept": "application/vnd.github+json"}
    # 1. Get the repo's public key used to encrypt secrets
    r = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
                     headers=h, timeout=30)
    if r.status_code != 200:
        print(f"   ⚠️  could not fetch repo public key: {r.status_code} {r.text[:120]}")
        return False
    pk = r.json()

    # 2. Encrypt the token with that key (libsodium sealed box)
    sealed = public.SealedBox(
        public.PublicKey(pk["key"].encode(), encoding.Base64Encoder())
    ).encrypt(new_token.encode())
    payload = {"encrypted_value": base64.b64encode(sealed).decode(),
               "key_id": pk["key_id"]}

    # 3. Store it back as the IG_ACCESS_TOKEN secret
    r = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/IG_ACCESS_TOKEN",
        headers=h, json=payload, timeout=30)
    if r.status_code not in (201, 204):
        print(f"   ⚠️  could not update secret: {r.status_code} {r.text[:120]}")
        return False
    return True


def main():
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": TOKEN},
        timeout=60,
    )
    data = r.json()
    if r.status_code != 200 or "access_token" not in data:
        raise SystemExit(f"Refresh failed: {data}")

    new_token = data["access_token"]
    days = round(data.get("expires_in", 0) / 86400, 1)

    stored = []
    if save_to_env(new_token):
        stored.append(".env")
    if save_to_github_secret(new_token):
        stored.append("GitHub secret")

    where = " and ".join(stored) if stored else "NOWHERE (⚠️ token not persisted!)"
    print(f"✅ Token refreshed — valid ~{days} more days. Saved to: {where}")


if __name__ == "__main__":
    main()
