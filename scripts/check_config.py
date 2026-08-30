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
