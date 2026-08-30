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
