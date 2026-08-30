#!/usr/bin/env python3
"""
Verify LinkedIn session cookies before running scrape tests.

Usage (from project root):
    PYTHONPATH=. python scripts/verify_session.py
"""

from __future__ import annotations

import asyncio
import sys

from app.config import settings
from app.linkedin.auth import LinkedInAuth, LinkedInSession
from app.linkedin.endpoints import endpoints_config
from app.linkedin.http_client import LinkedInHttpClient


def _cookies_configured() -> bool:
    if not settings.has_cookie_auth:
        return False
    placeholders = ("your_li_at", "your_jsessionid", "paste", "example")
    li_at = (settings.linkedin_li_at or "").lower()
    jsession = (settings.linkedin_jsessionid or "").lower()
    return not any(p in li_at or p in jsession for p in placeholders)


async def verify() -> int:
    print("=" * 60)
    print("LinkedIn Session Verification")
    print("=" * 60)

    if not _cookies_configured():
        print("FAIL: LINKEDIN_LI_AT and LINKEDIN_JSESSIONID are not set in .env")
        print("Run: PYTHONPATH=. python scripts/extract_session.py")
        return 1

    auth = LinkedInAuth(None)
    jsessionid = auth._sanitize_cookie(settings.linkedin_jsessionid)
    li_at = auth._sanitize_cookie(settings.linkedin_li_at)
    csrf_token = auth._extract_csrf_from_jsessionid(jsessionid)
    session = LinkedInSession(li_at=li_at, jsessionid=jsessionid, csrf_token=csrf_token)
    headers = auth._build_request_headers(session)

    async with LinkedInHttpClient() as http:
        client = await http.get_client()
        response = await client.get(
            f"{endpoints_config.base_url}{endpoints_config.me_endpoint}",
            headers=headers,
            follow_redirects=False,
        )

    print(f"GET /voyager/api/me -> HTTP {response.status_code}")

    if response.status_code == 200:
        print("OK: Session is valid. You can run scripts/test_scrape.py")
        return 0

    if response.status_code == 302:
        location = response.headers.get("location", "")
        print("FAIL: LinkedIn redirected (session invalid or cookies mismatched).")
        if location:
            print(f"  Redirect: {location[:100]}")
    elif response.status_code in (401, 403):
        print("FAIL: LinkedIn rejected the session (401/403).")
    else:
        print(f"FAIL: Unexpected response ({response.status_code}).")

    print()
    print("Fix:")
    print("  1. Log into linkedin.com in your browser")
    print("  2. Open DevTools -> Network, refresh the feed")
    print("  3. Confirm /voyager/api/me returns 200 in the browser")
    print("  4. Copy li_at AND JSESSIONID at the same time from Application -> Cookies")
    print("  5. Run: PYTHONPATH=. python scripts/extract_session.py")
    print("  6. Restart: docker compose up -d --force-recreate worker api")
    return 1


def main() -> int:
    return asyncio.run(verify())


if __name__ == "__main__":
    sys.exit(main())
