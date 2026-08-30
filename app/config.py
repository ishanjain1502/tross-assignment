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
