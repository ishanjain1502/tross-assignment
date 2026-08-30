import httpx
from typing import Dict, Any, Optional
from app.linkedin.endpoints import endpoints_config
from app.linkedin.exceptions import (
    SessionExpiredError, RateLimitError, GraphQLQueryError
)

class LinkedInGraphQLClient:
    """Makes authenticated requests to LinkedIn GraphQL endpoint"""
    
    def __init__(self, client: httpx.AsyncClient, auth_headers: dict):
        self.client = client
        self.auth_headers = auth_headers
    
    async def get_profile(self, profile_id: str) -> Dict[str, Any]:
        """
        Fetch comprehensive profile data via GraphQL.
        
        Args:
            profile_id: Internal LinkedIn profile ID (e.g., 'ACoAAB...')
        
        Returns:
            Parsed JSON response with profile data
        """
        profile_urn = f"urn:li:fsd_profile:{profile_id}"
        
        payload = {
            "operationName": "profileView",
            "variables": {
                "profileUrn": profile_urn,
                "decorationId": endpoints_config.full_profile_decoration_id
            },
            "query": endpoints_config.full_profile_query
        }
        
        headers = {
            **self.auth_headers,
            "Content-Type": "application/json",
        }
        
        response = await self.client.post(
            f"{endpoints_config.base_url}{endpoints_config.graphql_endpoint}",
            headers=headers,
            json=payload
        )
        
        self._handle_response(response)
        
        try:
            data = response.json()
            
            # Check for GraphQL errors
            if 'errors' in data:
                errors = data['errors']
                error_messages = [e.get('message', 'Unknown error') for e in errors]
                raise GraphQLQueryError(
                    f"GraphQL errors: {'; '.join(error_messages)}"
                )
            
            return data
            
        except GraphQLQueryError:
            raise
        except Exception as e:
            if isinstance(e, GraphQLQueryError):
                raise
            raise GraphQLQueryError(f"Failed to parse GraphQL response: {e}")
    
    def _handle_response(self, response: httpx.Response):
        """Handle HTTP response errors"""
        
        if response.status_code == 200:
            return
        
        if response.status_code == 401:
            raise SessionExpiredError("Session expired (GraphQL)")
        
        if response.status_code == 403:
            raise RateLimitError("Access forbidden - may be rate limited")
        
        if response.status_code == 429:
            retry_after = 60
            if 'X-RateLimit-Reset' in response.headers:
                try:
                    retry_after = int(response.headers['X-RateLimit-Reset'])
                except ValueError:
                    pass
            raise RateLimitError("Rate limited (GraphQL)", retry_after=retry_after)
        
        raise GraphQLQueryError(
            f"GraphQL request failed with status {response.status_code}"
        )
