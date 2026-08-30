import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import ProfileCache
from app.config import settings

class CacheService:
    """Manages profile data caching in PostgreSQL"""
    
    def __init__(self, ttl_hours: int = None):
        self.ttl_hours = ttl_hours or settings.cache_ttl_hours
    
    async def get(self, session: AsyncSession, url: str) -> Optional[Dict[str, Any]]:
        """
        Get cached profile data if exists and not expired.
        
        Returns None if not cached or expired.
        """
        stmt = select(ProfileCache).where(
            and_(
                ProfileCache.url == url,
                ProfileCache.expires_at > datetime.now(timezone.utc)
            )
        )
        result = await session.execute(stmt)
        cache_entry = result.scalar_one_or_none()
        
        if cache_entry:
            return cache_entry.data
        
        return None
    
    async def set(
        self, 
        session: AsyncSession, 
        url: str, 
        data: Dict[str, Any],
        ttl_hours: int = None
    ) -> None:
        """
        Store profile data in cache.
        
        Uses UPSERT pattern - inserts or updates existing entry.
        """
        ttl = ttl_hours or self.ttl_hours
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)
        
        # Check if entry exists
        stmt = select(ProfileCache).where(ProfileCache.url == url)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.data = data
            existing.expires_at = expires_at
        else:
            new_entry = ProfileCache(
                url=url,
                data=data,
                expires_at=expires_at
            )
            session.add(new_entry)
        
        await session.commit()
    
    async def delete(self, session: AsyncSession, url: str) -> bool:
        """Delete a specific cache entry. Returns True if deleted."""
        stmt = delete(ProfileCache).where(ProfileCache.url == url)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0
    
    async def cleanup_expired(self, session: AsyncSession) -> int:
        """Delete all expired cache entries. Returns count deleted."""
        stmt = delete(ProfileCache).where(
            ProfileCache.expires_at <= datetime.now(timezone.utc)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount
    
    async def clear_all(self, session: AsyncSession) -> int:
        """Clear all cache entries. Returns count deleted."""
        stmt = delete(ProfileCache)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount
