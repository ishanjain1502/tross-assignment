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
