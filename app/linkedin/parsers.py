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
    
    def parse_graphql_positions(self, data: Dict[str, Any]) -> List[Dict]:
        """Parse experience/positions from GraphQL response"""
        positions = data.get('data', {}).get('profile', {}).get('positions', {})
        elements = positions.get('elements', [])
        
        results = []
        for pos in elements:
            results.append({
                "title": pos.get('title', ''),
                "company": {
                    "name": pos.get('companyName', ''),
                    "url": self._urn_to_company_url(pos.get('companyUrn')),
                    "logo_url": self._parse_graphql_image(
                        pos.get('companyLogo', {}).get('image') if pos.get('companyLogo') else None
                    ),
                },
                "location": pos.get('locationName', ''),
                "dates": {
                    "start": self._parse_graphql_date(pos.get('startDate')),
                    "end": self._parse_graphql_date(pos.get('endDate')),
                    "is_current": pos.get('endDate') is None,
                },
                "description": self._clean_html(pos.get('description', '')),
            })
        
        return results
    
    def parse_rest_positions(self, positions_data: Dict) -> List[Dict]:
        """Parse positions from REST endpoint"""
        if not positions_data:
            return []
        
        elements = positions_data.get('elements', [])
        results = []
        
        for pos in elements:
            results.append({
                "title": pos.get('title', ''),
                "company": {
                    "name": pos.get('companyName', ''),
                    "url": self._urn_to_company_url(pos.get('companyUrn')),
                },
                "location": pos.get('locationName', ''),
                "dates": {
                    "start": self._parse_rest_date(pos.get('startDate')),
                    "end": self._parse_rest_date(pos.get('endDate')),
                    "is_current": pos.get('endDate') is None,
                },
                "description": self._clean_html(pos.get('description', '')),
            })
        
        return results
    
    def parse_graphql_education(self, data: Dict[str, Any]) -> List[Dict]:
        """Parse education from GraphQL response"""
        education = data.get('data', {}).get('profile', {}).get('educations', {})
        elements = education.get('elements', [])
        
        results = []
        for edu in elements:
            results.append({
                "institution": {
                    "name": edu.get('schoolName', ''),
                    "url": self._urn_to_school_url(edu.get('schoolUrn')),
                },
                "degree": edu.get('degreeName', ''),
                "field_of_study": edu.get('fieldOfStudy', ''),
                "dates": {
                    "start": self._parse_graphql_date(edu.get('startDate')),
                    "end": self._parse_graphql_date(edu.get('endDate')),
                },
                "description": self._clean_html(edu.get('description', '')),
            })
        
        return results
    
    def parse_rest_education(self, education_data: Dict) -> List[Dict]:
        """Parse education from REST endpoint"""
        if not education_data:
            return []
        
        elements = education_data.get('elements', [])
        results = []
        
        for edu in elements:
            results.append({
                "institution": {
                    "name": edu.get('schoolName', ''),
                    "url": self._urn_to_school_url(edu.get('schoolUrn')),
                },
                "degree": edu.get('degreeName', ''),
                "field_of_study": edu.get('fieldOfStudy', ''),
                "dates": {
                    "start": self._parse_rest_date(edu.get('startDate')),
                    "end": self._parse_rest_date(edu.get('endDate')),
                },
                "description": self._clean_html(edu.get('description', '')),
            })
        
        return results
    
    def parse_graphql_skills(self, data: Dict[str, Any]) -> List[Dict]:
        """Parse skills from GraphQL response"""
        skills = data.get('data', {}).get('profile', {}).get('skills', {})
        elements = skills.get('elements', [])
        
        return [
            {
                "name": s.get('name', ''),
                "endorsement_count": s.get('endorsementCount', 0),
            }
            for s in elements
        ]
    
    def parse_rest_skills(self, skills_data: Dict) -> List[Dict]:
        """Parse skills from REST endpoint"""
        if not skills_data:
            return []
        
        elements = skills_data.get('elements', [])
        return [
            {
                "name": s.get('name', ''),
                "endorsement_count": s.get('endorsementCount', 0),
            }
            for s in elements
        ]
    
    def parse_graphql_certifications(self, data: Dict[str, Any]) -> List[Dict]:
        """Parse certifications from GraphQL response"""
        certs = data.get('data', {}).get('profile', {}).get('certifications', {})
        elements = certs.get('elements', [])
        
        return [
            {
                "name": c.get('name', ''),
                "issuer": c.get('authority', ''),
                "issue_date": self._parse_graphql_date(c.get('start')),
                "expiry_date": self._parse_graphql_date(c.get('end')),
                "credential_id": c.get('licenseNumber', ''),
            }
            for c in elements
        ]
    
    def parse_rest_certifications(self, certs_data: Dict) -> List[Dict]:
        """Parse certifications from REST endpoint"""
        if not certs_data:
            return []
        
        elements = certs_data.get('elements', [])
        return [
            {
                "name": c.get('name', ''),
                "issuer": c.get('authority', ''),
                "issue_date": self._parse_rest_date(c.get('start')),
                "expiry_date": self._parse_rest_date(c.get('end')),
                "credential_id": c.get('licenseNumber', ''),
            }
            for c in elements
        ]
    
    def parse_graphql_languages(self, data: Dict[str, Any]) -> List[Dict]:
        """Parse languages from GraphQL response"""
        langs = data.get('data', {}).get('profile', {}).get('languages', {})
        elements = langs.get('elements', [])
        
        return [
            {
                "name": l.get('name', ''),
                "proficiency": l.get('proficiency', ''),
            }
            for l in elements
        ]
    
    def parse_rest_languages(self, langs_data: Dict) -> List[Dict]:
        """Parse languages from REST endpoint"""
        if not langs_data:
            return []
        
        elements = langs_data.get('elements', [])
        return [
            {
                "name": l.get('name', ''),
                "proficiency": l.get('proficiency', ''),
            }
            for l in elements
        ]
    
    def _parse_graphql_date(self, date_obj: Optional[Dict]) -> Optional[Dict]:
        """Parse GraphQL date object {year, month}"""
        if not date_obj:
            return None
        return {
            "year": date_obj.get('year'),
            "month": date_obj.get('month'),
        }
    
    def _parse_rest_date(self, date_obj: Optional[Dict]) -> Optional[Dict]:
        """Parse REST date object"""
        if not date_obj:
            return None
        return {
            "year": date_obj.get('year'),
            "month": date_obj.get('month'),
        }
    
    def _urn_to_company_url(self, urn: Optional[str]) -> Optional[str]:
        """Convert company URN to URL"""
        if not urn:
            return None
        parts = urn.split(':')
        if len(parts) >= 4:
            return f"https://www.linkedin.com/company/{parts[-1]}/"
        return None
    
    def _urn_to_school_url(self, urn: Optional[str]) -> Optional[str]:
        """Convert school URN to URL"""
        if not urn:
            return None
        parts = urn.split(':')
        if len(parts) >= 4:
            return f"https://www.linkedin.com/school/{parts[-1]}/"
        return None
