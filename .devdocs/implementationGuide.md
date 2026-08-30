# LinkedIn Profile API - AI IDE Implementation Guide

## For Cursor

---

# PREAMBLE

## Project Overview

Build a hosted HTTPS API that accepts LinkedIn profile URLs and returns structured profile data (name, headline, location, about, experience, education, skills, certifications, languages, profile images) by directly hitting LinkedIn's internal APIs—**no browser automation allowed**.

The system uses an async job queue pattern: clients submit URLs and receive job IDs immediately, then poll for results. This handles the inherent latency of LinkedIn scraping (2-5 seconds/profile) and rate limiting gracefully.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT                                         │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ HTTPS POST /api/v1/scrape
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI SERVICE                                     │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────────────────────┐    │
│  │ Input Valid. │→│ Create Job    │→│ Return 202 + job_id            │    │
│  └──────────────┘  └───────────────┘  └────────────────────────────────┘    │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POSTGRESQL (Docker)                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────────┐     │
│  │ jobs table     │  │ cache table    │  │ sessions table (optional)  │     │
│  │ (queue)        │  │ (profile data) │  │                            │     │
│  └────────────────┘  └────────────────┘  └────────────────────────────┘     │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ Worker polls
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WORKER PROCESS                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 1. Poll jobs table for status='queued'                             │    │
│  │ 2. Check cache table → HIT: copy data, skip scraping               │    │
│  │ 3. Resolve profile URL → internal ID                               │    │
│  │ 4. Authenticate (cookie or credential)                             │    │
│  │ 5. Fetch data via LinkedIn GraphQL/REST APIs                       │    │
│  │ 6. Parse response to clean JSON                                    │    │
│  │ 7. Store in cache table                                            │    │
│  │ 8. Update jobs table with result                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.11+ |
| Web Framework | FastAPI | 0.100+ |
| HTTP Client | httpx | 0.25+ |
| Database | PostgreSQL | 16 |
| Database Driver | asyncpg | 0.29+ |
| ORM | SQLAlchemy (async) | 2.0+ |
| Container | Docker | 24+ |
| Base Image | python:3.11-slim | - |

## Global Constraints & Anti-Patterns

### MUST DO
- Use `httpx.AsyncClient` for all HTTP requests (NOT `requests`)
- Use async/await throughout (NOT synchronous code)
- Use parameterized SQL queries (NOT string formatting)
- Store all secrets in environment variables (NOT in code)
- Return job ID immediately, poll for results (NOT synchronous scraping)
- Handle partial data gracefully with warnings array

