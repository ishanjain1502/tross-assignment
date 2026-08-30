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
    
    def invalidate_session(self):
        """Force session to be refreshed on next get_session() call"""
        self._session = None
