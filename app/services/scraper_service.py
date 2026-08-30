import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.linkedin.client import LinkedInClient
from app.linkedin.parsers import ProfileParser
from app.linkedin.exceptions import (
    LinkedInError,
    ProfileNotFoundError,
    RateLimitError,
    SessionExpiredError,
    ProfileIdResolutionError,
    GraphQLQueryError,
    RESTEndpointError,
    PartialDataError,
)
from app.services.cache_service import CacheService
from app.services.job_service import JobService

logger = logging.getLogger(__name__)

class ScraperService:
    """Orchestrates the profile scraping process"""
    
    def __init__(self):
        self.cache = CacheService()
        self.jobs = JobService()
        self.parser = ProfileParser()
    
    async def scrape_profile(
        self,
        session: AsyncSession,
        job_id: str,
        url: str,
        include_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Execute a complete profile scrape.
        
        Flow:
        1. Check cache
        2. Resolve profile ID
        3. Fetch data (GraphQL primary, REST fallback)
        4. Parse response
        5. Cache result
        6. Return structured data
        """
        start_time = time.time()
        
        try:
            # Step 1: Check cache
            cached = await self.cache.get(session, url)
            if cached:
                duration_ms = int((time.time() - start_time) * 1000)
                await self.jobs.complete(session, job_id, cached, duration_ms, from_cache=True)
                logger.info(f"Job {job_id} served from cache")
                return cached
            
            # Step 2-4: Scrape
            result = await self._do_scrape(url, include_fields)
            
            # Step 5: Cache
            await self.cache.set(session, url, result)
            
            # Step 6: Complete job
            duration_ms = int((time.time() - start_time) * 1000)
            await self.jobs.complete(session, job_id, result, duration_ms, from_cache=False)
            
            logger.info(f"Job {job_id} completed in {duration_ms}ms")
            return result
            
        except ProfileNotFoundError as e:
            await self.jobs.fail(session, job_id, "PROFILE_NOT_FOUND", str(e))
            raise
        except RateLimitError as e:
            await self.jobs.fail(session, job_id, "RATE_LIMITED", str(e))
            raise
        except SessionExpiredError as e:
            await self.jobs.fail(session, job_id, "SESSION_EXPIRED", str(e))
            raise
        except ProfileIdResolutionError as e:
            await self.jobs.fail(session, job_id, "RESOLUTION_FAILED", str(e))
            raise
        except LinkedInError as e:
            await self.jobs.fail(session, job_id, "LINKEDIN_ERROR", str(e))
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in job {job_id}")
            await self.jobs.fail(session, job_id, "INTERNAL_ERROR", str(e))
            raise
    
    async def _do_scrape(
        self,
        url: str,
        include_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Execute the actual scraping logic"""
        async with LinkedInClient() as client:
            # Resolve profile ID
            profile_id = await client.resolve_profile_id(url)
            
            # Try GraphQL first
            try:
                graphql_data = await client.get_profile_graphql(profile_id)
                return self._parse_graphql_response(graphql_data, profile_id, url)
            except (GraphQLQueryError, LinkedInError) as graphql_error:
                logger.warning(f"GraphQL failed, falling back to REST: {graphql_error}")
                
                # Fall back to REST
                try:
                    rest_data = await client.get_profile_rest(profile_id)
                    return self._parse_rest_response(rest_data, profile_id, url)
                except Exception as rest_error:
                    logger.error(f"REST also failed: {rest_error}")
                    raise PartialDataError(
                        "Both GraphQL and REST failed",
                        {},
                        [str(graphql_error), str(rest_error)]
                    )
    
    def _parse_graphql_response(
        self,
        data: Dict[str, Any],
        profile_id: str,
        url: str
    ) -> Dict[str, Any]:
        """Parse GraphQL response into final format"""
        profile = self.parser.parse_graphql_profile(data)
        profile['url'] = url
        profile['internal_id'] = profile_id
        
        return {
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
    
    def _parse_rest_response(
        self,
        data: Dict[str, Any],
        profile_id: str,
        url: str
    ) -> Dict[str, Any]:
        """Parse REST responses into final format"""
        profile = self.parser.parse_rest_profile(
            data.get('profile', {}) or {},
            data.get('profile_extended', {}) or {},
            data.get('picture', {}) or {}
        )
        profile['url'] = url
        profile['internal_id'] = profile_id
        
        # Collect any errors from REST calls
        warnings = data.get('_errors', [])
        
        return {
            "profile": profile,
            "experience": self.parser.parse_rest_positions(data.get('positions', {}) or {}),
            "education": self.parser.parse_rest_education(data.get('education', {}) or {}),
            "skills": self.parser.parse_rest_skills(data.get('skills', {}) or {}),
            "certifications": self.parser.parse_rest_certifications(data.get('certifications', {}) or {}),
            "languages": self.parser.parse_rest_languages(data.get('languages', {}) or {}),
            "warnings": warnings,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "source": "rest",
        }
