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
