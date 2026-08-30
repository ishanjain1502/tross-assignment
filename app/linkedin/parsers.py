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

    def parse_dash_profile_response(
        self,
        data: Dict[str, Any],
        url: str,
        profile_id: str,
    ) -> Dict[str, Any]:
        """Parse a dash profiles API response into the standard scrape shape."""
        included = data.get("included", [])
        profile_entity = self._find_included(
            included, "com.linkedin.voyager.dash.identity.profile.Profile"
        )
        geo_index = {
            item.get("entityUrn"): item
            for item in included
            if item.get("$type") == "com.linkedin.voyager.dash.common.Geo"
        }

        profile = {
            "url": url,
            "internal_id": profile_id,
            "first_name": self._dash_text(profile_entity, "firstName", "multiLocaleFirstName"),
            "last_name": self._dash_text(profile_entity, "lastName", "multiLocaleLastName"),
            "full_name": self._make_full_name(
                self._dash_text(profile_entity, "firstName", "multiLocaleFirstName"),
                self._dash_text(profile_entity, "lastName", "multiLocaleLastName"),
            ),
            "headline": self._dash_text(profile_entity, "headline", "multiLocaleHeadline"),
            "about": self._clean_html(
                self._dash_text(profile_entity, "summary", "multiLocaleSummary")
            ),
            "location": self._parse_dash_location(profile_entity, geo_index),
            "profile_image_url": self._parse_dash_profile_picture(
                (profile_entity or {}).get("profilePicture")
            ),
            "background_image_url": self._parse_dash_background_picture(
                (profile_entity or {}).get("backgroundPicture")
                or (profile_entity or {}).get("backgroundPictures")
            ),
            "connections": None,
        }

        return {
            "status": "success",
            "profile_url": url,
            "profile": profile,
            "experience": self._parse_dash_positions(included),
            "education": self._parse_dash_education(included),
            "skills": self._parse_dash_skills(included),
            "certifications": self._parse_dash_certifications(included),
            "languages": self._parse_dash_languages(included),
            "warnings": [],
            "scraped_at": None,
            "source": "dash",
        }

    def _find_included(self, included: List[Dict], type_suffix: str) -> Optional[Dict]:
        for item in included:
            item_type = item.get("$type", "")
            if item_type == type_suffix or item_type.endswith(f".{type_suffix.split('.')[-1]}"):
                if type_suffix in item_type:
                    return item
        return None

    def _dash_text(self, entity: Optional[Dict], *keys: str) -> str:
        if not entity:
            return ""
        for key in keys:
            value = entity.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                for localized in value.values():
                    if localized:
                        return str(localized)
        return ""

    def _parse_dash_location(
        self,
        profile_entity: Optional[Dict],
        geo_index: Dict[str, Dict],
    ) -> Optional[Dict]:
        if not profile_entity:
            return None
        geo_location = profile_entity.get("geoLocation") or {}
        geo_urn = geo_location.get("geoUrn") or geo_location.get("*geo")
        geo = geo_index.get(geo_urn) if geo_urn else None
        if geo:
            return {
                "name": geo.get("defaultLocalizedName") or geo.get("defaultLocalizedNameWithoutCountryName", ""),
                "country": geo.get("countryISOCode"),
            }
        return None

    def _parse_dash_profile_picture(self, picture: Optional[Dict]) -> Optional[str]:
        if not picture:
            return None
        vector = (
            picture.get("displayImageReference", {})
            .get("vectorImage", {})
        )
        return self._parse_dash_vector_image(vector)

    def _parse_dash_background_picture(self, background: Any) -> Optional[str]:
        if isinstance(background, list) and background:
            background = background[0]
        if not isinstance(background, dict):
            return None
        vector = background.get("vectorImage") or background.get("displayImageReference", {}).get("vectorImage")
        return self._parse_dash_vector_image(vector)

    def _parse_dash_vector_image(self, vector: Optional[Dict]) -> Optional[str]:
        if not vector:
            return None
        root_url = vector.get("rootUrl", "")
        artifacts = vector.get("artifacts", [])
        if not root_url or not artifacts:
            return None
        largest = max(artifacts, key=lambda item: item.get("width", 0))
        segment = largest.get("fileIdentifyingUrlPathSegment", "")
        if segment:
            return f"{root_url}{segment}"
        return None

    def _parse_dash_date(self, date_range: Optional[Dict]) -> Dict[str, Optional[Dict]]:
        if not date_range:
            return {"start": None, "end": None, "is_current": True}
        return {
            "start": self._parse_rest_date(date_range.get("start")),
            "end": self._parse_rest_date(date_range.get("end")),
            "is_current": date_range.get("end") is None,
        }

    def _parse_dash_positions(self, included: List[Dict]) -> List[Dict]:
        results = []
        for item in included:
            if item.get("$type") != "com.linkedin.voyager.dash.identity.profile.Position":
                continue
            results.append({
                "title": self._dash_text(item, "title", "multiLocaleTitle"),
                "company": {
                    "name": self._dash_text(item, "companyName", "multiLocaleCompanyName"),
                    "url": self._urn_to_company_url(item.get("companyUrn") or item.get("*company")),
                },
                "location": self._dash_text(item, "locationName", "geoLocationName"),
                "dates": self._parse_dash_date(item.get("dateRange")),
                "description": self._clean_html(self._dash_text(item, "description", "multiLocaleDescription")),
            })
        return results

    def _parse_dash_education(self, included: List[Dict]) -> List[Dict]:
        results = []
        for item in included:
            if item.get("$type") != "com.linkedin.voyager.dash.identity.profile.Education":
                continue
            results.append({
                "institution": {
                    "name": self._dash_text(item, "schoolName", "multiLocaleSchoolName"),
                    "url": self._urn_to_school_url(item.get("schoolUrn")),
                },
                "degree": self._dash_text(item, "degreeName", "multiLocaleDegreeName"),
                "field_of_study": self._dash_text(item, "fieldOfStudy", "multiLocaleFieldOfStudy"),
                "dates": {
                    "start": self._parse_rest_date((item.get("dateRange") or {}).get("start")),
                    "end": self._parse_rest_date((item.get("dateRange") or {}).get("end")),
                },
                "description": self._clean_html(self._dash_text(item, "description", "multiLocaleDescription")),
            })
        return results

    def _parse_dash_skills(self, included: List[Dict]) -> List[Dict]:
        results = []
        for item in included:
            if item.get("$type") != "com.linkedin.voyager.dash.identity.profile.Skill":
                continue
            results.append({
                "name": self._dash_text(item, "name", "multiLocaleName"),
                "endorsement_count": item.get("endorsementCount", 0),
            })
        return results

    def _parse_dash_certifications(self, included: List[Dict]) -> List[Dict]:
        results = []
        for item in included:
            if item.get("$type") != "com.linkedin.voyager.dash.identity.profile.Certification":
                continue
            results.append({
                "name": self._dash_text(item, "name", "multiLocaleName"),
                "issuer": self._dash_text(item, "authority", "multiLocaleAuthority"),
                "issue_date": self._parse_rest_date(item.get("issuedOn") or (item.get("dateRange") or {}).get("start")),
                "expiry_date": self._parse_rest_date((item.get("dateRange") or {}).get("end")),
                "credential_id": item.get("licenseNumber", ""),
            })
        return results

    def _parse_dash_languages(self, included: List[Dict]) -> List[Dict]:
        results = []
        for item in included:
            if item.get("$type") != "com.linkedin.voyager.dash.identity.profile.Language":
                continue
            results.append({
                "name": self._dash_text(item, "name", "multiLocaleName"),
                "proficiency": item.get("proficiency", ""),
            })
        return results
