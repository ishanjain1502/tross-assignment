import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class ProfileIdPattern:
    name: str
    pattern: str

@dataclass  
class EndpointsConfig:
    base_url: str
    rest_endpoints: Dict[str, str]
    graphql: Dict[str, Any]
    required_headers: Dict[str, str]
    profile_id_patterns: List[ProfileIdPattern]
    
    @property
    def me_endpoint(self) -> str:
        return self.rest_endpoints.get('me', '/voyager/api/me')
    
    @property
    def graphql_endpoint(self) -> str:
        return self.rest_endpoints.get('graphql', '/voyager/api/graphql')
    
    @property
    def full_profile_query(self) -> str:
        return self.graphql.get('profile_full_query', '')
    
    @property
    def full_profile_decoration_id(self) -> str:
        return self.graphql.get('decoration_ids', {}).get('full_profile', '')
    
    def get_rest_endpoint(self, name: str, **kwargs) -> str:
        """Get REST endpoint with variable substitution"""
        template = self.rest_endpoints.get(name)
        if not template:
            raise ValueError(f"Unknown endpoint: {name}")
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing parameter {e} for endpoint {name}")
    
    def get_profile_id_patterns(self) -> List[ProfileIdPattern]:
        return self.profile_id_patterns

def load_endpoints_config(config_path: Optional[str] = None) -> EndpointsConfig:
    """Load endpoints configuration from YAML file"""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "linkedin_endpoints.yaml"
    
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    
    patterns = [
        ProfileIdPattern(name=p['name'], pattern=p['pattern'])
        for p in data.get('profile_id_patterns', [])
    ]
    
    return EndpointsConfig(
        base_url=data.get('base_url', 'https://www.linkedin.com'),
        rest_endpoints=data.get('rest_endpoints', {}),
        graphql=data.get('graphql', {}),
        required_headers=data.get('required_headers', {}),
        profile_id_patterns=patterns
    )

# Singleton instance
endpoints_config = load_endpoints_config()
