from dataclasses import dataclass
from typing import List, Optional, Dict
import javalang
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class FeignMethod:
    name: str
    http_method: str
    path: str
    request_dto: Optional[str]
    response_dto: Optional[str]

@dataclass
class FeignClientInfo:
    interface_name: str
    target_service: str
    url_value: Optional[str]
    fallback_class: Optional[str]
    methods: List[FeignMethod]

class FeignClientParser:
    def __init__(self, service_mapping_manager):
        self.service_mapping_manager = service_mapping_manager
        self.http_method_annotations = {
            'GetMapping': 'GET',
            'PostMapping': 'POST',
            'PutMapping': 'PUT',
            'DeleteMapping': 'DELETE',
            'PatchMapping': 'PATCH',
            'RequestMapping': 'GET'  # Default method for RequestMapping
        }

    def parse_feign_client(self, file_path: str, repo_path: str) -> Optional[FeignClientInfo]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            tree = javalang.parse.parse(content)
            
            for interface_declaration in tree.types:
                if not isinstance(interface_declaration, javalang.tree.InterfaceDeclaration):
                    continue
                    
                feign_client_annotation = None
                for ann in interface_declaration.annotations:
                    if ann.name == 'FeignClient':
                        feign_client_annotation = ann
                        break
                        
                if not feign_client_annotation:
                    continue
                    
                # Extract FeignClient annotation details
                target_service = None
                url_value = None
                fallback_class = None
                
                if hasattr(feign_client_annotation, 'arguments'):
                    for arg in feign_client_annotation.arguments:
                        if isinstance(arg, javalang.tree.ElementValuePair):
                            if arg.name == 'value' or arg.name == 'name':
                                target_service = arg.value.value.strip('"')
                            elif arg.name == 'url':
                                url_value = arg.value.value.strip('"')
                            elif arg.name == 'fallback':
                                fallback_class = arg.value.member
                        elif isinstance(arg, javalang.tree.Literal):
                            # If no name is specified, the first string argument is the name
                            target_service = arg.value.strip('"')
                
                # Parse methods
                methods: List[FeignMethod] = []
                for method in interface_declaration.methods:
                    feign_method = self._parse_feign_method(method)
                    if feign_method:
                        methods.append(feign_method)
                
                # If url contains property placeholder, try to resolve it
                if url_value and '${' in url_value:
                    repo_key = Path(repo_path).name
                    resolved_url = self.service_mapping_manager.resolve_property(repo_key, url_value)
                    if resolved_url:
                        url_value = resolved_url
                
                return FeignClientInfo(
                    interface_name=interface_declaration.name,
                    target_service=target_service,
                    url_value=url_value,
                    fallback_class=fallback_class,
                    methods=methods
                )
                
        except Exception as e:
            logger.error(f"Error parsing Feign client {file_path}: {str(e)}")
            return None

    def _parse_feign_method(self, method_declaration) -> Optional[FeignMethod]:
        try:
            http_method = None
            path = ""
            
            # Find HTTP method annotation
            for ann in method_declaration.annotations:
                if ann.name in self.http_method_annotations:
                    http_method = self.http_method_annotations[ann.name]
                    
                    # Extract path from annotation
                    if hasattr(ann, 'arguments'):
                        for arg in ann.arguments:
                            if isinstance(arg, javalang.tree.ElementValuePair):
                                if arg.name in ['value', 'path']:
                                    path = arg.value.value.strip('"')
                            elif isinstance(arg, javalang.tree.Literal):
                                path = arg.value.strip('"')
                    break
            
            if not http_method:
                return None
            
            # Parse request and response DTOs
            request_dto = None
            response_dto = None
            
            # Check parameters for request DTO
            for param in method_declaration.parameters:
                if hasattr(param, 'type'):
                    param_type = param.type.name
                    if param_type.endswith('DTO'):
                        request_dto = param_type
            
            # Check return type for response DTO
            if hasattr(method_declaration.return_type, 'name'):
                return_type = method_declaration.return_type.name
                if return_type.endswith('DTO'):
                    response_dto = return_type
            
            return FeignMethod(
                name=method_declaration.name,
                http_method=http_method,
                path=path,
                request_dto=request_dto,
                response_dto=response_dto
            )
            
        except Exception as e:
            logger.error(f"Error parsing Feign method {method_declaration.name}: {str(e)}")
            return None

    def extract_service_calls(self, repo_path: str) -> List[Dict]:
        """Extract all Feign client service calls from a repository"""
        service_calls = []
        
        try:
            for java_file in Path(repo_path).rglob("*.java"):
                if "@FeignClient" in java_file.read_text(encoding='utf-8'):
                    feign_client = self.parse_feign_client(str(java_file), repo_path)
                    if feign_client:
                        source_service = self.service_mapping_manager.get_service_name(repo_path)
                        
                        for method in feign_client.methods:
                            service_calls.append({
                                'source_service': source_service,
                                'target_service': feign_client.target_service,
                                'interface_name': feign_client.interface_name,
                                'method_name': method.name,
                                'http_method': method.http_method,
                                'path': method.path,
                                'url_value': feign_client.url_value,
                                'request_dto': method.request_dto,
                                'response_dto': method.response_dto,
                                'has_fallback': bool(feign_client.fallback_class)
                            })
        
        except Exception as e:
            logger.error(f"Error extracting service calls from {repo_path}: {str(e)}")
        
        return service_calls
