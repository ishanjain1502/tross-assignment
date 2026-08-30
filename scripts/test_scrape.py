#!/usr/bin/env python3
"""
Submit preset LinkedIn profile URLs to the local API and poll for results.

Usage (from project root):
    PYTHONPATH=. python scripts/test_scrape.py
    PYTHONPATH=. python scripts/test_scrape.py --url https://www.linkedin.com/in/someone/
    PYTHONPATH=. python scripts/test_scrape.py --base-url http://localhost:8000

Requires:
    - API running (docker compose up -d)
    - Valid LINKEDIN_LI_AT + LINKEDIN_JSESSIONID in .env
    - API_KEY in .env
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.config import settings

# Well-known public profiles for integration testing (edit as needed).
TEST_PROFILES: list[dict[str, str]] = [
    {"label": "Bill Gates", "url": "https://www.linkedin.com/in/williamhgates/"},
    {"label": "Satya Nadella", "url": "https://www.linkedin.com/in/satyanadella/"},
    {"label": "Jeff Weiner", "url": "https://www.linkedin.com/in/jeffweiner08/"},
]


@dataclass
class ScrapeResult:
    label: str
    url: str
    job_id: str
    status: str
    duration_ms: Optional[int] = None
    from_cache: bool = False
    source: Optional[str] = None
    full_name: Optional[str] = None
    headline: Optional[str] = None
    experience_count: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def _api_base_url(host: str, port: int, override: Optional[str]) -> str:
    if override:
        return override.rstrip("/")
    if host in ("0.0.0.0", "::"):
        return f"http://127.0.0.1:{port}"
    return f"http://{host}:{port}"


def _cookies_look_valid() -> bool:
    if not settings.has_cookie_auth:
        return False
    placeholders = ("your_li_at", "your_jsessionid", "paste", "example")
    li_at = (settings.linkedin_li_at or "").lower()
    jsession = (settings.linkedin_jsessionid or "").lower()
    return not any(p in li_at or p in jsession for p in placeholders)


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-API-Key": settings.api_key,
    }


def submit_job(client: httpx.Client, base_url: str, profile_url: str) -> str:
    response = client.post(
        f"{base_url}/api/v1/scrape",
        headers=_headers(),
        json={"profile_url": profile_url},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["job_id"]


def poll_job(
    client: httpx.Client,
    base_url: str,
    job_id: str,
    poll_interval: float,
    max_wait: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        response = client.get(
            f"{base_url}/api/v1/scrape/{job_id}",
            headers=_headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        status = data.get("status")
        if status in ("completed", "failed"):
            return data
        time.sleep(poll_interval)
    raise TimeoutError(f"Job {job_id} did not finish within {max_wait:.0f}s")


def run_scrape(
    client: httpx.Client,
    base_url: str,
    label: str,
    profile_url: str,
    poll_interval: float,
    max_wait: float,
) -> ScrapeResult:
    print(f"\n-> Submitting: {label}")
    print(f"  URL: {profile_url}")

    job_id = submit_job(client, base_url, profile_url)
    print(f"  Job ID: {job_id}")

    payload = poll_job(client, base_url, job_id, poll_interval, max_wait)
    status = payload.get("status", "unknown")

    if status == "completed":
        data = payload.get("data") or {}
        profile = data.get("profile") or {}
        return ScrapeResult(
            label=label,
            url=profile_url,
            job_id=job_id,
            status=status,
            duration_ms=payload.get("duration_ms"),
            from_cache=payload.get("from_cache", False),
            source=data.get("source"),
            full_name=profile.get("full_name") or profile.get("first_name"),
            headline=profile.get("headline"),
            experience_count=len(data.get("experience") or []),
        )

    error = payload.get("error") or {}
    return ScrapeResult(
        label=label,
        url=profile_url,
        job_id=job_id,
        status=status,
        error_code=error.get("code"),
        error_message=error.get("message"),
    )


def print_summary(results: list[ScrapeResult]) -> None:
    print("\n" + "=" * 72)
    print("SCRAPE TEST SUMMARY")
    print("=" * 72)

    passed = 0
    for r in results:
        if r.status == "completed":
            passed += 1
            cache = " (cache)" if r.from_cache else ""
            print(
                f"  OK {r.label}: {r.full_name or '-'} | {r.headline or '-'} "
                f"| exp={r.experience_count} | {r.source}{cache} | {r.duration_ms}ms"
            )
        else:
            print(f"  FAIL {r.label}: {r.status} - {r.error_code}: {r.error_message}")

    print("-" * 72)
    print(f"  {passed}/{len(results)} completed successfully")
    print("=" * 72)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test scrape API with preset profile URLs")
    parser.add_argument(
        "--base-url",
        default=None,
        help="API base URL (default: http://127.0.0.1:APP_PORT from .env)",
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        metavar="URL",
        help="Additional profile URL to test (can be repeated)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between status polls (default: 2)",
    )
    parser.add_argument(
        "--max-wait",
        type=float,
        default=120.0,
        help="Max seconds to wait per job (default: 120)",
    )
    parser.add_argument(
        "--skip-preset",
        action="store_true",
        help="Only run URLs passed via --url",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = _api_base_url(settings.app_host, settings.app_port, args.base_url)

    profiles: list[dict[str, str]] = []
    if not args.skip_preset:
        profiles.extend(TEST_PROFILES)
    for url in args.urls or []:
        profiles.append({"label": url, "url": url})

    if not profiles:
        print("No profiles to test. Use preset list or pass --url.")
        return 1

    print("=" * 72)
    print("LinkedIn Profile API - Scrape Test")
    print("=" * 72)
    print(f"API:        {base_url}")
    print(f"Profiles:   {len(profiles)}")
    print(f"Cookie auth: {'yes' if _cookies_look_valid() else 'NO - run scripts/extract_session.py'}")

    if not _cookies_look_valid():
        print("\nWarning: LinkedIn cookies not configured. Scrapes will likely fail.")

    try:
        with httpx.Client() as client:
            health = client.get(f"{base_url}/health", timeout=10.0)
            health.raise_for_status()
            print(f"Health:     {health.json()}")
    except httpx.HTTPError as exc:
        print(f"\nError: API not reachable at {base_url}/health - {exc}")
        print("Start the stack: docker compose up -d")
        print("If you also run uvicorn locally, stop it or use a different port.")
        return 1

    results: list[ScrapeResult] = []
    with httpx.Client() as client:
        for entry in profiles:
            try:
                results.append(
                    run_scrape(
                        client,
                        base_url,
                        entry["label"],
                        entry["url"],
                        args.poll_interval,
                        args.max_wait,
                    )
                )
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:200]
                print(f"  HTTP {exc.response.status_code}: {detail}")
                if exc.response.status_code == 401:
                    print(
                        "  Hint: API_KEY mismatch or a stale local uvicorn on port 8000. "
                        "Stop local servers, then: docker compose up -d --force-recreate api worker"
                    )
                results.append(
                    ScrapeResult(
                        label=entry["label"],
                        url=entry["url"],
                        job_id="-",
                        status="http_error",
                        error_code=str(exc.response.status_code),
                        error_message=detail,
                    )
                )
            except TimeoutError as exc:
                print(f"  Timeout: {exc}")
                results.append(
                    ScrapeResult(
                        label=entry["label"],
                        url=entry["url"],
                        job_id="-",
                        status="timeout",
                        error_message=str(exc),
                    )
                )

    print_summary(results)
    return 0 if all(r.status == "completed" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
