import httpx
from typing import Dict, Any, Optional
from app.linkedin.endpoints import endpoints_config
from app.linkedin.exceptions import (
    LinkedInError, SessionExpiredError, RateLimitError, RESTEndpointError
)

class LinkedInRESTClient:
    """Makes authenticated requests to LinkedIn REST endpoints"""
    
    def __init__(self, client: httpx.AsyncClient, auth_headers: dict):
        self.client = client
        self.auth_headers = auth_headers
    
    async def get(self, endpoint_name: str, **path_params) -> Dict[str, Any]:
        """
        Make authenticated GET request to a LinkedIn REST endpoint.
        
        Args:
            endpoint_name: Key from endpoints config (e.g., 'profile', 'positions')
            **path_params: Variables for URL formatting (e.g., profile_id='ABC123')
        
        Returns:
            Parsed JSON response
        
        Raises:
            SessionExpiredError: If session is invalid (401)
            RateLimitError: If rate limited (429)
            RESTEndpointError: For other errors
        """
        url_path = endpoints_config.get_rest_endpoint(endpoint_name, **path_params)
        full_url = f"{endpoints_config.base_url}{url_path}"
        
        response = await self.client.get(
            full_url,
            headers=self.auth_headers
        )
        
        self._handle_response(response, endpoint_name)
        
        try:
            return response.json()
        except Exception:
            raise RESTEndpointError(
                f"Failed to parse JSON response from {endpoint_name}"
            )
    
    def _handle_response(self, response: httpx.Response, endpoint_name: str):
        """Check for error responses and raise appropriate exceptions"""
        
        if response.status_code == 200:
            return
        
        if response.status_code == 401:
            raise SessionExpiredError(
                f"Session expired when calling {endpoint_name}"
            )
        
        if response.status_code == 403:
            error_msg = "Access forbidden"
            try:
                error_data = response.json()
                error_msg = error_data.get('message', error_msg)
            except Exception:
                pass
            
            if 'throttle' in error_msg.lower() or 'rate' in error_msg.lower():
                raise RateLimitError(f"Rate limited: {error_msg}")
            
            raise RESTEndpointError(f"Forbidden when calling {endpoint_name}: {error_msg}")
        
        if response.status_code == 404:
            raise RESTEndpointError(f"Endpoint not found: {endpoint_name}")
        
        if response.status_code == 429:
            retry_after = 60
            if 'X-RateLimit-Reset' in response.headers:
                try:
                    retry_after = int(response.headers['X-RateLimit-Reset'])
                except ValueError:
                    pass
            raise RateLimitError(
                f"Rate limited when calling {endpoint_name}",
                retry_after=retry_after
            )
        
        if response.status_code >= 500:
            raise RESTEndpointError(
                f"LinkedIn server error ({response.status_code}) on {endpoint_name}"
            )
        
        raise RESTEndpointError(
            f"Unexpected status {response.status_code} from {endpoint_name}"
        )
