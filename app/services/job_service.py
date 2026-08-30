import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import select, update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Job
from app.config import settings

class JobService:
    """Manages scrape jobs in PostgreSQL queue"""
    
    async def create(
        self,
        session: AsyncSession,
        url: str,
        webhook_url: Optional[str] = None,
        include_fields: Optional[List[str]] = None
    ) -> str:
        """Create a new job and return its ID"""
        job_id = str(uuid.uuid4())
        
        job = Job(
            id=job_id,
            url=url,
            webhook_url=webhook_url,
            include_fields=include_fields,
            status="queued"
        )
        
        session.add(job)
        await session.commit()
        
        return job_id
    
    async def get(self, session: AsyncSession, job_id: str) -> Optional[Job]:
        """Get a job by ID"""
        stmt = select(Job).where(Job.id == job_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_next_queued(self, session: AsyncSession) -> Optional[Job]:
        """Get the next queued job (FIFO order)"""
        stmt = select(Job).where(
            Job.status == "queued"
        ).order_by(Job.created_at.asc()).limit(1)
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def start_processing(self, session: AsyncSession, job_id: str) -> bool:
        """Mark a job as processing. Returns False if already being processed."""
        stmt = (
            update(Job)
            .where(and_(
                Job.id == job_id,
                Job.status == "queued"
            ))
            .values(status="processing")
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0
    
    async def complete(
        self,
        session: AsyncSession,
        job_id: str,
        result: Dict[str, Any],
        duration_ms: int,
        from_cache: bool = False
    ) -> None:
        """Mark a job as completed with results"""
        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(
                status="completed",
                result=result,
                duration_ms=duration_ms,
                from_cache=from_cache,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await session.execute(stmt)
        await session.commit()
    
    async def fail(
        self,
        session: AsyncSession,
        job_id: str,
        error_code: str,
        error_message: str
    ) -> None:
        """Mark a job as failed"""
        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(
                status="failed",
                error_code=error_code,
                error_message=error_message,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await session.execute(stmt)
        await session.commit()
    
    async def get_queue_depth(self, session: AsyncSession) -> int:
        """Get count of queued jobs"""
        stmt = select(func.count()).where(Job.status == "queued")
        result = await session.execute(stmt)
        return result.scalar() or 0
    
    async def cleanup_old_jobs(self, session: AsyncSession, days: int = 7) -> int:
        """Delete completed/failed jobs older than N days"""
        from sqlalchemy import delete
        cutoff = datetime.now(timezone.utc) - __import__('datetime').timedelta(days=days)
        stmt = delete(Job).where(
            and_(
                Job.status.in_(["completed", "failed"]),
                Job.updated_at < cutoff
            )
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount
    
    def to_dict(self, job: Job) -> Dict[str, Any]:
        """Convert Job model to dictionary for API response"""
        return {
            "job_id": job.id,
            "url": job.url,
            "status": job.status,
            "result": job.result,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "from_cache": job.from_cache,
            "duration_ms": job.duration_ms,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }
