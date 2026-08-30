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
    
    async def resolve_profile_id(self, public_url: str) -> str:
        """
        Convert public URL to internal profile ID.
        
        Strategy: Fetch profile page HTML and extract ID from:
        1. data-member-id attribute
        2. memberId JSON field
        3. fsd_profile URN format
        """
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
        
        if response.status_code == 401 or response.status_code == 403:
            raise ProfileIdResolutionError(
                f"Access denied ({response.status_code}). Session may be expired."
            )
        
        if response.status_code != 200:
            raise ProfileIdResolutionError(
                f"Unexpected status {response.status_code} when fetching profile page"
            )
        
        # Try each pattern in order
        html = response.text
        
        for pattern_info in endpoints_config.get_profile_id_patterns():
            match = re.search(pattern_info.pattern, html)
            if match:
                profile_id = match.group(1)
                if self._validate_profile_id(profile_id):
                    return profile_id
        
        raise ProfileIdResolutionError(
            f"Could not extract profile ID from {public_url}. "
            f"LinkedIn may have changed their page structure. "
            f"Check config/linkedin_endpoints.yaml for updated patterns."
        )
    
    def _validate_profile_id(self, profile_id: str) -> bool:
        """Basic validation of extracted profile ID"""
        if not profile_id or len(profile_id) < 5:
            return False
        # Profile IDs are typically alphanumeric, sometimes with dashes
        return bool(re.match(r'^[A-Za-z0-9_-]+$', profile_id))