### MUST NOT DO
- Use browser automation (Playwright, Selenium, Puppeteer)
- Use Redis (we're using PostgreSQL for everything)
- Use `requests` library (blocking, no async)
- Hardcode LinkedIn endpoints in business logic
- Return errors as 200 with error in body (use proper HTTP status codes)
- Store raw LinkedIn responses in cache (parse first)

### Cursor-Specific Notes
- Each segment creates/modifies specific files—follow exactly
- Run verification commands after each segment
- If a segment fails, do NOT proceed to the next one
- Use `@filename` to reference existing files when asked to modify them

---

# SEGMENT 0: Project Scaffolding & Docker Setup

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Empty directory
This Segment Creates: Project structure, Docker files, .env.example
This Segment Depends On: Nothing
```

## Objective
Create the project directory structure, Docker Compose setup with PostgreSQL, and base configuration files.

## Steps

### Step 0.1: Create Directory Structure

```bash
mkdir -p linkedin-api
cd linkedin-api
mkdir -p app/api app/models app/linkedin app/services app/workers app/db migrations tests/fixtures scripts
touch app/__init__.py app/api/__init__.py app/models/__init__.py app/linkedin/__init__.py app/services/__init__.py app/workers/__init__.py app/db/__init__.py
```

### Step 0.2: Create `.env.example`

Create file `.env.example`:

```env
# LinkedIn Credentials (extract from browser - see Segment 8)
LINKEDIN_LI_AT=your_li_at_cookie_here
LINKEDIN_JSESSIONID=your_jsessionid_cookie_here

# Optional: Credential login (often triggers CAPTCHA)
LINKEDIN_USERNAME=
LINKEDIN_PASSWORD=

# Database
DATABASE_URL=postgresql+asyncpg://linkedin:linkedin@localhost:5432/linkedin_api

# API Security
API_KEY=change_this_to_a_secure_random_string

# App Settings
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO
CACHE_TTL_HOURS=24
```

### Step 0.3: Create `.env` (copy from example)

```bash
cp .env.example .env
```

### Step 0.4: Create `docker-compose.yml`

Create file `docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: linkedin_postgres
    environment:
      POSTGRES_USER: linkedin
      POSTGRES_PASSWORD: linkedin
      POSTGRES_DB: linkedin_api
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U linkedin"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    container_name: linkedin_api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://linkedin:linkedin@postgres:5432/linkedin_api
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    container_name: linkedin_worker
    environment:
      - DATABASE_URL=postgresql+asyncpg://linkedin:linkedin@postgres:5432/linkedin_api
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
    command: python -m app.workers.main

volumes:
  postgres_data:
```

### Step 0.5: Create `Dockerfile.api`

Create file `Dockerfile.api`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Step 0.6: Create `Dockerfile.worker`

Create file `Dockerfile.worker`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "app.workers.main"]
```

### Step 0.7: Create `requirements.txt`

Create file `requirements.txt`:

```
fastapi==0.104.1
uvicorn==0.24.0
httpx==0.25.2
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.23
pydantic==2.5.2
pydantic-settings==2.1.0
python-dotenv==1.0.0
```

### Step 0.8: Create `.gitignore`

Create file `.gitignore`:

```
.env
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
build/
postgres_data/
```

## File Map

### Creates
- `.env.example`
- `.env`
- `docker-compose.yml`
- `Dockerfile.api`
- `Dockerfile.worker`
- `requirements.txt`
- `.gitignore`
- `app/__init__.py` (and subdirectory __init__.py files)

### Depends On
- Nothing

### Is Used By
- All subsequent segments

## Verification

### Step 1: Start PostgreSQL only

```bash
docker-compose up -d postgres
```

### Step 2: Verify PostgreSQL is running

```bash
docker-compose exec postgres psql -U linkedin -c "SELECT 1;"
```

**Expected Output:**
```
 ?column? 
----------
        1
(1 row)
```

### Step 3: Stop containers

```bash
docker-compose down
```

## If This Fails

### Symptom: "docker-compose: command not found"
**Diagnosis**: Docker Compose not installed
**Fix**: Install Docker Desktop which includes Compose, or install docker-compose separately
**Reference**: https://docs.docker.com/get-docker/

### Symptom: "port 5432 already in use"
**Diagnosis**: Another PostgreSQL instance running
**Fix Option A**: Stop existing PostgreSQL: `sudo systemctl stop postgresql`
**Fix Option B**: Change port in docker-compose.yml to `5433:5432`

### Symptom: "permission denied" on docker-compose
**Diagnosis**: User not in docker group
**Fix**:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Symptom: Container exits immediately
**Diagnosis**: Check logs
```bash
docker-compose logs postgres
```
Look for specific error messages in output.

---

# SEGMENT 1: Database Schema & Connection

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Docker setup complete, PostgreSQL running
This Segment Creates: Database schema, connection module
This Segment Depends On: Segment 0 (Docker, PostgreSQL)
```

## Objective
Create the PostgreSQL tables for jobs queue, profile cache, and establish async database connection.

## Steps

### Step 1.1: Create `app/db/connection.py`

Create file `app/db/connection.py`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://linkedin:linkedin@localhost:5432/linkedin_api")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### Step 1.2: Create `app/db/models.py`

Create file `app/db/models.py`:

```python
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Boolean
from sqlalchemy.sql import func
from app.db.connection import Base

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(String, primary_key=True)
    url = Column(String, nullable=False)
    webhook_url = Column(String, nullable=True)
    include_fields = Column(JSON, nullable=True)
    status = Column(String, default="queued", nullable=False)  # queued, processing, completed, failed
    result = Column(JSON, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    from_cache = Column(Boolean, default=False)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ProfileCache(Base):
    __tablename__ = "profile_cache"
    
    url = Column(String, primary_key=True)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
```

### Step 1.3: Create `migrations/001_initial.sql`

Create file `migrations/001_initial.sql`:

```sql
-- This file is for reference. SQLAlchemy creates tables automatically.
-- Run this manually if you prefer SQL-based migrations.

CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR PRIMARY KEY,
    url VARCHAR NOT NULL,
    webhook_url VARCHAR,
    include_fields JSON,
    status VARCHAR NOT NULL DEFAULT 'queued',
    result JSON,
    error_code VARCHAR,
    error_message TEXT,
    from_cache BOOLEAN DEFAULT FALSE,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS profile_cache (
    url VARCHAR PRIMARY KEY,
    data JSON NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created ON jobs(created_at);
CREATE INDEX idx_cache_expires ON profile_cache(expires_at);
```

### Step 1.4: Create `scripts/init_db.py`

Create file `scripts/init_db.py`:

```python
import asyncio
from app.db.connection import init_db

async def main():
    print("Initializing database tables...")
    await init_db()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
```

## File Map

### Creates
- `app/db/connection.py`
- `app/db/models.py`
- `migrations/001_initial.sql`
- `scripts/init_db.py`

### Modifies
- Nothing

### Depends On
- Segment 0 (PostgreSQL running)

### Is Used By
- Segment 2 (Configuration)
- Segment 14 (Job queue)
- Segment 15 (Cache service)
- Segment 17 (FastAPI routes)
- Segment 19 (Worker)

## Verification

### Step 1: Start PostgreSQL

```bash
docker-compose up -d postgres
```

### Step 2: Install dependencies locally

```bash
pip install -r requirements.txt
```

### Step 3: Initialize database

```bash
python scripts/init_db.py
```

**Expected Output:**
```
Initializing database tables...
Done!
```

### Step 4: Verify tables exist

```bash
docker-compose exec postgres psql -U linkedin -d linkedin_api -c "\dt"
```

**Expected Output:**
```
             List of relations
 Schema |     Name      | Type  |  Owner   
--------+---------------+-------+----------
 public | jobs          | table | linkedin
 public | profile_cache | table | linkedin
(2 rows)
```

### Step 5: Verify table structure

```bash
docker-compose exec postgres psql -U linkedin -d linkedin_api -c "\d jobs"
```

**Expected Output:**
```
                                        Table "public.jobs"
    Column     |           Type           | Collation | Nullable |              Default              
---------------+--------------------------+-----------+----------+-----------------------------------
 id            | character varying        |           | not null | 
 url           | character varying        |           | not null | 
 webhook_url   | character varying        |           |          | 
 include_fields | json                     |           |          | 
 status        | character varying        |           | not null | 'queued'::character varying
 result        | json                     |           |          | 
 error_code    | character varying        |           |          | 
 error_message | text                     |           |          | 
 from_cache    | boolean                  |           |          | false
 duration_ms   | integer                  |           |          | 
 created_at    | timestamp with time zone |           |          | now()
 updated_at    | timestamp with time zone |           |          | now()
Indexes:
    "jobs_pkey" PRIMARY KEY, btree (id)
    "idx_jobs_created" btree (created_at)
    "idx_jobs_status" btree (status)
```

## If This Fails

### Symptom: "ModuleNotFoundError: No module named 'sqlalchemy'"
**Diagnosis**: Dependencies not installed
**Fix**:
```bash
pip install -r requirements.txt
```

### Symptom: "relation does not exist" when checking tables
**Diagnosis**: init_db.py didn't run or failed silently
**Fix**: Check for errors when running init_db.py, ensure DATABASE_URL in .env is correct

### Symptom: "could not connect to server: Connection refused"
**Diagnosis**: PostgreSQL not running or wrong port
**Fix**:
```bash
docker-compose ps  # Check if postgres is running
docker-compose logs postgres  # Check for errors
```

### Symptom: "password authentication failed"
**Diagnosis**: Wrong credentials in DATABASE_URL
**Fix**: Ensure .env has correct DATABASE_URL matching docker-compose.yml credentials

### Symptom: "database 'linkedin_api' does not exist"
**Diagnosis**: Database not created
**Fix**: 
```bash
docker-compose exec postgres createdb -U linkedin linkedin_api
python scripts/init_db.py
```

---

# SEGMENT 2: Configuration Management

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Database schema created
This Segment Creates: Configuration module with validation
This Segment Depends On: Segment 0, Segment 1
```

## Objective
Create a centralized configuration module using pydantic-settings that loads from environment variables with validation.

## Steps

### Step 2.1: Create `app/config.py`

Create file `app/config.py`:

```python
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Optional, List

class Settings(BaseSettings):
    # LinkedIn Authentication
    linkedin_li_at: Optional[str] = Field(None, alias="LINKEDIN_LI_AT")
    linkedin_jsessionid: Optional[str] = Field(None, alias="LINKEDIN_JSESSIONID")
    linkedin_username: Optional[str] = Field(None, alias="LINKEDIN_USERNAME")
    linkedin_password: Optional[str] = Field(None, alias="LINKEDIN_PASSWORD")
    
    # Database
    database_url: str = Field("postgresql+asyncpg://linkedin:linkedin@localhost:5432/linkedin_api", alias="DATABASE_URL")
    
    # API Security
    api_key: str = Field("change-this-key", alias="API_KEY")
    
    # App Settings
    app_host: str = Field("0.0.0.0", alias="APP_HOST")
    app_port: int = Field(8000, alias="APP_PORT")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    cache_ttl_hours: int = Field(24, alias="CACHE_TTL_HOURS")
    
    # LinkedIn API Configuration
    linkedin_base_url: str = "https://www.linkedin.com"
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v.upper()
    
    @property
    def has_cookie_auth(self) -> bool:
        return bool(self.linkedin_li_at and self.linkedin_jsessionid)
    
    @property
    def has_credential_auth(self) -> bool:
        return bool(self.linkedin_username and self.linkedin_password)
    
    @property
    def has_any_auth(self) -> bool:
        return self.has_cookie_auth or self.has_credential_auth
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Singleton instance
settings = Settings()
```

### Step 2.2: Create `scripts/check_config.py`

Create file `scripts/check_config.py`:

```python
from app.config import settings

def main():
    print("=" * 50)
    print("Configuration Check")
    print("=" * 50)
    print(f"Database URL: {settings.database_url[:50]}...")
    print(f"API Key: {settings.api_key[:10]}...")
    print(f"Cache TTL: {settings.cache_ttl_hours} hours")
    print(f"Log Level: {settings.log_level}")
    print()
    print("Authentication Status:")
    print(f"  Cookie Auth: {'✓ Configured' if settings.has_cookie_auth else '✗ Missing'}")
    print(f"  Credential Auth: {'✓ Configured' if settings.has_credential_auth else '✗ Missing'}")
    print()
    
    if not settings.has_any_auth:
        print("⚠️  WARNING: No authentication configured!")
        print("   Run 'python scripts/extract_session.py' to set up cookie auth.")
    else:
        print("✓ Authentication ready")
    
    if settings.api_key == "change-this-key":
        print("⚠️  WARNING: API key is default value. Change it in .env")

if __name__ == "__main__":
    main()
```

## File Map

### Creates
- `app/config.py`
- `scripts/check_config.py`

### Modifies
- Nothing

### Depends On
- Segment 0 (.env file)

### Is Used By
- All subsequent segments that need configuration

## Verification

### Step 1: Run configuration check

```bash
python scripts/check_config.py
```

**Expected Output:**
```
==================================================
Configuration Check
==================================================
Database URL: postgresql+asyncpg://linkedin:linkedin@localhost:5432/link...
API Key: change-this...
Cache TTL: 24 hours
Log Level: INFO

Authentication Status:
  Cookie Auth: ✗ Missing
  Credential Auth: ✗ Missing

⚠️  WARNING: No authentication configured!
   Run 'python scripts/extract_session.py' to set up cookie auth.
⚠️  WARNING: API key is default value. Change it in .env
```

### Step 2: Verify settings import works

```bash
python -c "from app.config import settings; print(f'Log level: {settings.log_level}')"
```

**Expected Output:**
```
Log level: INFO
```

## If This Fails

### Symptom: "ModuleNotFoundError: No module named 'pydantic_settings'"
**Diagnosis**: Wrong package name or not installed
**Fix**:
```bash
pip install pydantic-settings
```

### Symptom: "ValidationError: LOG_LEVEL must be one of..."
**Diagnosis**: Invalid LOG_LEVEL value in .env
**Fix**: Set LOG_LEVEL=INFO (or DEBUG, WARNING, ERROR, CRITICAL) in .env

### Symptom: "dotenv.Error: File does not exist"
**Diagnosis**: .env file missing
**Fix**:
```bash
cp .env.example .env
```

### Symptom: Import error from app.config
**Diagnosis**: Python path issue
**Fix**: Ensure you're running from project root directory

---

# SEGMENT 3: Pydantic Request/Response Models

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Database and config ready
This Segment Creates: Pydantic models for API contracts
This Segment Depends On: Segment 0, Segment 1, Segment 2
```

## Objective
Define the API request and response schemas using Pydantic v2.

## Steps

### Step 3.1: Create `app/models/requests.py`

Create file `app/models/requests.py`:

```python
from pydantic import BaseModel, field_validator
from typing import Optional, List
import re

class ScrapeRequest(BaseModel):
    profile_url: str
    webhook_url: Optional[str] = None
    include_fields: Optional[List[str]] = None
    
    @field_validator('profile_url')
    @classmethod
    def validate_linkedin_url(cls, v: str) -> str:
        # Normalize URL
        v = v.strip()
        if v.endswith('/'):
            v = v[:-1]
        
        # Validate format
        pattern = r'^https?://(www\.)?linkedin\.com/in/[\w-]+$'
        if not re.match(pattern, v):
            raise ValueError(
                'Invalid LinkedIn profile URL. '
                'Expected format: https://www.linkedin.com/in/username'
            )
        
        return v
    
    @field_validator('include_fields')
    @classmethod
    def validate_include_fields(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        
        valid_fields = {
            'profile', 'experience', 'education', 'skills', 
            'certifications', 'languages', 'projects', 'publications',
            'patents', 'honors', 'volunteer', 'courses', 'organizations'
        }
        
        invalid = set(v) - valid_fields
        if invalid:
            raise ValueError(f'Invalid fields: {invalid}. Valid: {valid_fields}')
        
        return v
```

### Step 3.2: Create `app/models/responses.py`

Create file `app/models/responses.py`:

```python
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# === Job Status Responses ===

class JobAcceptedResponse(BaseModel):
    job_id: str
    status: str
    estimated_wait_seconds: int
    poll_url: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    created_at: Optional[str] = None

class JobErrorResponse(BaseModel):
    job_id: str
    status: str
    error: Dict[str, str]

class JobCompletedResponse(BaseModel):
    job_id: str
    status: str
    duration_ms: int
    data: Dict[str, Any]
    scraped_at: Optional[str] = None
    from_cache: bool = False

# === Error Responses ===

class ErrorResponse(BaseModel):
    error: Dict[str, Any]

# === Profile Data Models ===

class LocationInfo(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None

class CompanyInfo(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    logo_url: Optional[str] = None
    industry: Optional[str] = None

class DateRange(BaseModel):
    start: Optional[Dict[str, int]] = None
    end: Optional[Dict[str, int]] = None
    is_current: bool = False

class ExperienceItem(BaseModel):
    title: Optional[str] = None
    company: Optional[CompanyInfo] = None
    location: Optional[str] = None
    dates: Optional[DateRange] = None
    description: Optional[str] = None

class EducationItem(BaseModel):
    institution: Optional[Dict[str, str]] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    dates: Optional[DateRange] = None
    description: Optional[str] = None

class SkillItem(BaseModel):
    name: Optional[str] = None
    endorsement_count: Optional[int] = 0

class CertificationItem(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    issue_date: Optional[Dict[str, int]] = None
    expiry_date: Optional[Dict[str, int]] = None
    credential_id: Optional[str] = None

class LanguageItem(BaseModel):
    name: Optional[str] = None
    proficiency: Optional[str] = None

class ProfileData(BaseModel):
    url: Optional[str] = None
    internal_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    headline: Optional[str] = None
    about: Optional[str] = None
    location: Optional[LocationInfo] = None
    profile_image_url: Optional[str] = None
    background_image_url: Optional[str] = None
    connections: Optional[str] = None

class CompleteProfileResponse(BaseModel):
    profile: ProfileData
    experience: List[ExperienceItem] = []
    education: List[EducationItem] = []
    skills: List[SkillItem] = []
    certifications: List[CertificationItem] = []
    languages: List[LanguageItem] = []
    warnings: List[str] = []
    scraped_at: Optional[str] = None
    source: Optional[str] = None
```

### Step 3.3: Create `app/models/__init__.py`

Update file `app/models/__init__.py`:

```python
from app.models.requests import ScrapeRequest
from app.models.responses import (
    JobAcceptedResponse,
    JobStatusResponse,
    JobErrorResponse,
    JobCompletedResponse,
    ErrorResponse,
    ProfileData,
    ExperienceItem,
    EducationItem,
    SkillItem,
    CertificationItem,
    LanguageItem,
    CompleteProfileResponse,
)

__all__ = [
    "ScrapeRequest",
    "JobAcceptedResponse",
    "JobStatusResponse",
    "JobErrorResponse",
    "JobCompletedResponse",
    "ErrorResponse",
    "ProfileData",
    "ExperienceItem",
    "EducationItem",
    "SkillItem",
    "CertificationItem",
    "LanguageItem",
    "CompleteProfileResponse",
]
```

## File Map

### Creates
- `app/models/requests.py`
- `app/models/responses.py`

### Modifies
- `app/models/__init__.py`

### Depends On
- Segment 0 (requirements.txt with pydantic)

### Is Used By
- Segment 17 (FastAPI routes)

## Verification

### Step 1: Test request validation

```bash
python -c "
from app.models.requests import ScrapeRequest

# Valid URL
req = ScrapeRequest(profile_url='https://www.linkedin.com/in/johndoe')
print(f'Valid URL: {req.profile_url}')

# Test invalid URL
try:
    ScrapeRequest(profile_url='https://google.com')
except Exception as e:
    print(f'Invalid URL caught: {e}')
"
```

**Expected Output:**
```
Valid URL: https://www.linkedin.com/in/johndoe
Invalid URL caught: 1 validation error for ScrapeRequest
profile_url
  Value error, Invalid LinkedIn profile URL. Expected format: https://www.linkedin.com/in/username [type=value_error, input_value='https://google.com', input_type=str]
```

### Step 2: Test response models

```bash
python -c "
from app.models.responses import JobAcceptedResponse, ProfileData

# Test JobAcceptedResponse
resp = JobAcceptedResponse(
    job_id='test-123',
    status='queued',
    estimated_wait_seconds=10,
    poll_url='/api/v1/scrape/test-123'
)
print(f'Job response: {resp.model_dump_json(indent=2)}')

# Test ProfileData
profile = ProfileData(first_name='John', last_name='Doe')
print(f'Profile: {profile.model_dump_json(indent=2)}')
"
```

**Expected Output:**
```json
{
  "job_id": "test-123",
  "status": "queued",
  "estimated_wait_seconds": 10,
  "poll_url": "/api/v1/scrape/test-123"
}
{
  "url": null,
  "internal_id": null,
  "first_name": "John",
  "last_name": "Doe",
  "full_name": null,
  "headline": null,
  "about": null,
  "location": null,
  "profile_image_url": null,
  "background_image_url": null,
  "connections": null
}
```

## If This Fails

### Symptom: "ImportError: cannot import name 'field_validator'"
**Diagnosis**: Wrong Pydantic version (v1 instead of v2)
**Fix**:
```bash
pip install pydantic==2.5.2
```

### Symptom: Validation error not raised for invalid URL
**Diagnosis**: Validator not being called
**Fix**: Ensure `@classmethod` decorator is present before validator function

### Symptom: "model_dump_json" not found
**Diagnosis**: Pydantic v1 installed (uses `.json()` instead)
**Fix**:
```bash
pip install --upgrade pydantic
```

---

# SEGMENT 4: LinkedIn Endpoints Configuration

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Models defined
This Segment Creates: Externalized endpoint configuration
This Segment Depends On: Segment 0, Segment 3
```

## Objective
Create an externalized configuration for LinkedIn API endpoints and GraphQL queries that can be updated without code changes.

## Steps

### Step 4.1: Create `config/linkedin_endpoints.yaml`

Create directory and file `config/linkedin_endpoints.yaml`:

```yaml
# LinkedIn Internal API Endpoints
# Update these when LinkedIn changes their API structure
# Last verified: 2024-01

base_url: "https://www.linkedin.com"

rest_endpoints:
  # Identity & Profile
  profile: "/voyager/api/identity/profiles/{profile_id}"
  profile_extended: "/voyager/api/identity/dash/profiles/{profile_id}"
  profile_picture: "/voyager/api/identity/profiles/{profile_id}/profilePicture"
  me: "/voyager/api/me"
  
  # Sections
  positions: "/voyager/api/identity/profiles/{profile_id}/positions"
  education: "/voyager/api/identity/profiles/{profile_id}/educations"
  skills: "/voyager/api/identity/profiles/{profile_id}/skills"
  certifications: "/voyager/api/identity/profiles/{profile_id}/certifications"
  languages: "/voyager/api/identity/profiles/{profile_id}/languages"
  projects: "/voyager/api/identity/profiles/{profile_id}/projects"
  publications: "/voyager/api/identity/profiles/{profile_id}/publications"
  honors: "/voyager/api/identity/profiles/{profile_id}/honors"
  volunteer: "/voyager/api/identity/profiles/{profile_id}/volunteerExperiences"
  
  # GraphQL
  graphql: "/voyager/api/graphql"

graphql:
  profile_full_query: |
    query profileView($profileUrn:Urn!, $decorationId:String!) {
      profile(viewer:{}, profileUrn:$profileUrn) {
        ... on FullProfile {
          firstName
          lastName
          headline
          summary
          location { name country { code } }
          profilePicture { displayImage { elements { identifier rootUrl } } }
          backgroundImage { displayImage { elements { identifier rootUrl } } }
          positions { elements { ... on Position { title companyName companyUrn companyLogo { image { rootUrl identifier } } locationName startDate { year month } endDate { year month } description } } }
          educations { elements { ... on Education { schoolName degreeName fieldOfStudy startDate { year } endDate { year } activities description } } }
          skills { elements { name endorsementCount } }
          certifications { elements { name authority start { year month } end { year month } licenseNumber } }
          languages { elements { name proficiency } }
        }
      }
    }
  
  decoration_ids:
    full_profile: "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-28"

# Headers required for authenticated requests
required_headers:
  accept: "application/vnd.linkedin.normalized+json+2.1"
  x_restli_protocol_version: "2.0.0"
  x_li_track: '{"clientVersion":"3.0.4244","osName":"web","deviceFactor":"DESKTOP","browserName":"chrome","browserVersion":"120.0"}'
  sec_fetch_dest: "empty"
  sec_fetch_mode: "cors"
  sec_fetch_site: "same-origin"

# Profile ID extraction patterns (order matters - first match wins)
profile_id_patterns:
  - name: "data_member_id"
    pattern: 'data-member-id="([^"]+)"'
  - name: "member_id_urn"
    pattern: '"memberId":"([^"]+)"'
  - name: "fsd_profile_urn"
    pattern: 'urn:li:fsd_profile:([A-Za-z0-9_-]+)'
```

### Step 4.2: Create `app/linkedin/endpoints.py`

Create file `app/linkedin/endpoints.py`:

```python
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class ProfileIdPattern:
    name: str
    pattern: str

@dataclass  
class EndpointsConfig:
    base_url: str
    rest_endpoints: Dict[str, str]
    graphql: Dict[str, Any]
    required_headers: Dict[str, str]
    profile_id_patterns: List[ProfileIdPattern]
    
    @property
    def me_endpoint(self) -> str:
        return self.rest_endpoints.get('me', '/voyager/api/me')
    
    @property
    def graphql_endpoint(self) -> str:
        return self.rest_endpoints.get('graphql', '/voyager/api/graphql')
    
    @property
    def full_profile_query(self) -> str:
        return self.graphql.get('profile_full_query', '')
    
    @property
    def full_profile_decoration_id(self) -> str:
        return self.graphql.get('decoration_ids', {}).get('full_profile', '')
    
    def get_rest_endpoint(self, name: str, **kwargs) -> str:
        """Get REST endpoint with variable substitution"""
        template = self.rest_endpoints.get(name)
        if not template:
            raise ValueError(f"Unknown endpoint: {name}")
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing parameter {e} for endpoint {name}")
    
    def get_profile_id_patterns(self) -> List[ProfileIdPattern]:
        return self.profile_id_patterns

def load_endpoints_config(config_path: Optional[str] = None) -> EndpointsConfig:
    """Load endpoints configuration from YAML file"""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "linkedin_endpoints.yaml"
    
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    
    patterns = [
        ProfileIdPattern(name=p['name'], pattern=p['pattern'])
        for p in data.get('profile_id_patterns', [])
    ]
    
    return EndpointsConfig(
        base_url=data.get('base_url', 'https://www.linkedin.com'),
        rest_endpoints=data.get('rest_endpoints', {}),
        graphql=data.get('graphql', {}),
        required_headers=data.get('required_headers', {}),
        profile_id_patterns=patterns
    )

# Singleton instance
endpoints_config = load_endpoints_config()
```

### Step 4.3: Add PyYAML to requirements

Update file `requirements.txt`, add:
```
pyyaml==6.0.1
```

## File Map

### Creates
- `config/linkedin_endpoints.yaml`
- `app/linkedin/endpoints.py`

### Modifies
- `requirements.txt`

### Depends On
- Segment 0 (project structure)

### Is Used By
- Segment 6 (Authentication)
- Segment 9 (Profile ID resolution)
- Segment 10-12 (API client)

## Verification

### Step 1: Install PyYAML

```bash
pip install pyyaml==6.0.1
```

### Step 2: Test endpoint loading

```bash
python -c "
from app.linkedin.endpoints import endpoints_config, load_endpoints_config

print('Base URL:', endpoints_config.base_url)
print('Me endpoint:', endpoints_config.me_endpoint)
print('GraphQL endpoint:', endpoints_config.graphql_endpoint)
print()
print('Profile endpoint with ID:')
print('  ', endpoints_config.get_rest_endpoint('profile', profile_id='ABC123'))
print()
print('Profile ID patterns:')
for p in endpoints_config.get_profile_id_patterns():
    print(f'  - {p.name}: {p.pattern[:40]}...')
print()
print('Required headers:')
for k, v in endpoints_config.required_headers.items():
    print(f'  {k}: {v[:40]}...')
"
```

**Expected Output:**
```
Base URL: https://www.linkedin.com
Me endpoint: /voyager/api/me
GraphQL endpoint: /voyager/api/graphql

Profile endpoint with ID:
   /voyager/api/identity/profiles/ABC123

Profile ID patterns:
  - data_member_id: data-member-id="([^"]+)"
  - member_id_urn: "memberId":"([^"]+)"
  - fsd_profile_urn: urn:li:fsd_profile:([A-Za-z0-9_-]+)

Required headers:
  accept: application/vnd.linkedin.normalized+json+2.1
  x_restli_protocol_version: 2.0.0
  x_li_track: {"clientVersion":"3.0.4244","osName":"web...
  sec_fetch_dest: empty
  sec_fetch_mode: cors
  sec_fetch_site: same-origin
```

## If This Fails

### Symptom: "ModuleNotFoundError: No module named 'yaml'"
**Diagnosis**: PyYAML not installed
**Fix**:
```bash
pip install pyyaml
```

### Symptom: "FileNotFoundError: config/linkedin_endpoints.yaml"
**Diagnosis**: Config file not created or wrong path
**Fix**: Ensure you created the `config/` directory and the YAML file inside it

### Symptom: "KeyError: 'rest_endpoints'"
**Diagnosis**: YAML file has incorrect structure
**Fix**: Check YAML indentation (must be spaces, not tabs) and structure matches the example

---

# SEGMENT 5: Custom Exceptions

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Endpoints configured
This Segment Creates: Exception hierarchy
This Segment Depends On: Segment 0
```

## Objective
Create a custom exception hierarchy for LinkedIn-specific errors.

## Steps

### Step 5.1: Create `app/linkedin/exceptions.py`

Create file `app/linkedin/exceptions.py`:

```python
class LinkedInError(Exception):
    """Base exception for all LinkedIn API errors"""
    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class AuthError(LinkedInError):
    """Authentication failed"""
    pass

class SessionExpiredError(AuthError):
    """Session token expired or invalid"""
    pass

class CaptchaRequiredError(AuthError):
    """CAPTCHA intervention required during login"""
    pass

class ProfileNotFoundError(LinkedInError):
    """Profile does not exist or is not accessible"""
    pass

class PrivateProfileError(LinkedInError):
    """Profile is private and not accessible"""
    pass

class RateLimitError(LinkedInError):
    """Rate limit exceeded"""
    def __init__(self, message: str, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message)

class ProfileIdResolutionError(LinkedInError):
    """Could not extract profile ID from URL"""
    pass

class GraphQLQueryError(LinkedInError):
    """GraphQL query failed"""
    pass

class RESTEndpointError(LinkedInError):
    """REST endpoint returned error"""
    pass

class PartialDataError(LinkedInError):
    """Some sections failed but others succeeded"""
    def __init__(self, message: str, partial_data: dict, errors: list):
        self.partial_data = partial_data
        self.errors = errors
        super().__init__(message)
```

## File Map

### Creates
- `app/linkedin/exceptions.py`

### Modifies
- Nothing

### Depends On
- Nothing

### Is Used By
- Segment 6 (Auth)
- Segment 9-12 (Client)
- Segment 15 (Service)
- Segment 19 (Worker)

## Verification

```bash
python -c "
from app.linkedin.exceptions import (
    LinkedInError, AuthError, SessionExpiredError, CaptchaRequiredError,
    ProfileNotFoundError, RateLimitError, PartialDataError
)

# Test inheritance
e = SessionExpiredError('Session expired')
print(f'SessionExpiredError is LinkedInError: {isinstance(e, LinkedInError)}')
print(f'SessionExpiredError is AuthError: {isinstance(e, AuthError)}')

# Test RateLimitError with retry_after
r = RateLimitError('Rate limited', retry_after=120)
print(f'Retry after: {r.retry_after} seconds')

# Test PartialDataError
p = PartialDataError('Partial failure', {'name': 'John'}, ['skills failed'])
print(f'Partial data: {p.partial_data}')
print(f'Errors: {p.errors}')
"
```

**Expected Output:**
```
SessionExpiredError is LinkedInError: True
SessionExpiredError is AuthError: True
Retry after: 120 seconds
Partial data: {'name': 'John'}
Errors: ['skills failed']
```

## If This Fails

### Symptom: "cannot import name 'LinkedInError'"
**Diagnosis**: File not created or path issue
**Fix**: Ensure `app/linkedin/exceptions.py` exists and `app/linkedin/__init__.py` exists

---

# SEGMENT 6: HTTP Client Foundation & Cookie Authentication

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Exceptions and endpoints defined
This Segment Creates: HTTP client with cookie-based auth
This Segment Depends On: Segment 2, Segment 4, Segment 5
```

## Objective
Create the HTTP client foundation using httpx and implement cookie-based authentication.

## Steps

### Step 6.1: Create `app/linkedin/auth.py`

Create file `app/linkedin/auth.py`:

```python
import time
from dataclasses import dataclass
from typing import Optional, Tuple
import httpx
from app.config import settings
from app.linkedin.endpoints import endpoints_config
from app.linkedin.exceptions import (
    AuthError, SessionExpiredError, CaptchaRequiredError
)

@dataclass
class LinkedInSession:
    """Represents an authenticated LinkedIn session"""
    li_at: str
    jsessionid: str
    csrf_token: str
    created_at: float = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
    
    @property
    def cookie_string(self) -> str:
        return f"li_at={self.li_at}; JSESSIONID={self.jsessionid}"
    
    @property
    def is_expired(self) -> bool:
        """Sessions typically last 6 months, but check for safety"""
        age_hours = (time.time() - self.created_at) / 3600
        return age_hours > 24 * 180  # 180 days

class LinkedInAuth:
    """Handles LinkedIn authentication"""
    
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self._session: Optional[LinkedInSession] = None
    
    def _extract_csrf_from_jsessionid(self, jsessionid: str) -> str:
        """CSRF token is the part after the pipe character in JSESSIONID"""
        if "|" in jsessionid:
            return jsessionid.split("|")[1]
        return jsessionid
    
    def get_auth_headers(self) -> dict:
        """Get headers required for authenticated requests"""
        if not self._session:
            raise AuthError("Not authenticated - call get_session() first")
        
        headers = dict(endpoints_config.required_headers)
        headers.update({
            "Cookie": self._session.cookie_string,
            "X-CSRF-Token": self._session.csrf_token,
            "Referer": f"{endpoints_config.base_url}/feed/",
        })
        return headers
    
    async def get_session(self) -> LinkedInSession:
        """Get a valid session, creating if necessary"""
        if self._session and not self._session.is_expired:
            # Verify session is still valid
            if await self._verify_session():
                return self._session
        
        # Try cookie-based auth first
        if settings.has_cookie_auth:
            return await self._create_cookie_session()
        
        # Fall back to credential auth (implemented in next segment)
        raise AuthError(
            "No authentication available. "
            "Set LINKEDIN_LI_AT and LINKEDIN_JSESSIONID in .env, "
            "or configure credential-based auth."
        )
    
    async def _create_cookie_session(self) -> LinkedInSession:
        """Create session from pre-extracted cookies"""
        jsessionid = settings.linkedin_jsessionid
        csrf_token = self._extract_csrf_from_jsessionid(jsessionid)
        
        session = LinkedInSession(
            li_at=settings.linkedin_li_at,
            jsessionid=jsessionid,
            csrf_token=csrf_token
        )
        
        # Verify the session works
        if await self._verify_session_with(session):
            self._session = session
            return session
        
        raise SessionExpiredError(
            "Cookie session is invalid or expired. "
            "Please re-extract cookies from your browser."
        )
    
    async def _verify_session(self) -> bool:
        """Verify current session is valid"""
        if not self._session:
            return False
        return await self._verify_session_with(self._session)
    
    async def _verify_session_with(self, session: LinkedInSession) -> bool:
        """Verify a specific session works by calling /me endpoint"""
        try:
            headers = dict(endpoints_config.required_headers)
            headers.update({
                "Cookie": session.cookie_string,
                "X-CSRF-Token": session.csrf_token,
                "Referer": f"{endpoints_config.base_url}/feed/",
            })
            
            response = await self.client.get(
                f"{endpoints_config.base_url}{endpoints_config.me_endpoint}",
                headers=headers
            )
            
            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                return False
            else:
                # Other status codes might indicate temporary issues
                return response.status_code == 200
                
        except Exception:
            return False
    
    def invalidate_session(self):
        """Force session to be refreshed on next get_session() call"""
        self._session = None
```

### Step 6.2: Create `app/linkedin/http_client.py`

Create file `app/linkedin/http_client.py`:

```python
import httpx
from typing import Optional

class LinkedInHttpClient:
    """HTTP client wrapper for LinkedIn API requests"""
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
    
    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                    keepalive_expiry=30.0
                )
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()

# Singleton instance
http_client = LinkedInHttpClient()
```

## File Map

### Creates
- `app/linkedin/auth.py`
- `app/linkedin/http_client.py`

### Modifies
- Nothing

### Depends On
- Segment 2 (config)
- Segment 4 (endpoints)
- Segment 5 (exceptions)

### Is Used By
- Segment 7 (credential auth)
- Segment 9-12 (API client)

## Verification

```bash
python -c "
import asyncio
from app.linkedin.http_client import LinkedInHttpClient
from app.linkedin.auth import LinkedInAuth

async def test():
    async with LinkedInHttpClient() as http:
        auth = LinkedInAuth(http.client)
        print('Auth module loaded successfully')
        print(f'Has cookie auth: {auth._session is None}')
        
        # Test CSRF extraction
        csrf = auth._extract_csrf_from_jsessionid('ajax:123|ABC-DEF-TOKEN')
        print(f'CSRF extracted: {csrf}')

asyncio.run(test())
"
```

**Expected Output:**
```
Auth module loaded successfully
Has cookie auth: True
CSRF extracted: ABC-DEF-TOKEN
```

## If This Fails

### Symptom: "ModuleNotFoundError: No module named 'httpx'"
**Diagnosis**: httpx not installed
**Fix**:
```bash
pip install httpx
```

### Symptom: "cannot import name 'settings'"
**Diagnosis**: Config module issue
**Fix**: Ensure `app/config.py` exists and has no syntax errors

### Symptom: "AttributeError: 'NoneType' object has no attribute 'client'"
**Diagnosis**: Not using async context manager
**Fix**: Always use `async with LinkedInHttpClient() as http:` pattern

---

# SEGMENT 7: Credential-Based Authentication Fallback

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Cookie auth implemented
This Segment Creates: Credential login fallback
This Segment Depends On: Segment 6
```

## Objective
Add credential-based login as a fallback when cookie auth is unavailable.

## Steps

### Step 7.1: Update `app/linkedin/auth.py`

Modify file `app/linkedin/auth.py` - add these methods to the `LinkedInAuth` class:

```python
    # Add these methods to the LinkedInAuth class
    
    async def get_session(self) -> LinkedInSession:
        """Get a valid session, creating if necessary"""
        if self._session and not self._session.is_expired:
            if await self._verify_session():
                return self._session
        
        # Try cookie-based auth first
        if settings.has_cookie_auth:
            try:
                return await self._create_cookie_session()
            except SessionExpiredError:
                pass  # Fall through to credential auth
        
        # Fall back to credential auth
        if settings.has_credential_auth:
            return await self._login_with_credentials()
        
        raise AuthError(
            "No authentication available. "
            "Set LINKEDIN_LI_AT and LINKEDIN_JSESSIONID in .env, "
            "or configure LINKEDIN_USERNAME and LINKEDIN_PASSWORD."
        )
    
    async def _login_with_credentials(self) -> LinkedInSession:
        """Login using email/password - may trigger CAPTCHA"""
        
        # Step 1: Get initial page to obtain JSESSIONID
        response = await self.client.get(
            f"{endpoints_config.base_url}/",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html",
            }
        )
        
        jsessionid = self._get_cookie(response, "JSESSIONID")
        if not jsessionid:
            raise AuthError("Could not obtain JSESSIONID from initial page load")
        
        csrf_token = self._extract_csrf_from_jsessionid(jsessionid)
        
        # Step 2: Submit login form
        login_response = await self.client.post(
            f"{endpoints_config.base_url}/uas/authenticate",
            headers={
                "X-CSRF-Token": csrf_token,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{endpoints_config.base_url}/",
                "Cookie": f"JSESSIONID={jsessionid}",
            },
            data={
                "session_key": settings.linkedin_username,
                "session_password": settings.linkedin_password,
                "csrfToken": csrf_token,
            },
            follow_redirects=False
        )
        
        # Step 3: Check for success (302 redirect) or failure
        if login_response.status_code != 302:
            if "captcha" in login_response.text.lower():
                raise CaptchaRequiredError(
                    "Login triggered CAPTCHA. Use cookie-based authentication instead. "
                    "Run: python scripts/extract_session.py"
                )
            raise AuthError(
                f"Login failed with status {login_response.status_code}. "
                "Use cookie-based authentication instead."
            )
        
        # Step 4: Extract auth cookies from response
        li_at = self._get_cookie(login_response, "li_at")
        new_jsessionid = self._get_cookie(login_response, "JSESSIONID") or jsessionid
        
        if not li_at:
            raise AuthError("Login appeared to succeed but li_at cookie not received")
        
        # Create and verify session
        new_csrf = self._extract_csrf_from_jsessionid(new_jsessionid)
        session = LinkedInSession(
            li_at=li_at,
            jsessionid=new_jsessionid,
            csrf_token=new_csrf
        )
        
        if await self._verify_session_with(session):
            self._session = session
            return session
        
        raise AuthError("Login succeeded but session verification failed")
    
    def _get_cookie(self, response: httpx.Response, name: str) -> str:
        """Extract cookie value from response"""
        for cookie in response.cookies.jar:
            if cookie.name == name:
                return cookie.value
        return None
```

## File Map

### Creates
- Nothing new

### Modifies
- `app/linkedin/auth.py`

### Depends On
- Segment 6 (base auth module)

### Is Used By
- Same as Segment 6

## Verification

```bash
python -c "
from app.linkedin.auth import LinkedInAuth
from app.linkedin.http_client import LinkedInHttpClient
import asyncio

async def test():
    async with LinkedInHttpClient() as http:
        auth = LinkedInAuth(http.client)
        
        # Test that methods exist
        print('Has _login_with_credentials:', hasattr(auth, '_login_with_credentials'))
        print('Has _get_cookie:', hasattr(auth, '_get_cookie'))
        print('Credential auth module loaded successfully')

asyncio.run(test())
"
```

**Expected Output:**
```
Has _login_with_credentials: True
Has _get_cookie: True
Credential auth module loaded successfully
```

## If This Fails

### Symptom: "NameError: name 'httpx' is not defined"
**Diagnosis**: Missing import
**Fix**: Ensure `import httpx` is at the top of auth.py

### Symptom: Indentation errors after modification
**Diagnosis**: Incorrect indentation when adding methods
**Fix**: Ensure new methods are indented at the same level as existing methods in the class

---

# SEGMENT 8: Session Extraction Script

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Both auth methods implemented
This Segment Creates: Manual cookie extraction script
This Segment Depends On: Segment 0 (.env file)
```

## Objective
Create an interactive script to help users extract cookies from their browser.

## Steps

### Step 8.1: Create `scripts/extract_session.py`

Create file `scripts/extract_session.py`:

```python
#!/usr/bin/env python3
"""
LinkedIn Session Extraction Script

This script helps you extract authentication cookies from your browser
for use with the LinkedIn Profile API.

INSTRUCTIONS:
=============

1. Open Chrome/Firefox and go to https://www.linkedin.com
2. Make sure you are logged in
3. Open Developer Tools (Press F12 or Right-Click > Inspect)
4. Go to the "Application" tab (Chrome) or "Storage" tab (Firefox)
5. In the left sidebar, expand "Cookies" and click "https://www.linkedin.com"
6. Find and copy the values for:
   - li_at
   - JSESSIONID
7. Run this script and paste the values when prompted

NOTES:
======
- li_at cookies typically last ~6 months
- JSESSIONID is used to extract the CSRF token
- If scraping fails with auth errors, re-run this script
- Never share your cookies with anyone
"""

import os
import sys
from pathlib import Path

def get_env_path() -> Path:
    """Get path to .env file"""
    # Try current directory first, then parent directories
    current = Path.cwd()
    for _ in range(3):
        env_path = current / ".env"
        if env_path.exists():
            return env_path
        current = current.parent
    return Path.cwd() / ".env"

def read_existing_env(env_path: Path) -> dict:
    """Read existing .env values"""
    existing = {}
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing[key.strip()] = value.strip()
    return existing

def write_env(env_path: Path, values: dict):
    """Write values to .env file"""
    with open(env_path, 'w') as f:
        for key, value in values.items():
            f.write(f"{key}={value}\n")

def print_header():
    print()
    print("=" * 60)
    print("  LINKEDIN SESSION EXTRACTION")
    print("=" * 60)
    print()

def print_instructions():
    print("STEP-BY-STEP INSTRUCTIONS:")
    print("-" * 60)
    print()
    print("1. Open your browser and go to linkedin.com")
    print("2. Make sure you are LOGGED IN")
    print("3. Open Developer Tools:")
    print("   - Chrome/Edge: Press F12 or Ctrl+Shift+I")
    print("   - Firefox: Press F12 or Ctrl+Shift+I")
    print()
    print("4. Find the Cookies:")
    print("   - Chrome/Edge: Application tab > Cookies > linkedin.com")
    print("   - Firefox: Storage tab > Cookies > linkedin.com")
    print()
    print("5. Find these cookies and COPY their values:")
    print("   >>> li_at")
    print("   >>> JSESSIONID")
    print()
    print("-" * 60)
    print()

def validate_cookie(value: str, name: str) -> bool:
    """Basic cookie validation"""
    if not value or len(value) < 10:
        return False
    if 'example' in value.lower() or 'paste' in value.lower():
        return False
    return True

def main():
    print_header()
    print_instructions()
    
    env_path = get_env_path()
    existing = read_existing_env(env_path)
    
    # Show current status
    has_li_at = bool(existing.get('LINKEDIN_LI_AT'))
    has_jsessionid = bool(existing.get('LINKEDIN_JSESSIONID'))
    
    if has_li_at and has_jsessionid:
        print("Current Status: Cookies already configured")
        update = input("Update them? (y/n): ").strip().lower()
        if update != 'y':
            print("\nKeeping existing cookies. Done!")
            return
    
    print()
    print("Enter the cookie values (paste from browser):")
    print()
    
    # Get li_at
    li_at = input("li_at value: ").strip()
    if not validate_cookie(li_at, 'li_at'):
        print("\n❌ ERROR: Invalid li_at value. Make sure you copied the full cookie value.")
        sys.exit(1)
    
    # Get JSESSIONID
    jsessionid = input("JSESSIONID value: ").strip()
    if not validate_cookie(jsessionid, 'JSESSIONID'):
        print("\n❌ ERROR: Invalid JSESSIONID value. Make sure you copied the full cookie value.")
        sys.exit(1)
    
    # Update existing values
    existing['LINKEDIN_LI_AT'] = li_at
    existing['LINKEDIN_JSESSIONID'] = jsessionid
    
    # Write to .env
    write_env(env_path, existing)
    
    print()
    print("-" * 60)
    print("✅ SUCCESS! Cookies saved to .env file")
    print(f"   Location: {env_path}")
    print()
    print("You can now run the LinkedIn Profile API.")
    print()
    print("⚠️  NOTES:")
    print("   - Sessions typically last ~6 months")
    print("   - If you get auth errors, re-run this script")
    print("   - Never share your .env file or cookies")
    print("-" * 60)
    print()

if __name__ == "__main__":
    main()
```

## File Map

### Creates
- `scripts/extract_session.py`

### Modifies
- Nothing (modifies .env at runtime)

### Depends On
- Segment 0 (.env file)

### Is Used By
- User manually runs this

## Verification

```bash
python scripts/extract_session.py
```

**Expected Output:**
```
============================================================
  LINKEDIN SESSION EXTRACTION
============================================================

STEP-BY-STEP INSTRUCTIONS:
------------------------------------------------------------

1. Open your browser and go to linkedin.com
2. Make sure you are LOGGED IN
3. Open Developer Tools:
   - Chrome/Edge: Press F12 or Ctrl+Shift+I
   - Firefox: Press F12 or Ctrl+Shift+I

4. Find the Cookies:
   - Chrome/Edge: Application tab > Cookies > linkedin.com
   - Firefox: Storage tab > Cookies > linkedin.com

5. Find these cookies and COPY their values:
   >>> li_at
   >>> JSESSIONID

------------------------------------------------------------

Enter the cookie values (paste from browser):

li_at value: [paste here]
JSESSIONID value: [paste here]
```

After entering valid cookies:
```
------------------------------------------------------------
✅ SUCCESS! Cookies saved to .env file
   Location: /path/to/linkedin-api/.env

You can now run the LinkedIn Profile API.

⚠️  NOTES:
   - Sessions typically last ~6 months
   - If you get auth errors, re-run this script
   - Never share your .env file or cookies
------------------------------------------------------------
```

## If This Fails

### Symptom: "Invalid li_at value"
**Diagnosis**: Cookie value too short or contains placeholder text
**Fix**: Ensure you copied the FULL cookie value from browser (often 100+ characters)

### Symptom: ".env file not found"
**Diagnosis**: Running script from wrong directory
**Fix**: Run from the project root directory where .env exists

### Symptom: "Permission denied" writing to .env
**Diagnosis**: File permissions issue
**Fix**:
```bash
chmod 600 .env
```

---

# SEGMENT 9: Profile ID Resolution

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Authentication working
This Segment Creates: URL to internal ID resolver
This Segment Depends On: Segment 4, Segment 5, Segment 6
```

## Objective
Implement the logic to convert a public LinkedIn URL to an internal profile ID by fetching and parsing the profile page HTML.

## Steps

### Step 9.1: Create `app/linkedin/resolver.py`

Create file `app/linkedin/resolver.py`:

```python
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
```

## File Map

### Creates
- `app/linkedin/resolver.py`

### Modifies
- Nothing

### Depends On
- Segment 4 (endpoints config with patterns)
- Segment 5 (exceptions)
- Segment 6 (http client, auth headers)

### Is Used By
- Segment 12 (full client)

## Verification

```bash
python -c "
from app.linkedin.resolver import ProfileResolver

# Test URL normalization
resolver = ProfileResolver(None, None)

tests = [
    ('https://www.linkedin.com/in/johndoe/', 'https://www.linkedin.com/in/johndoe'),
    ('//www.linkedin.com/in/janedoe', 'https://www.linkedin.com/in/janedoe'),
    ('http://linkedin.com/in/bobsmith', 'https://www.linkedin.com/in/bobsmith'),
    ('/in/alicewonderland/', 'https://www.linkedin.com/in/alicewonderland'),
]

print('URL Normalization Tests:')
for input_url, expected in tests:
    result = resolver.normalize_url(input_url)
    status = '✓' if result == expected else '✗'
    print(f'  {status} {input_url[:40]:40} -> {result}')
"
```

**Expected Output:**
```
URL Normalization Tests:
  ✓ https://www.linkedin.com/in/johndoe/    -> https://www.linkedin.com/in/johndoe
  ✓ //www.linkedin.com/in/janedoe           -> https://www.linkedin.com/in/janedoe
  ✓ http://linkedin.com/in/bobsmith         -> https://www.linkedin.com/in/bobsmith
  ✓ /in/alicewonderland/                   -> https://www.linkedin.com/in/alicewonderland
```

## If This Fails

### Symptom: URL normalization tests fail
**Diagnosis**: Logic error in normalize_url
**Fix**: Check the order of conditions - protocol-relative URLs (//) must be handled before relative paths (/)

### Symptom: Import error
**Diagnosis**: Missing dependencies
**Fix**: Ensure `app/linkedin/endpoints.py` and `app/linkedin/exceptions.py` exist

---

# SEGMENT 10: Single REST Endpoint Client

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Profile ID resolution working
This Segment Creates: Basic REST API client
This Segment Depends On: Segment 4, Segment 5, Segment 6
```

## Objective
Create a client that can make authenticated requests to a single LinkedIn REST endpoint.

## Steps

### Step 10.1: Create `app/linkedin/rest_client.py`

Create file `app/linkedin/rest_client.py`:

```python
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
```

## File Map

### Creates
- `app/linkedin/rest_client.py`

### Modifies
- Nothing

### Depends On
- Segment 4 (endpoints)
- Segment 5 (exceptions)
- Segment 6 (http client)

### Is Used By
- Segment 12 (full client)

## Verification

```bash
python -c "
from app.linkedin.rest_client import LinkedInRESTClient

# Test that class loads and has correct methods
print('LinkedInRESTClient loaded')
print('Has get method:', hasattr(LinkedInRESTClient, 'get'))
print('Has _handle_response method:', hasattr(LinkedInRESTClient, '_handle_response'))
print('REST client module ready')
"
```

**Expected Output:**
```
LinkedInRESTClient loaded
Has get method: True
Has _handle_response method: True
REST client module ready
```

## If This Fails

### Symptom: Import errors
**Diagnosis**: Dependencies not in place
**Fix**: Ensure segments 4, 5, 6 are complete

---

# SEGMENT 11: GraphQL Client

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: REST client working
This Segment Creates: GraphQL client
This Segment Depends On: Segment 4, Segment 5, Segment 6
```

## Objective
Create a client for LinkedIn's GraphQL endpoint that can fetch comprehensive profile data in a single request.

## Steps

### Step 11.1: Create `app/linkedin/graphql_client.py`

Create file `app/linkedin/graphql_client.py`:

```python
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
```

## File Map

### Creates
- `app/linkedin/graphql_client.py`

### Modifies
- Nothing

### Depends On
- Segment 4 (endpoints with GraphQL query)
- Segment 5 (exceptions)
- Segment 6 (http client)

### Is Used By
- Segment 12 (full client)

## Verification

```bash
python -c "
from app.linkedin.graphql_client import LinkedInGraphQLClient
from app.linkedin.endpoints import endpoints_config

# Verify GraphQL config is loaded
print('GraphQL endpoint:', endpoints_config.graphql_endpoint)
print('Query length:', len(endpoints_config.full_profile_query), 'chars')
print('Decoration ID:', endpoints_config.full_profile_decoration_id)
print()
print('GraphQL client module ready')
"
```

**Expected Output:**
```
GraphQL endpoint: /voyager/api/graphql
Query length: 847 chars
Decoration ID: com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-28

GraphQL client module ready
```

## If This Fails

### Symptom: "Query length: 0 chars"
**Diagnosis**: YAML not loading correctly or query field empty
**Fix**: Check `config/linkedin_endpoints.yaml` has the `graphql.profile_full_query` field with content

### Symptom: "Decoration ID: None"
**Diagnosis**: Missing decoration_id in config
**Fix**: Add `decoration_ids.full_profile` to the YAML file

---

# SEGMENT 12: Unified LinkedIn Client

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: REST and GraphQL clients ready
This Segment Creates: Unified client orchestrating all components
This Segment Depends On: Segment 6, 7, 9, 10, 11
```

## Objective
Create a unified client that combines authentication, profile resolution, and data fetching with GraphQL-primary/REST-fallback strategy.

## Steps

### Step 12.1: Create `app/linkedin/client.py`

Create file `app/linkedin/client.py`:

```python
import asyncio
from typing import Dict, Any, Optional, List
import httpx
from app.linkedin.http_client import LinkedInHttpClient
from app.linkedin.auth import LinkedInAuth
from app.linkedin.resolver import ProfileResolver
from app.linkedin.rest_client import LinkedInRESTClient
from app.linkedin.graphql_client import LinkedInGraphQLClient
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
    
    async def __aenter__(self):
        self._http = LinkedInHttpClient()
        http_client = await self._http.get_client()
        
        self._auth = LinkedInAuth(http_client)
        await self._auth.get_session()  # Ensure authenticated
        
        auth_headers = self._auth.get_auth_headers()
        
        self._resolver = ProfileResolver(http_client, auth_headers)
        self._rest_client = LinkedInRESTClient(http_client, auth_headers)
        self._graphql_client = LinkedInGraphQLClient(http_client, auth_headers)
        
        return self
    
    async def __aexit__(self, *args):
        if self._http:
            await self._http.close()
    
    async def resolve_profile_id(self, public_url: str) -> str:
        """Convert public URL to internal profile ID"""
        return await self._resolver.resolve_profile_id(public_url)
    
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
```

### Step 12.2: Update `app/linkedin/__init__.py`

Update file `app/linkedin/__init__.py`:

```python
from app.linkedin.client import LinkedInClient
from app.linkedin.exceptions import (
    LinkedInError,
    AuthError,
    SessionExpiredError,
    CaptchaRequiredError,
    ProfileNotFoundError,
    RateLimitError,
    ProfileIdResolutionError,
    GraphQLQueryError,
    RESTEndpointError,
    PartialDataError,
)

__all__ = [
    "LinkedInClient",
    "LinkedInError",
    "AuthError",
    "SessionExpiredError",
    "CaptchaRequiredError",
    "ProfileNotFoundError",
    "RateLimitError",
    "ProfileIdResolutionError",
    "GraphQLQueryError",
    "RESTEndpointError",
    "PartialDataError",
]
```

## File Map

### Creates
- `app/linkedin/client.py`

### Modifies
- `app/linkedin/__init__.py`

### Depends On
- Segments 6, 7, 9, 10, 11

### Is Used By
- Segment 15 (scraper service)
- Segment 19 (worker)

## Verification

```bash
python -c "
import asyncio
from app.linkedin.client import LinkedInClient

async def test():
    # Test that client can be instantiated (won't actually connect)
    print('Creating client context...')
    # We can't fully test without valid credentials, but verify structure
    print('LinkedInClient has resolve_profile_id:', hasattr(LinkedInClient, 'resolve_profile_id'))
    print('LinkedInClient has get_profile_graphql:', hasattr(LinkedInClient, 'get_profile_graphql'))
    print('LinkedInClient has get_profile_rest:', hasattr(LinkedInClient, 'get_profile_rest'))
    print('LinkedInClient has invalidate_session:', hasattr(LinkedInClient, 'invalidate_session'))
    print()
    print('✓ Unified client module ready')

asyncio.run(test())
"
```

**Expected Output:**
```
Creating client context...
LinkedInClient has resolve_profile_id: True
LinkedInClient has get_profile_graphql: True
LinkedInClient has get_profile_rest: True
LinkedInClient has invalidate_session: True

✓ Unified client module ready
```

## If This Fails

### Symptom: Import errors for submodules
**Diagnosis**: Previous segments not complete
**Fix**: Go back and complete segments 6-11

### Symptom: "cannot import name 'LinkedInHttpClient'"
**Diagnosis**: http_client.py not created
**Fix**: Complete Segment 6

---

# SEGMENT 13: Response Parsers - Profile Data

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Client can fetch raw data
This Segment Creates: Parsers for profile basic info
This Segment Depends On: Segment 3 (models)
```

## Objective
Create parsers that transform raw LinkedIn API responses into clean, normalized data structures.

## Steps

### Step 13.1: Create `app/linkedin/parsers.py`

Create file `app/linkedin/parsers.py`:

```python
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

class ProfileParser:
    """Parses LinkedIn API responses into clean, normalized format"""
    
    def parse_graphql_profile(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse profile data from GraphQL response"""
        profile = data.get('data', {}).get('profile', {})
        
        return {
            "url": None,  # Not in GraphQL response, add later
            "internal_id": None,  # Add later from context
            "first_name": profile.get('firstName', ''),
            "last_name": profile.get('lastName', ''),
            "full_name": self._make_full_name(
                profile.get('firstName'), 
                profile.get('lastName')
            ),
            "headline": profile.get('headline', ''),
            "about": self._clean_html(profile.get('summary', '')),
            "location": self._parse_graphql_location(profile.get('location')),
            "profile_image_url": self._parse_graphql_image(profile.get('profilePicture')),
            "background_image_url": self._parse_graphql_image(profile.get('backgroundImage')),
            "connections": None,  # Not in standard GraphQL response
        }
    
    def parse_rest_profile(self, profile_data: Dict, profile_ext_data: Dict, picture_data: Dict) -> Dict[str, Any]:
        """Parse profile data from REST endpoints"""
        
        return {
            "url": None,  # Add from context
            "internal_id": None,  # Add from context
            "first_name": profile_data.get('firstName', ''),
            "last_name": profile_data.get('lastName', ''),
            "full_name": profile_ext_data.get('fullName', ''),
            "headline": profile_ext_data.get('headline', ''),
            "about": self._clean_html(profile_ext_data.get('summary', '')),
            "location": self._parse_rest_location(profile_ext_data.get('location', {})),
            "profile_image_url": self._parse_rest_picture(picture_data),
            "background_image_url": None,
            "connections": profile_ext_data.get('connections', ''),
        }
    
    def _parse_graphql_location(self, location: Optional[Dict]) -> Optional[Dict]:
        if not location:
            return None
        return {
            "name": location.get('name', ''),
            "country": location.get('country', {}).get('code', '') if location.get('country') else None,
        }
    
    def _parse_rest_location(self, location: Dict) -> Optional[Dict]:
        if not location:
            return None
        return {
            "name": location.get('name', ''),
            "country": location.get('country', ''),
        }
    
    def _parse_graphql_image(self, image_data: Optional[Dict]) -> Optional[str]:
        """Extract image URL from GraphQL image structure"""
        if not image_data:
            return None
        
        display_image = image_data.get('displayImage', image_data)
        elements = display_image.get('elements', [])
        
        if elements:
            # Get largest image (last element)
            largest = elements[-1]
            root_url = largest.get('rootUrl', '')
            identifier = largest.get('identifier', '')
            if root_url and identifier:
                return f"{root_url}{identifier}"
        
        return None
    
    def _parse_rest_picture(self, picture_data: Dict) -> Optional[str]:
        """Extract profile picture URL from REST picture endpoint response"""
        if not picture_data or 'error' in str(picture_data):
            return None
        
        # Handle different response formats
        if isinstance(picture_data, dict):
            # Try nested structure
            profile_pic = picture_data.get('profilePicture', picture_data)
            display_image = profile_pic.get('displayImage', {})
            elements = display_image.get('elements', [])
            
            if elements:
                largest = elements[-1]
                identifiers = largest.get('identifiers', [])
                if identifiers:
                    return identifiers[0].get('identifier', '')
            
            # Try direct URL
            return picture_data.get('url') or picture_data.get('artifact')
        
        return None
    
    def _make_full_name(self, first: Optional[str], last: Optional[str]) -> str:
        parts = [p for p in [first, last] if p]
        return ' '.join(parts)
    
    def _clean_html(self, text: Optional[str]) -> str:
        """Remove HTML tags and clean up whitespace"""
        if not text:
            return ''
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
```

## File Map

### Creates
- `app/linkedin/parsers.py`

### Modifies
- Nothing

### Depends On
- Segment 3 (response models for reference)

### Is Used By
- Segment 14 (experience/education parsers)
- Segment 15 (scraper service)

## Verification

```bash
python -c "
from app.linkedin.parsers import ProfileParser

parser = ProfileParser()

# Test GraphQL parsing
graphql_data = {
    'data': {
        'profile': {
            'firstName': 'John',
            'lastName': 'Doe',
            'headline': 'Senior Engineer at Google',
            'summary': '<p>Passionate about building <strong>scalable systems</strong></p>',
            'location': {'name': 'Mountain View, CA', 'country': {'code': 'US'}},
            'profilePicture': {
                'displayImage': {
                    'elements': [
                        {'rootUrl': 'https://media.licdn.com/', 'identifier': 'small.jpg'},
                        {'rootUrl': 'https://media.licdn.com/', 'identifier': 'large.jpg'}
                    ]
                }
            }
        }
    }
}

result = parser.parse_graphql_profile(graphql_data)
print('First Name:', result['first_name'])
print('Full Name:', result['full_name'])
print('Headline:', result['headline'])
print('About (cleaned):', result['about'])
print('Location:', result['location'])
print('Profile Image:', result['profile_image_url'])
"
```

**Expected Output:**
```
First Name: John
Full Name: John Doe
Headline: Senior Engineer at Google
About (cleaned): Passionate about building scalable systems
Location: {'name': 'Mountain View, CA', 'country': 'US'}
Profile Image: https://media.licdn.com/large.jpg
```

## If This Fails

### Symptom: "About (cleaned): <p>Passionate..."
**Diagnosis**: HTML cleaning not working
**Fix**: Check that `_clean_html` method is called and the regex is correct

### Symptom: "Profile Image: None"
**Diagnosis**: Image parsing logic issue
**Fix**: Debug by printing intermediate values in `_parse_graphql_image`

---

# SEGMENT 14: Response Parsers - Experience, Education, Skills

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Profile parser working
This Segment Creates: Parsers for all sections
This Segment Depends On: Segment 13
```

## Objective
Add parsers for experience, education, skills, certifications, and languages.

## Steps

### Step 14.1: Add methods to `app/linkedin/parsers.py`

Add these methods to the `ProfileParser` class in `app/linkedin/parsers.py`:

```python
    # Add these methods to ProfileParser class
    
    def parse_graphql_positions(self, data: Dict[str, Any]) -> List[Dict]:
        """Parse experience/positions from GraphQL response"""
        positions = data.get('data', {}).get('profile', {}).get('positions', {})
        elements = positions.get('elements', [])
        
        results = []
        for pos in elements:
            results.append({
                "title": pos.get('title', ''),
                "company": {
                    "name": pos.get('companyName', ''),
                    "url": self._urn_to_company_url(pos.get('companyUrn')),
                    "logo_url": self._parse_graphql_image(
                        pos.get('companyLogo', {}).get('image') if pos.get('companyLogo') else None
                    ),
                },
                "location": pos.get('locationName', ''),
                "dates": {
                    "start": self._parse_graphql_date(pos.get('startDate')),
                    "end": self._parse_graphql_date(pos.get('endDate')),
                    "is_current": pos.get('endDate') is None,
                },
                "description": self._clean_html(pos.get('description', '')),
            })
        
        return results
    
    def parse_rest_positions(self, positions_data: Dict) -> List[Dict]:
        """Parse positions from REST endpoint"""
        if not positions_data:
            return []
        
        elements = positions_data.get('elements', [])
        results = []
        
        for pos in elements:
            results.append({
                "title": pos.get('title', ''),
                "company": {
                    "name": pos.get('companyName', ''),
                    "url": self._urn_to_company_url(pos.get('companyUrn')),
                },
                "location": pos.get('locationName', ''),
                "dates": {
                    "start": self._parse_rest_date(pos.get('startDate')),
                    "end": self._parse_rest_date(pos.get('endDate')),
                    "is_current": pos.get('endDate') is None,
                },
                "description": self._clean_html(pos.get('description', '')),
            })
        
        return results
    
    def parse_graphql_education(self, data: Dict[str, Any]) -> List[Dict]:
        """Parse education from GraphQL response"""
        education = data.get('data', {}).get('profile', {}).get('educations', {})
        elements = education.get('elements', [])
        
        results = []
        for edu in elements:
            results.append({
                "institution": {
                    "name": edu.get('schoolName', ''),
                    "url": self._urn_to_school_url(edu.get('schoolUrn')),
                },
                "degree": edu.get('degreeName', ''),
                "field_of_study": edu.get('fieldOfStudy', ''),
                "dates": {
                    "start": self._parse_graphql_date(edu.get('startDate')),
                    "end": self._parse_graphql_date(edu.get('endDate')),
                },
                "description": self._clean_html(edu.get('description', '')),
            })
        
        return results
    
    def parse_rest_education(self, education_data: Dict) -> List[Dict]:
        """Parse education from REST endpoint"""
        if not education_data:
            return []
        
        elements = education_data.get('elements', [])
        results = []
        
        for edu in elements:
            results.append({
                "institution": {
                    "name": edu.get('schoolName', ''),
                    "url": self._urn_to_school_url(edu.get('schoolUrn')),
                },
                "degree": edu.get('degreeName', ''),
                "field_of_study": edu.get('fieldOfStudy', ''),
                "dates": {
                    "start": self._parse_rest_date(edu.get('startDate')),
                    "end": self._parse_rest_date(edu.get('endDate')),
                },
                "description": self._clean_html(edu.get('description', '')),
            })
        
        return results
    
    def parse_graphql_skills(self, data: Dict[str, Any]) -> List[Dict]:
        """Parse skills from GraphQL response"""
        skills = data.get('data', {}).get('profile', {}).get('skills', {})
        elements = skills.get('elements', [])
        
        return [
            {
                "name": s.get('name', ''),
                "endorsement_count": s.get('endorsementCount', 0),
            }
            for s in elements
        ]
    
    def parse_rest_skills(self, skills_data: Dict) -> List[Dict]:
        """Parse skills from REST endpoint"""
        if not skills_data:
            return []
        
        elements = skills_data.get('elements', [])
        return [
            {
                "name": s.get('name', ''),
                "endorsement_count": s.get('endorsementCount', 0),
            }
            for s in elements
        ]
    
    def parse_graphql_certifications(self, data: Dict[str, Any]) -> List[Dict]:
        """Parse certifications from GraphQL response"""
        certs = data.get('data', {}).get('profile', {}).get('certifications', {})
        elements = certs.get('elements', [])
        
        return [
            {
                "name": c.get('name', ''),
                "issuer": c.get('authority', ''),
                "issue_date": self._parse_graphql_date(c.get('start')),
                "expiry_date": self._parse_graphql_date(c.get('end')),
                "credential_id": c.get('licenseNumber', ''),
            }
            for c in elements
        ]
    
    def parse_rest_certifications(self, certs_data: Dict) -> List[Dict]:
        """Parse certifications from REST endpoint"""
        if not certs_data:
            return []
        
        elements = certs_data.get('elements', [])
        return [
            {
                "name": c.get('name', ''),
                "issuer": c.get('authority', ''),
                "issue_date": self._parse_rest_date(c.get('start')),
                "expiry_date": self._parse_rest_date(c.get('end')),
                "credential_id": c.get('licenseNumber', ''),
            }
            for c in elements
        ]
    
    def parse_graphql_languages(self, data: Dict[str, Any]) -> List[Dict]:
        """Parse languages from GraphQL response"""
        langs = data.get('data', {}).get('profile', {}).get('languages', {})
        elements = langs.get('elements', [])
        
        return [
            {
                "name": l.get('name', ''),
                "proficiency": l.get('proficiency', ''),
            }
            for l in elements
        ]
    
    def parse_rest_languages(self, langs_data: Dict) -> List[Dict]:
        """Parse languages from REST endpoint"""
        if not langs_data:
            return []
        
        elements = langs_data.get('elements', [])
        return [
            {
                "name": l.get('name', ''),
                "proficiency": l.get('proficiency', ''),
            }
            for l in elements
        ]
    
    # === Helper Methods ===
    
    def _parse_graphql_date(self, date_obj: Optional[Dict]) -> Optional[Dict]:
        """Parse GraphQL date object {year, month}"""
        if not date_obj:
            return None
        return {
            "year": date_obj.get('year'),
            "month": date_obj.get('month'),
        }
    
    def _parse_rest_date(self, date_obj: Optional[Dict]) -> Optional[Dict]:
        """Parse REST date object"""
        if not date_obj:
            return None
        return {
            "year": date_obj.get('year'),
            "month": date_obj.get('month'),
        }
    
    def _urn_to_company_url(self, urn: Optional[str]) -> Optional[str]:
        """Convert company URN to URL"""
        if not urn:
            return None
        # URN format: urn:li:fsd_company:12345 or urn:li:organization:12345
        parts = urn.split(':')
        if len(parts) >= 4:
            return f"https://www.linkedin.com/company/{parts[-1]}/"
        return None
    
    def _urn_to_school_url(self, urn: Optional[str]) -> Optional[str]:
        """Convert school URN to URL"""
        if not urn:
            return None
        parts = urn.split(':')
        if len(parts) >= 4:
            return f"https://www.linkedin.com/school/{parts[-1]}/"
        return None
```

## File Map

### Creates
- Nothing new

### Modifies
- `app/linkedin/parsers.py`

### Depends On
- Segment 13 (base parser)

### Is Used By
- Segment 15 (scraper service)

## Verification

```bash
python -c "
from app.linkedin.parsers import ProfileParser

parser = ProfileParser()

# Test positions parsing
graphql_data = {
    'data': {
        'profile': {
            'positions': {
                'elements': [
                    {
                        'title': 'Senior Engineer',
                        'companyName': 'Google',
                        'companyUrn': 'urn:li:fsd_company:1441',
                        'locationName': 'Mountain View, CA',
                        'startDate': {'year': 2020, 'month': 1},
                        'endDate': None,
                        'description': '<p>Built scalable systems</p>'
                    }
                ]
            }
        }
    }
}

positions = parser.parse_graphql_positions(graphql_data)
print('Positions count:', len(positions))
if positions:
    p = positions[0]
    print('Title:', p['title'])
    print('Company:', p['company']['name'])
    print('Company URL:', p['company']['url'])
    print('Is Current:', p['dates']['is_current'])
    print('Description (cleaned):', p['description'])
"
```

**Expected Output:**
```
Positions count: 1
Title: Senior Engineer
Company: Google
Company URL: https://www.linkedin.com/company/1441/
Is Current: True
Description (cleaned): Built scalable systems
```

## If This Fails

### Symptom: "Positions count: 0"
**Diagnosis**: Path to elements incorrect
**Fix**: Check the data structure - might be `data.profile.positions` not `data.data.profile.positions`

### Symptom: "Company URL: None"
**Diagnosis**: URN parsing failing
**Fix**: Debug `_urn_to_company_url` with the actual URN value

---

# SEGMENT 15: Cache Service

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Parsers complete
This Segment Creates: Cache layer using PostgreSQL
This Segment Depends On: Segment 1 (database), Segment 2 (config)
```

## Objective
Implement a cache service that stores and retrieves profile data in PostgreSQL with TTL-based expiration.

## Steps

### Step 15.1: Create `app/services/cache_service.py`

Create file `app/services/cache_service.py`:

```python
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
```

## File Map

### Creates
- `app/services/cache_service.py`

### Modifies
- Nothing

### Depends On
- Segment 1 (ProfileCache model)
- Segment 2 (settings)

### Is Used By
- Segment 16 (scraper service)
- Segment 19 (worker)

## Verification

```bash
python -c "
import asyncio
from app.db.connection import async_session, init_db
from app.services.cache_service import CacheService

async def test():
    await init_db()
    
    cache = CacheService(ttl_hours=1)
    
    async with async_session() as session:
        # Test set
        print('Testing cache set...')
        await cache.set(session, 'https://linkedin.com/in/test', {'name': 'Test User'})
        print('✓ Set successful')
        
        # Test get
        print('Testing cache get...')
        data = await cache.get(session, 'https://linkedin.com/in/test')
        print(f'✓ Get successful: {data}')
        
        # Test miss
        print('Testing cache miss...')
        miss = await cache.get(session, 'https://linkedin.com/in/nonexistent')
        print(f'✓ Miss returns None: {miss is None}')
        
        # Test cleanup
        print('Testing cleanup...')
        count = await cache.cleanup_expired(session)
        print(f'✓ Cleanup complete: {count} expired entries removed')

asyncio.run(test())
"
```

**Expected Output:**
```
Testing cache set...
✓ Set successful
Testing cache get...
✓ Get successful: {'name': 'Test User'}
Testing cache miss...
✓ Miss returns None: True
Testing cleanup...
✓ Cleanup complete: 0 expired entries removed
```

## If This Fails

### Symptom: "ForeignKeyViolation" or similar
**Diagnosis**: Table doesn't exist
**Fix**: Run `python scripts/init_db.py`

### Symptom: "AttributeError: 'CacheService' object has no attribute"
**Diagnosis**: Method name typo
**Fix**: Check method names match the interface

### Symptom: Data not persisting
**Diagnosis**: Missing commit
**Fix**: Ensure `await session.commit()` is called

---

# SEGMENT 16: Job Queue Service

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Cache service working
This Segment Creates: Job queue management
This Segment Depends On: Segment 1 (Job model), Segment 2 (config)
```

## Objective
Implement job queue operations using PostgreSQL as the backing store.

## Steps

### Step 16.1: Create `app/services/job_service.py`

Create file `app/services/job_service.py`:

```python
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
```

## File Map

### Creates
- `app/services/job_service.py`

### Modifies
- Nothing

### Depends On
- Segment 1 (Job model)
- Segment 2 (config)

### Is Used By
- Segment 17 (FastAPI routes)
- Segment 19 (worker)

## Verification

```bash
python -c "
import asyncio
from app.db.connection import async_session, init_db
from app.services.job_service import JobService

async def test():
    await init_db()
    
    job_service = JobService()
    
    async with async_session() as session:
        # Create job
        print('Creating job...')
        job_id = await job_service.create(
            session,
            url='https://linkedin.com/in/test',
            webhook_url='https://example.com/webhook'
        )
        print(f'✓ Job created: {job_id}')
        
        # Get job
        print('Getting job...')
        job = await job_service.get(session, job_id)
        print(f'✓ Job status: {job.status}')
        
        # Get next queued
        print('Getting next queued...')
        next_job = await job_service.get_next_queued(session)
        print(f'✓ Next queued: {next_job.id if next_job else None}')
        
        # Start processing
        print('Starting processing...')
        started = await job_service.start_processing(session, job_id)
        print(f'✓ Started: {started}')
        
        # Complete job
        print('Completing job...')
        await job_service.complete(
            session, job_id,
            result={'name': 'Test'},
            duration_ms=1000,
            from_cache=False
        )
        print('✓ Job completed')
        
        # Get queue depth
        depth = await job_service.get_queue_depth(session)
        print(f'✓ Queue depth: {depth}')

asyncio.run(test())
"
```

**Expected Output:**
```
Creating job...
✓ Job created: [uuid]
Getting job...
✓ Job status: queued
Getting next queued...
✓ Next queued: [uuid]
Starting processing...
✓ Started: True
Completing job...
✓ Job completed
✓ Queue depth: 0
```

## If This Fails

### Symptom: "IntegrityError: duplicate key"
**Diagnosis**: Job ID collision (unlikely with UUID)
**Fix**: Ensure uuid4() is being used

### Symptom: "start_processing returns False"
**Diagnosis**: Job not in 'queued' status
**Fix**: Check job wasn't already started by another process

---

# SEGMENT 17: Scraper Service (Orchestration)

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: Cache and job services ready
This Segment Creates: Main orchestration service
This Segment Depends On: Segments 12, 13, 14, 15, 16
```

## Objective
Create the scraper service that orchestrates the complete profile scraping flow.

## Steps

### Step 17.1: Create `app/services/scraper_service.py`

Create file `app/services/scraper_service.py`:

```python
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
```

## File Map

### Creates
- `app/services/scraper_service.py`

### Modifies
- Nothing

### Depends On
- Segments 12, 13, 14, 15, 16

### Is Used By
- Segment 19 (worker)

## Verification

```bash
python -c "
from app.services.scraper_service import ScraperService

service = ScraperService()
print('ScraperService created')
print('Has scrape_profile:', hasattr(service, 'scrape_profile'))
print('Has _do_scrape:', hasattr(service, '_do_scrape'))
print('Has _parse_graphql_response:', hasattr(service, '_parse_graphql_response'))
print('Has _parse_rest_response:', hasattr(service, '_parse_rest_response'))
print()
print('✓ Scraper service module ready')
"
```

**Expected Output:**
```
ScraperService created
Has scrape_profile: True
Has _do_scrape: True
Has _parse_graphql_response: True
Has _parse_rest_response: True

✓ Scraper service module ready
```

## If This Fails

### Symptom: Import errors
**Diagnosis**: Dependencies not complete
**Fix**: Complete segments 12-16 first

---

# SEGMENT 18: FastAPI Application Setup

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: All services ready
This Segment Creates: FastAPI app with dependencies
This Segment Depends On: Segments 1, 2, 16
```

## Objective
Create the FastAPI application with database session dependency and basic setup.

## Steps

### Step 18.1: Create `app/dependencies.py`

Create file `app/dependencies.py`:

```python
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
```

### Step 18.2: Create `app/main.py`

Create file `app/main.py`:

```python
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.connection import init_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events"""
    logger.info("Starting LinkedIn Profile API...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down LinkedIn Profile API...")

app = FastAPI(
    title="LinkedIn Profile API",
    description="API for scraping LinkedIn profile data",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}}
    )

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

# Import and include routes
from app.api.routes import router as scrape_router
app.include_router(scrape_router, prefix="/api/v1")
```

### Step 18.3: Create `app/api/routes.py`

Create file `app/api/routes.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional

from app.models.requests import ScrapeRequest
from app.models.responses import (
    JobAcceptedResponse,
    JobStatusResponse,
    JobCompletedResponse,
    JobErrorResponse,
    ErrorResponse,
)
from app.dependencies import get_db, verify_api_key
from app.services.job_service import JobService

router = APIRouter(tags=["scrape"])

@router.post(
    "/scrape",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Invalid API key"},
        429: {"model": ErrorResponse, "description": "Rate limited"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    }
)
async def create_scrape_job(
    request: ScrapeRequest,
    db=Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Submit a LinkedIn profile URL for scraping"""
    job_service = JobService()
    
    # Create job
    job_id = await job_service.create(
        db,
        url=request.profile_url,
        webhook_url=request.webhook_url,
        include_fields=request.include_fields
    )
    
    # Get estimated wait time
    queue_depth = await job_service.get_queue_depth(db)
    estimated_wait = queue_depth * 5  # ~5 seconds per job estimate
    
    return JobAcceptedResponse(
        job_id=job_id,
        status="queued",
        estimated_wait_seconds=estimated_wait,
        poll_url=f"/api/v1/scrape/{job_id}"
    )

@router.get(
    "/scrape/{job_id}",
    responses={
        200: {"description": "Job status or result"},
        401: {"model": ErrorResponse, "description": "Invalid API key"},
        404: {"model": ErrorResponse, "description": "Job not found"},
    }
)
async def get_scrape_status(
    job_id: str,
    db=Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Get the status and result of a scrape job"""
    job_service = JobService()
    
    job = await job_service.get(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "JOB_NOT_FOUND", "message": f"Job {job_id} not found"}}
        )
    
    job_dict = job_service.to_dict(job)
    
    if job.status == "completed":
        return JobCompletedResponse(
            job_id=job.id,
            status=job.status,
            duration_ms=job.duration_ms or 0,
            data=job.result or {},
            scraped_at=job_dict.get("updated_at"),
            from_cache=job.from_cache or False
        )
    elif job.status == "failed":
        return JobErrorResponse(
            job_id=job.id,
            status=job.status,
            error={
                "code": job.error_code or "UNKNOWN",
                "message": job.error_message or "Unknown error"
            }
        )
    else:
        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            created_at=job_dict.get("created_at")
        )
```

## File Map

### Creates
- `app/dependencies.py`
- `app/main.py`
- `app/api/routes.py`

### Modifies
- Nothing

### Depends On
- Segments 1, 2, 3, 16

### Is Used By
- Segment 20 (Docker testing)

## Verification

### Step 1: Start PostgreSQL

```bash
docker-compose up -d postgres
```

### Step 2: Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

### Step 3: Test health endpoint (in another terminal)

```bash
curl http://localhost:8000/health
```

**Expected Output:**
```json
{"status":"healthy","version":"1.0.0"}
```

### Step 4: Test API without key (should fail)

```bash
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{"profile_url": "https://www.linkedin.com/in/test/"}'
```

**Expected Output:**
```json
{"detail":"Invalid or missing API key"}
```

### Step 5: Test with invalid URL

```bash
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-this-key" \
  -d '{"profile_url": "https://google.com"}'
```

**Expected Output:**
```json
{"detail":[{"type":"value_error","loc":["body","profile_url"],"msg":"Value error, Invalid LinkedIn profile URL. Expected format: https://www.linkedin.com/in/username","input":"https://google.com"}]}
```

### Step 6: Test valid job creation

```bash
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-this-key" \
  -d '{"profile_url": "https://www.linkedin.com/in/johndoe/"}'
```

**Expected Output:**
```json
{
  "job_id": "[uuid]",
  "status": "queued",
  "estimated_wait_seconds": 0,
  "poll_url": "/api/v1/scrape/[uuid]"
}
```

## If This Fails

### Symptom: "ModuleNotFoundError: No module named 'fastapi'"
**Diagnosis**: FastAPI not installed
**Fix**:
```bash
pip install fastapi uvicorn
```

### Symptom: "Address already in use"
**Diagnosis**: Port 8000 in use
**Fix**: Kill existing process or use different port: `uvicorn app.main:app --port 8001`

### Symptom: "sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres.asyncpg"
**Diagnosis**: Wrong DATABASE_URL format
**Fix**: Ensure DATABASE_URL starts with `postgresql+asyncpg://`

### Symptom: Import error for routes
**Diagnosis**: Circular import or missing module
**Fix**: Ensure all files in `app/api/` and `app/services/` exist

---

# SEGMENT 19: Background Worker

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: API working
This Segment Creates: Background worker process
This Segment Depends On: Segments 15, 16, 17
```

## Objective
Create the background worker that processes jobs from the queue.

## Steps

### Step 19.1: Create `app/workers/main.py`

Create file `app/workers/main.py`:

```python
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
```

## File Map

### Creates
- `app/workers/main.py`

### Modifies
- Nothing

### Depends On
- Segments 15, 16, 17

### Is Used By
- Docker (worker container)

## Verification

### Step 1: Start PostgreSQL

```bash
docker-compose up -d postgres
```

### Step 2: Start worker (in one terminal)

```bash
python -m app.workers.main
```

**Expected Output:**
```
2024-01-15 10:00:00 - root - INFO - Worker starting...
2024-01-15 10:00:00 - root - INFO - Database initialized
```

Worker should keep running, polling for jobs.

### Step 3: Submit a test job (in another terminal)

```bash
python -c "
import asyncio
from app.db.connection import async_session, init_db
from app.services.job_service import JobService

async def test():
    await init_db()
    async with async_session() as session:
        job_service = JobService()
        job_id = await job_service.create(session, 'https://linkedin.com/in/testuser/')
        print(f'Created job: {job_id}')

asyncio.run(test())
"
```

### Step 4: Check worker logs

Worker should show:
```
2024-01-15 10:00:05 - root - INFO - Processing job [uuid]: https://linkedin.com/in/testuser/
```

Job will fail (no valid auth), but this proves the worker is picking up jobs.

### Step 5: Stop worker with Ctrl+C

**Expected Output:**
```
2024-01-15 10:00:10 - root - INFO - Shutdown signal received...
2024-01-15 10:00:10 - root - INFO - Worker stopped
```

## If This Fails

### Symptom: "Worker starting..." but no "Database initialized"
**Diagnosis**: Database connection failing
**Fix**: Ensure PostgreSQL is running and DATABASE_URL is correct

### Symptom: Worker picks up job but crashes
**Diagnosis**: Scraper service error
**Fix**: Check the specific error in logs, likely authentication issue

### Symptom: "Job already being processed" loop
**Diagnosis**: Job stuck in 'processing' state
**Fix**: Manually update job status in database:
```bash
docker-compose exec postgres psql -U linkedin -d linkedin_api -c "UPDATE jobs SET status='queued' WHERE status='processing';"
```

---

# SEGMENT 20: Docker Deployment & End-to-End Testing

## Context Card
```
Architecture: Async queue, PostgreSQL-backed, no browser
Auth Strategy: Cookie-primary, credential-fallback
Data Source: GraphQL-primary with REST fallback
Key Constraint: Must work without browser automation
Current State: All components ready
This Segment Creates: Full Docker deployment and E2E test
This Segment Depends On: All previous segments
```

## Objective
Deploy the complete stack using Docker Compose and perform end-to-end testing.

## Steps

### Step 20.1: Update `docker-compose.yml`

Update file `docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: linkedin_postgres
    environment:
      POSTGRES_USER: linkedin
      POSTGRES_PASSWORD: linkedin
      POSTGRES_DB: linkedin_api
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U linkedin"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
   