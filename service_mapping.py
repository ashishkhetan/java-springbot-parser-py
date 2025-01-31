from dataclasses import dataclass
from typing import Optional, Dict, List
import re
import yaml
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ServiceMapping:
    repository_path: str
    friendly_name: str
    service_name: str
    base_path: str

class ServiceMappingManager:
    def __init__(self):
        self.mappings: Dict[str, ServiceMapping] = {}
        self.property_cache: Dict[str, Dict[str, str]] = {}

    def load_from_repositories_file(self, file_path: str):
        """Load service mappings from repositories.txt"""
        try:
            logger.info(f"Loading service mappings from {file_path}")
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Split by spaces but preserve quoted strings
                        import shlex
                        parts = shlex.split(line)
                        logger.info(f"Processing line: {line}")
                        logger.info(f"Split parts: {parts}")
                        
                        if len(parts) >= 4:
                            repo_path = parts[0]
                            friendly_name = parts[1]  # shlex handles the quotes
                            service_name = parts[2]
                            base_path = parts[3]
                            
                            # Extract the service directory name as the repo key
                            repo_key = repo_path.split('/')[-1]  # spring-boot-cloud-eureka-order-service
                            logger.info(f"Extracted repo key: {repo_key}")
                            logger.info(f"Full repo path: {repo_path}")
                            
                            if repo_key in ['api', 'v1']:  # Skip common path segments
                                logger.info(f"Skipping common path segment: {repo_key}")
                                continue
                                
                            self.mappings[repo_key] = ServiceMapping(
                                repository_path=repo_path,
                                friendly_name=friendly_name,
                                service_name=service_name,
                                base_path=base_path
                            )
                            logger.info(f"Added mapping for {repo_key}: {self.mappings[repo_key]}")
        except Exception as e:
            logger.error(f"Error loading repository mappings: {str(e)}")
            raise

    def load_application_properties(self, repo_path: str):
        """Load application.yml/properties for a repository"""
        repo_key = repo_path.split('/')[-1]  # Get the last part of the path
        if repo_key in ['api', 'v1']:  # Skip common path segments
            return None
        properties = {}

        # Try application.yml
        yml_path = Path(repo_path) / "src" / "main" / "resources" / "application.yml"
        if yml_path.exists():
            try:
                with open(yml_path, 'r') as f:
                    yaml_data = yaml.safe_load(f)
                    self._flatten_dict(yaml_data, "", properties)
            except Exception as e:
                logger.warning(f"Error loading application.yml: {str(e)}")

        # Try application.yaml
        yaml_path = Path(repo_path) / "src" / "main" / "resources" / "application.yaml"
        if yaml_path.exists():
            try:
                with open(yaml_path, 'r') as f:
                    yaml_data = yaml.safe_load(f)
                    self._flatten_dict(yaml_data, "", properties)
            except Exception as e:
                logger.warning(f"Error loading application.yaml: {str(e)}")

        # Try application.properties
        props_path = Path(repo_path) / "src" / "main" / "resources" / "application.properties"
        if props_path.exists():
            try:
                with open(props_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            properties[key.strip()] = value.strip()
            except Exception as e:
                logger.warning(f"Error loading application.properties: {str(e)}")

        self.property_cache[repo_key] = properties

    def _flatten_dict(self, d: Dict, prefix: str, result: Dict[str, str]):
        """Flatten nested dictionary with dot notation"""
        for key, value in d.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._flatten_dict(value, new_key, result)
            else:
                result[new_key] = str(value)

    def resolve_property(self, repo_key: str, property_placeholder: str) -> Optional[str]:
        """Resolve ${property.path} to its actual value"""
        if not property_placeholder.startswith("${") or not property_placeholder.endswith("}"):
            return property_placeholder

        property_path = property_placeholder[2:-1]
        properties = self.property_cache.get(repo_key, {})
        return properties.get(property_path)

    def get_service_name(self, repo_path: str) -> Optional[str]:
        """Get service name for a repository"""
        repo_key = repo_path.split('/')[-1]  # Get the last part of the path
        if repo_key in ['api', 'v1']:  # Skip common path segments
            return None
        mapping = self.mappings.get(repo_key)
        return mapping.service_name if mapping else None

    def get_friendly_name(self, repo_path: str) -> Optional[str]:
        """Get friendly name for a repository"""
        repo_key = repo_path.split('/')[-1]  # Get the last part of the path
        if repo_key in ['api', 'v1']:  # Skip common path segments
            return None
        mapping = self.mappings.get(repo_key)
        return mapping.friendly_name if mapping else None

    def get_base_path(self, repo_path: str) -> Optional[str]:
        """Get base path for a repository"""
        repo_key = repo_path.split('/')[-1]  # Get the last part of the path
        if repo_key in ['api', 'v1']:  # Skip common path segments
            return None
        mapping = self.mappings.get(repo_key)
        return mapping.base_path if mapping else None
