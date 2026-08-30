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
