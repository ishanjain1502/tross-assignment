import asyncio
from typing import Dict, Any, Optional, List
import httpx
from app.linkedin.http_client import LinkedInHttpClient
from app.linkedin.auth import LinkedInAuth
from app.linkedin.resolver import ProfileResolver
from app.linkedin.rest_client import LinkedInRESTClient
from app.linkedin.graphql_client import LinkedInGraphQLClient
from app.linkedin.dash_client import LinkedInDashClient
from app.linkedin.exceptions import (
    LinkedInError, GraphQLQueryError, ProfileNotFoundError
)

class LinkedInClient:
    """
    Unified client for LinkedIn API operations.
    
    Usage:
        async with LinkedInClient() as client:
            data = await client.scrape_profile("https://www.linkedin.com/in/johndoe/")
    """
    
    def __init__(self):
        self._http: Optional[LinkedInHttpClient] = None
        self._auth: Optional[LinkedInAuth] = None
        self._resolver: Optional[ProfileResolver] = None
        self._rest_client: Optional[LinkedInRESTClient] = None
        self._graphql_client: Optional[LinkedInGraphQLClient] = None
        self._dash_client: Optional[LinkedInDashClient] = None
    
    async def __aenter__(self):
        self._http = LinkedInHttpClient()
        http_client = await self._http.get_client()
        
        self._auth = LinkedInAuth(http_client)
        await self._auth.get_session()  # Ensure authenticated
        
        auth_headers = self._auth.get_auth_headers()
        
        self._resolver = ProfileResolver(http_client, auth_headers)
        self._rest_client = LinkedInRESTClient(http_client, auth_headers)
        self._graphql_client = LinkedInGraphQLClient(http_client, auth_headers)
        self._dash_client = LinkedInDashClient(http_client, auth_headers)
        
        return self
    
    async def __aexit__(self, *args):
        if self._http:
            await self._http.close()
    
    async def resolve_profile_id(self, public_url: str) -> str:
        """Convert public URL to internal profile ID"""
        return await self._resolver.resolve_profile_id(public_url)

    def extract_vanity_name(self, public_url: str) -> Optional[str]:
        """Extract vanity username from a /in/<username> profile URL."""
        return self._resolver.extract_vanity_name(public_url)

    async def get_profile_dash(self, vanity: str) -> Dict[str, Any]:
        """Fetch profile via Voyager dash API (primary method)."""
        return await self._dash_client.get_profile_by_vanity(vanity)
    
    async def get_profile_graphql(self, profile_id: str) -> Dict[str, Any]:
        """Fetch profile via GraphQL (primary method)"""
        return await self._graphql_client.get_profile(profile_id)
    
    async def get_profile_rest(self, profile_id: str) -> Dict[str, Any]:
        """Fetch all profile sections via REST endpoints"""
        results = await asyncio.gather(
            self._rest_client.get('profile', profile_id=profile_id),
            self._rest_client.get('profile_extended', profile_id=profile_id),
            self._rest_client.get('positions', profile_id=profile_id),
            self._rest_client.get('education', profile_id=profile_id),
            self._rest_client.get('skills', profile_id=profile_id),
            self._rest_client.get('certifications', profile_id=profile_id),
            self._rest_client.get('languages', profile_id=profile_id),
            self._rest_client.get('profile_picture', profile_id=profile_id),
            return_exceptions=True
        )
        
        keys = ['profile', 'profile_extended', 'positions', 'education',
                'skills', 'certifications', 'languages', 'picture']
        
        data = {}
        errors = []
        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                data[key] = None
                errors.append(f"{key}: {str(result)}")
            else:
                data[key] = result
        
        data['_errors'] = errors
        return data
    
    def invalidate_session(self):
        """Force session refresh on next request"""
        if self._auth:
            self._auth.invalidate_session()
