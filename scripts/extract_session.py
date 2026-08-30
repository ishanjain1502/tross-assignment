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
