from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.db.connection import get_session, async_session
from app.config import settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_db():
    """FastAPI dependency for database session"""
    async for session in get_session():
        yield session

async def verify_api_key(
    api_key: Optional[str] = Security(API_KEY_HEADER)
) -> str:
    """Verify API key from header"""
    if not api_key or api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
