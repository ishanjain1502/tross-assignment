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
