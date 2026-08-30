#!/usr/bin/env python3
"""
Standalone LinkedIn profile scraper (PhantomBuster-style).

Hits LinkedIn Voyager APIs directly with session cookies — no browser automation.

Inputs:
  - Session cookies: li_at + JSESSIONID (from a logged-in browser)
  - User-Agent (must match the browser where cookies were extracted)
  - One or more LinkedIn profile URLs

Output:
  JSON array of scrape results (profile, experience, education, skills, etc.)

Usage (from project root):
    PYTHONPATH=. python scripts/scrape_profiles.py \\
        --li-at "AQED..." \\
        --jsessionid "ajax:1234..." \\
        --user-agent "Mozilla/5.0 ..." \\
        --url "https://www.linkedin.com/in/williamhgates/"

    # Cookies + user-agent from .env (LINKEDIN_LI_AT, LINKEDIN_JSESSIONID, USER_AGENT):
    PYTHONPATH=. python scripts/scrape_profiles.py --url "https://www.linkedin.com/in/satyanadella/"

    # Multiple profiles + file output:
    PYTHONPATH=. python scripts/scrape_profiles.py \\
        --urls-file profiles.txt \\
        --output results.json \\
        --delay 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.linkedin.endpoints import endpoints_config
from app.linkedin.exceptions import (
    GraphQLQueryError,
    LinkedInError,
    ProfileIdResolutionError,
    ProfileNotFoundError,
    RateLimitError,
    SessionExpiredError,
)
from app.linkedin.dash_client import LinkedInDashClient
from app.linkedin.graphql_client import LinkedInGraphQLClient
from app.linkedin.http_client import LinkedInHttpClient
from app.linkedin.parsers import ProfileParser
from app.linkedin.resolver import ProfileResolver
from app.linkedin.rest_client import LinkedInRESTClient

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _sanitize_cookie(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _sanitize_user_agent(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _extract_csrf_from_jsessionid(jsessionid: str) -> str:
    jsessionid = _sanitize_cookie(jsessionid)
    if "|" in jsessionid:
        return jsessionid.split("|", 1)[1]
    return jsessionid


def _format_jsessionid(jsessionid: str) -> str:
    jsessionid = _sanitize_cookie(jsessionid)
    if jsessionid.startswith('"') and jsessionid.endswith('"'):
        return jsessionid
    return f'"{jsessionid}"'


def build_auth_headers(li_at: str, jsessionid: str, user_agent: str) -> dict[str, str]:
    """Headers LinkedIn Voyager expects for authenticated API calls."""
    li_at = _sanitize_cookie(li_at)
    jsessionid = _sanitize_cookie(jsessionid)
    csrf_token = _extract_csrf_from_jsessionid(jsessionid)

    headers = dict(endpoints_config.required_headers)
    headers.update(
        {
            "User-Agent": user_agent,
            "Cookie": f"li_at={li_at}; JSESSIONID={_format_jsessionid(jsessionid)}",
            "csrf-token": csrf_token,
            "X-CSRF-Token": csrf_token,
            "X-Li-Lang": "en_US",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{endpoints_config.base_url}/feed/",
        }
    )
    return headers


def parse_cookie_string(cookie_string: str) -> tuple[str, str]:
    """Extract li_at and JSESSIONID from a raw Cookie header or document.cookie string."""
    li_at_match = re.search(r"(?:^|;\s*)li_at=([^;]+)", cookie_string)
    jsession_match = re.search(r"(?:^|;\s*)JSESSIONID=([^;]+)", cookie_string, re.IGNORECASE)

    if not li_at_match or not jsession_match:
        raise ValueError(
            "Cookie string must contain both li_at and JSESSIONID values. "
            "Pass --li-at and --jsessionid separately if needed."
        )

    return _sanitize_cookie(li_at_match.group(1)), _sanitize_cookie(jsession_match.group(1))


def _cookies_look_valid(li_at: str, jsessionid: str) -> bool:
    if not li_at or not jsessionid or len(li_at) < 10 or len(jsessionid) < 10:
        return False
    placeholders = ("your_li_at", "your_jsessionid", "paste", "example")
    combined = f"{li_at} {jsessionid}".lower()
    return not any(p in combined for p in placeholders)


def _load_urls_from_file(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


class ProfileScraper:
    """Scrapes LinkedIn profiles via Voyager dash API (primary), GraphQL, and REST."""

    def __init__(self, auth_headers: dict[str, str]):
        self.auth_headers = auth_headers
        self.parser = ProfileParser()

    async def scrape(self, url: str) -> dict[str, Any]:
        async with LinkedInHttpClient() as http:
            client = await http.get_client()
            resolver = ProfileResolver(client, self.auth_headers)
            dash = LinkedInDashClient(client, self.auth_headers)
            graphql = LinkedInGraphQLClient(client, self.auth_headers)
            rest = LinkedInRESTClient(client, self.auth_headers)

            vanity = resolver.extract_vanity_name(url)
            if vanity:
                try:
                    dash_data = await dash.get_profile_by_vanity(vanity)
                    profile_id = resolver._profile_id_from_urn(
                        (dash_data.get("data", {}).get("*elements") or [None])[0]
                    ) or await resolver.resolve_profile_id(url)
                    result = self.parser.parse_dash_profile_response(dash_data, url, profile_id)
                    result["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    return result
                except LinkedInError as dash_error:
                    warnings = [f"dash_failed: {dash_error}"]
                except Exception as dash_error:
                    warnings = [f"dash_failed: {dash_error}"]
            else:
                warnings = []

            profile_id = await resolver.resolve_profile_id(url)

            try:
                graphql_data = await graphql.get_profile(profile_id)
                result = self._parse_graphql(graphql_data, profile_id, url)
                result["warnings"] = warnings
                return result
            except (GraphQLQueryError, LinkedInError) as graphql_error:
                warnings.append(f"graphql_failed: {graphql_error}")
                rest_data = await self._fetch_rest(rest, profile_id)
                result = self._parse_rest(rest_data, profile_id, url)
                result["warnings"].extend(warnings)
                return result

    async def _fetch_rest(self, rest: LinkedInRESTClient, profile_id: str) -> dict[str, Any]:
        keys = [
            "profile",
            "profile_extended",
            "positions",
            "education",
            "skills",
            "certifications",
            "languages",
            "picture",
        ]
        endpoint_names = [
            "profile",
            "profile_extended",
            "positions",
            "education",
            "skills",
            "certifications",
            "languages",
            "profile_picture",
        ]

        results = await asyncio.gather(
            *[rest.get(name, profile_id=profile_id) for name in endpoint_names],
            return_exceptions=True,
        )

        data: dict[str, Any] = {"_errors": []}
        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                data[key] = None
                data["_errors"].append(f"{key}: {result}")
            else:
                data[key] = result
        return data

    def _parse_graphql(self, data: dict[str, Any], profile_id: str, url: str) -> dict[str, Any]:
        profile = self.parser.parse_graphql_profile(data)
        profile["url"] = url
        profile["internal_id"] = profile_id

        return {
            "status": "success",
            "profile_url": url,
            "profile": profile,
            "experience": self.parser.parse_graphql_positions(data),
            "education": self.parser.parse_graphql_education(data),
            "skills": self.parser.parse_graphql_skills(data),
            "certifications": self.parser.parse_graphql_certifications(data),
            "languages": self.parser.parse_graphql_languages(data),
            "warnings": [],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "source": "graphql",
        }

    def _parse_rest(self, data: dict[str, Any], profile_id: str, url: str) -> dict[str, Any]:
        profile = self.parser.parse_rest_profile(
            data.get("profile") or {},
            data.get("profile_extended") or {},
            data.get("picture") or {},
        )
        profile["url"] = url
        profile["internal_id"] = profile_id

        return {
            "status": "success",
            "profile_url": url,
            "profile": profile,
            "experience": self.parser.parse_rest_positions(data.get("positions") or {}),
            "education": self.parser.parse_rest_education(data.get("education") or {}),
            "skills": self.parser.parse_rest_skills(data.get("skills") or {}),
            "certifications": self.parser.parse_rest_certifications(data.get("certifications") or {}),
            "languages": self.parser.parse_rest_languages(data.get("languages") or {}),
            "warnings": list(data.get("_errors") or []),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "source": "rest",
        }


async def verify_session(auth_headers: dict[str, str]) -> bool:
    async with LinkedInHttpClient() as http:
        client = await http.get_client()
        response = await client.get(
            f"{endpoints_config.base_url}{endpoints_config.me_endpoint}",
            headers=auth_headers,
            follow_redirects=False,
        )
    return response.status_code == 200


def _error_result(url: str, error: Exception) -> dict[str, Any]:
    code = type(error).__name__
    if isinstance(error, ProfileNotFoundError):
        code = "PROFILE_NOT_FOUND"
    elif isinstance(error, SessionExpiredError):
        code = "SESSION_EXPIRED"
    elif isinstance(error, RateLimitError):
        code = "RATE_LIMITED"
    elif isinstance(error, ProfileIdResolutionError):
        code = "RESOLUTION_FAILED"

    return {
        "status": "error",
        "profile_url": url,
        "error": {
            "code": code,
            "message": str(error),
        },
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


async def run_scrapes(
    scraper: ProfileScraper,
    urls: list[str],
    delay_seconds: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for index, url in enumerate(urls):
        if index > 0 and delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

        print(f"[{index + 1}/{len(urls)}] Scraping: {url}", file=sys.stderr)
        try:
            result = await scraper.scrape(url)
            name = result.get("profile", {}).get("full_name") or "-"
            exp_count = len(result.get("experience") or [])
            print(
                f"  OK: {name} | experience={exp_count} | source={result.get('source')}",
                file=sys.stderr,
            )
            results.append(result)
        except LinkedInError as exc:
            print(f"  FAIL: {exc}", file=sys.stderr)
            results.append(_error_result(url, exc))
        except Exception as exc:
            print(f"  FAIL: {exc}", file=sys.stderr)
            results.append(_error_result(url, exc))

    return results


def resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    li_at = args.li_at
    jsessionid = args.jsessionid
    user_agent = args.user_agent

    if args.cookie:
        parsed_li_at, parsed_jsessionid = parse_cookie_string(args.cookie)
        li_at = li_at or parsed_li_at
        jsessionid = jsessionid or parsed_jsessionid

    if not li_at:
        li_at = settings.linkedin_li_at
    if not jsessionid:
        jsessionid = settings.linkedin_jsessionid
    if not user_agent and settings.linkedin_user_agent:
        user_agent = _sanitize_user_agent(settings.linkedin_user_agent)
    if not user_agent:
        user_agent = DEFAULT_USER_AGENT

    if not _cookies_look_valid(li_at or "", jsessionid or ""):
        raise SystemExit(
            "Missing or invalid session cookies.\n"
            "Provide --li-at and --jsessionid, --cookie, or set LINKEDIN_LI_AT "
            "and LINKEDIN_JSESSIONID in .env.\n"
            "Extract cookies with: PYTHONPATH=. python scripts/extract_session.py"
        )

    return li_at, jsessionid, user_agent


def collect_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = []
    if args.url:
        urls.extend(args.url)
    if args.urls_file:
        urls.extend(_load_urls_from_file(Path(args.urls_file)))
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape LinkedIn profiles using session cookies (PhantomBuster-style)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    auth = parser.add_argument_group("authentication")
    auth.add_argument("--li-at", help="li_at session cookie value")
    auth.add_argument("--jsessionid", help="JSESSIONID cookie value")
    auth.add_argument(
        "--cookie",
        help='Full cookie string containing li_at and JSESSIONID (e.g. from document.cookie)',
    )
    auth.add_argument(
        "--user-agent",
        help="Browser User-Agent (overrides USER_AGENT in .env; must match cookie source browser)",
    )

    targets = parser.add_argument_group("profiles")
    targets.add_argument(
        "--url",
        action="append",
        dest="url",
        metavar="URL",
        help="LinkedIn profile URL (repeatable)",
    )
    targets.add_argument(
        "--urls-file",
        metavar="FILE",
        help="Text file with one profile URL per line (# comments allowed)",
    )

    output = parser.add_argument_group("output")
    output.add_argument(
        "--output",
        "-o",
        metavar="FILE",
        help="Write JSON results to file (default: stdout)",
    )
    output.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between profile requests (default: 2)",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip session verification against /voyager/api/me",
    )

    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    urls = collect_urls(args)

    if not urls:
        print("No profile URLs provided. Use --url or --urls-file.", file=sys.stderr)
        return 1

    li_at, jsessionid, user_agent = resolve_credentials(args)
    auth_headers = build_auth_headers(li_at, jsessionid, user_agent)

    if not args.skip_verify:
        print("Verifying session...", file=sys.stderr)
        if not await verify_session(auth_headers):
            print(
                "Session verification failed (GET /voyager/api/me did not return 200).\n"
                "Re-extract cookies from your browser and ensure --user-agent matches.",
                file=sys.stderr,
            )
            return 1
        print("Session OK.\n", file=sys.stderr)

    scraper = ProfileScraper(auth_headers)
    started = time.monotonic()
    results = await run_scrapes(scraper, urls, args.delay)
    elapsed = time.monotonic() - started

    payload = {
        "meta": {
            "profiles_requested": len(urls),
            "profiles_succeeded": sum(1 for r in results if r.get("status") == "success"),
            "profiles_failed": sum(1 for r in results if r.get("status") == "error"),
            "elapsed_seconds": round(elapsed, 2),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        },
        "results": results,
    }

    indent = 2 if args.pretty else None
    json_text = json.dumps(payload, indent=indent, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(json_text + "\n", encoding="utf-8")
        print(f"\nWrote {len(results)} result(s) to {args.output}", file=sys.stderr)
    else:
        print(json_text)

    failed = payload["meta"]["profiles_failed"]
    return 0 if failed == 0 else 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
