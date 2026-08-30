import httpx
from typing import Any, Dict, Optional
from app.linkedin.endpoints import endpoints_config
from app.linkedin.exceptions import ProfileIdResolutionError, SessionExpiredError


class LinkedInDashClient:
    """Fetches profile data via Voyager dash profiles API."""

    def __init__(self, client: httpx.AsyncClient, auth_headers: dict):
        self.client = client
        self.auth_headers = auth_headers

    async def get_profile_by_vanity(self, vanity: str) -> Dict[str, Any]:
        endpoint = endpoints_config.get_rest_endpoint("profile_by_vanity")
        response = await self.client.get(
            f"{endpoints_config.base_url}{endpoint}",
            params={
                "q": "memberIdentity",
                "memberIdentity": vanity,
                "decorationId": endpoints_config.dash_full_profile_decoration_id,
            },
            headers=self.auth_headers,
        )
        self._handle_response(response)
        return response.json()

    def _handle_response(self, response: httpx.Response):
        if response.status_code == 200:
            return
        if response.status_code in (401, 403):
            raise SessionExpiredError(
                f"Session expired or access denied (dash profiles, {response.status_code})"
            )
        raise ProfileIdResolutionError(
            f"Dash profile request failed with status {response.status_code}"
        )
