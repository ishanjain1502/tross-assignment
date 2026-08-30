import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

from app.config import settings
from app.db.connection import async_session, init_db
from app.services.job_service import JobService
from app.services.scraper_service import ScraperService
from app.linkedin.exceptions import RateLimitError, SessionExpiredError

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class ScrapeWorker:
    """Background worker that processes scrape jobs"""
    
    def __init__(self):
        self.jobs = JobService()
        self.scraper = ScraperService()
        self.running = True
        self.poll_interval = 2  # seconds
        self.rate_limit_backoff = 60  # seconds
        self.rate_limited_until = None
    
    async def run(self):
        """Main worker loop"""
        logger.info("Worker starting...")
        
        # Handle graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
        
        await init_db()
        logger.info("Database initialized")
        
        while self.running:
            try:
                await self._process_one_job()
            except Exception as e:
                logger.exception(f"Error in worker loop: {e}")
                await asyncio.sleep(self.poll_interval)
        
        logger.info("Worker stopped")
    
    async def stop(self):
        """Signal worker to stop"""
        logger.info("Shutdown signal received...")
        self.running = False
    
    async def _process_one_job(self):
        """Process a single job from the queue"""
        # Check if we're rate limited
        if self.rate_limited_until:
            if datetime.now(timezone.utc) < self.rate_limited_until:
                wait_seconds = (self.rate_limited_until - datetime.now(timezone.utc)).total_seconds()
                logger.info(f"Rate limited, waiting {wait_seconds:.0f}s")
                await asyncio.sleep(min(wait_seconds, self.poll_interval))
                return
            else:
                self.rate_limited_until = None
                logger.info("Rate limit period ended, resuming")
        
        async with async_session() as session:
            # Get next job
            job = await self.jobs.get_next_queued(session)
            if not job:
                await asyncio.sleep(self.poll_interval)
                return
            
            logger.info(f"Processing job {job.id}: {job.url}")
            
            # Try to claim the job
            claimed = await self.jobs.start_processing(session, job.id)
            if not claimed:
                logger.warning(f"Job {job.id} already being processed")
                return
            
            # Process the job
            try:
                await self.scraper.scrape_profile(
                    session,
                    job_id=job.id,
                    url=job.url,
                    include_fields=job.include_fields
                )
                logger.info(f"Job {job.id} completed successfully")
                
            except RateLimitError as e:
                logger.warning(f"Job {job.id} rate limited: {e}")
                self.rate_limited_until = datetime.now(timezone.utc) + __import__('datetime').timedelta(seconds=e.retry_after)
                
            except SessionExpiredError as e:
                logger.error(f"Job {job.id} session expired: {e}")
                # Job already marked as failed by scraper_service
                
            except Exception as e:
                logger.error(f"Job {job.id} failed: {e}")
                # Job already marked as failed by scraper_service


async def main():
    worker = ScrapeWorker()
    await worker.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
