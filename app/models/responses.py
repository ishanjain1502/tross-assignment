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
