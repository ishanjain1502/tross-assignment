import re
import httpx
from typing import Optional
from app.linkedin.endpoints import endpoints_config
from app.linkedin.exceptions import ProfileNotFoundError, ProfileIdResolutionError

class ProfileResolver:
    """Resolves public LinkedIn URLs to internal profile IDs"""
    
    def __init__(self, client: httpx.AsyncClient, auth_headers: dict):
        self.client = client
        self.auth_headers = auth_headers
    
    def normalize_url(self, url: str) -> str:
        """Normalize LinkedIn profile URL"""
        url = url.strip().rstrip('/')
        
        # Handle protocol-relative URLs
        if url.startswith('//'):
            url = 'https:' + url
        elif url.startswith('/'):
            url = f"{endpoints_config.base_url}{url}"
        elif not url.startswith('http'):
            url = f"{endpoints_config.base_url}/{url}"
        
        # Ensure https
        if url.startswith('http://'):
            url = 'https://' + url[7:]
        
        if url.startswith('https://linkedin.com/'):
            url = 'https://www.linkedin.com' + url[len('https://linkedin.com'):]
        
        return url
    
    def extract_vanity_name(self, public_url: str) -> Optional[str]:
        """Extract public username from /in/<vanity> profile URLs."""
        url = self.normalize_url(public_url)
        match = re.search(r"/in/([^/?#]+)", url)
        if not match:
            return None
        vanity = match.group(1).strip()
        if vanity.lower() in ("in", "pub"):
            return None
        return vanity
    
    async def resolve_profile_id(self, public_url: str) -> str:
        """
        Convert public URL to internal profile ID.

        Strategy:
        1. Voyager dash API lookup by vanity name (/in/<username>)
        2. HTML page scrape with configured regex patterns (fallback)
        """
        vanity = self.extract_vanity_name(public_url)
        if vanity:
            profile_id = await self._resolve_via_member_identity(vanity)
            if profile_id:
                return profile_id

        profile_id = await self._resolve_via_html(public_url)
        if profile_id:
            return profile_id

        raise ProfileIdResolutionError(
            f"Could not extract profile ID from {public_url}. "
            f"LinkedIn may have changed their page structure. "
            f"Check config/linkedin_endpoints.yaml for updated patterns."
        )

    async def _resolve_via_member_identity(self, vanity: str) -> Optional[str]:
        """Resolve profile ID via Voyager dash profiles API."""
        endpoint = endpoints_config.get_rest_endpoint("profile_by_vanity")
        response = await self.client.get(
            f"{endpoints_config.base_url}{endpoint}",
            params={"q": "memberIdentity", "memberIdentity": vanity},
            headers=self.auth_headers,
        )

        if response.status_code == 404:
            return None

        if response.status_code in (401, 403):
            raise ProfileIdResolutionError(
                f"Access denied ({response.status_code}). Session may be expired."
            )

        if response.status_code != 200:
            return None

        try:
            payload = response.json()
        except Exception:
            return None

        elements = (
            payload.get("data", {}).get("*elements")
            or payload.get("data", {}).get("elements")
            or []
        )
        for element in elements:
            profile_id = self._profile_id_from_urn(element)
            if profile_id:
                return profile_id

        for item in payload.get("included", []):
            entity_urn = item.get("entityUrn") or item.get("objectUrn")
            profile_id = self._profile_id_from_urn(entity_urn)
            if profile_id:
                return profile_id

        return None

    async def _resolve_via_html(self, public_url: str) -> Optional[str]:
        """Fallback: fetch profile page HTML and extract ID from known patterns."""
        url = self.normalize_url(public_url)

        response = await self.client.get(
            url,
            headers={
                **self.auth_headers,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        if response.status_code == 404:
            raise ProfileNotFoundError(f"Profile not found: {public_url}")

        if response.status_code in (401, 403):
            raise ProfileIdResolutionError(
                f"Access denied ({response.status_code}). Session may be expired."
            )

        if response.status_code != 200:
            raise ProfileIdResolutionError(
                f"Unexpected status {response.status_code} when fetching profile page"
            )

        html = response.text
        for pattern_info in endpoints_config.get_profile_id_patterns():
            match = re.search(pattern_info.pattern, html)
            if match:
                profile_id = match.group(1)
                if self._validate_profile_id(profile_id):
                    return profile_id

        return None

    def _profile_id_from_urn(self, urn: Optional[str]) -> Optional[str]:
        if not urn or not isinstance(urn, str):
            return None
        marker = "fsd_profile:"
        if marker not in urn:
            return None
        profile_id = urn.split(marker, 1)[1]
        if self._validate_profile_id(profile_id):
            return profile_id
        return None
    
    def _validate_profile_id(self, profile_id: str) -> bool:
        """Basic validation of extracted profile ID"""
        if not profile_id or len(profile_id) < 5:
            return False
        # Profile IDs are typically alphanumeric, sometimes with dashes
        return bool(re.match(r'^[A-Za-z0-9_-]+$', profile_id))
