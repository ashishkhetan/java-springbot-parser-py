import javalang
from typing import Dict, List, Optional
from pathlib import Path
from pydantic import BaseModel
import graphviz
import json
import argparse
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Models
class EndpointInfo(BaseModel):
    path: str
    method: str
    controller_class: str
    method_name: str
    request_dto: Optional[str] = None
    response_dto: Optional[str] = None
    service_calls: List[str] = []

class DtoInfo(BaseModel):
    name: str
    fields: Dict[str, str]
    used_in_controllers: List[str] = []
    used_in_services: List[str] = []
    mapped_to_entities: List[str] = []

class EntityInfo(BaseModel):
    name: str
    table_name: str
    fields: Dict[str, str]
    relationships: List[Dict[str, str]] = []
    mapped_to_dtos: List[str] = []

class ServiceInfo(BaseModel):
    name: str
    methods: List[str]
    used_dtos: List[str]
    used_entities: List[str]
    called_by_controllers: List[str] = []

class DependencyGraph(BaseModel):
    endpoints: List[EndpointInfo]
    dtos: Dict[str, DtoInfo]
    entities: Dict[str, EntityInfo]
    services: Dict[str, ServiceInfo]

# Parser
class JavaSpringParser:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.endpoints: List[EndpointInfo] = []
        self.dtos: Dict[str, DtoInfo] = {}
        self.entities: Dict[str, EntityInfo] = {}
        self.services: Dict[str, ServiceInfo] = {}

    def parse_java_file(self, file_path: Path) -> Optional[javalang.tree.CompilationUnit]:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            return javalang.parse.parse(content)
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {str(e)}")
            return None

    def parse_controller(self, file_path: Path):
        tree = self.parse_java_file(file_path)
        if not tree:
            return

        for class_decl in tree.types:
            if any(ann.name == 'RestController' for ann in class_decl.annotations):
                class_name = class_decl.name
                base_path = ""
                
                for ann in class_decl.annotations:
                    if ann.name == 'RequestMapping':
                        if hasattr(ann, 'arguments') and ann.arguments:
                            for arg in ann.arguments:
                                if isinstance(arg, javalang.tree.Literal):
                                    base_path = arg.value.strip('"')

                for method in class_decl.methods:
                    endpoint = self._parse_endpoint_method(method, class_name, base_path)
                    if endpoint:
                        self.endpoints.append(endpoint)

    def _parse_endpoint_method(self, method, class_name: str, base_path: str) -> Optional[EndpointInfo]:
        mapping_annotations = [
            'GetMapping', 'PostMapping', 'PutMapping', 
            'DeleteMapping', 'PatchMapping', 'RequestMapping'
        ]
        
        for ann in method.annotations:
            if ann.name in mapping_annotations:
                path = base_path
                http_method = ann.name.replace('Mapping', '').upper()
                if http_method == 'REQUEST':
                    http_method = 'GET'
                
                if hasattr(ann, 'arguments') and ann.arguments:
                    for arg in ann.arguments:
                        if isinstance(arg, javalang.tree.Literal):
                            path += arg.value.strip('"')

                request_dto = None
                response_dto = None
                
                for param in method.parameters:
                    if hasattr(param, 'type'):
                        param_type = param.type.name
                        if param_type.endswith('DTO'):
                            request_dto = param_type

                if hasattr(method.return_type, 'name'):
                    return_type = method.return_type.name
                    if return_type.endswith('DTO'):
                        response_dto = return_type

                return EndpointInfo(
                    path=path,
                    method=http_method,
                    controller_class=class_name,
                    method_name=method.name,
                    request_dto=request_dto,
                    response_dto=response_dto,
                    service_calls=[]
                )
        return None

    def parse_dto(self, file_path: Path):
        tree = self.parse_java_file(file_path)
        if not tree:
            return

        for class_decl in tree.types:
            if class_decl.name.endswith('DTO'):
                fields = {}
                for field in class_decl.fields:
                    field_type = field.type.name
                    for declarator in field.declarators:
                        fields[declarator.name] = field_type

                self.dtos[class_decl.name] = DtoInfo(
                    name=class_decl.name,
                    fields=fields,
                    used_in_controllers=[],
                    used_in_services=[],
                    mapped_to_entities=[]
                )

    def parse_entity(self, file_path: Path):
        tree = self.parse_java_file(file_path)
        if not tree:
            return

        for class_decl in tree.types:
            if any(ann.name == 'Entity' for ann in class_decl.annotations):
                table_name = class_decl.name.lower()
                for ann in class_decl.annotations:
                    if ann.name == 'Table':
                        if hasattr(ann, 'arguments') and ann.arguments:
                            for arg in ann.arguments:
                                if hasattr(arg, 'name') and arg.name == 'name' and hasattr(arg, 'value'):
                                    table_name = arg.value.value.strip('"')

                fields = {}
                relationships = []

                for field in class_decl.fields:
                    field_type = field.type.name
                    for declarator in field.declarators:
                        fields[declarator.name] = field_type
                        
                        for ann in field.annotations:
                            if ann.name in ['OneToMany', 'ManyToOne', 'OneToOne', 'ManyToMany']:
                                relationships.append({
                                    'type': ann.name,
                                    'field': declarator.name,
                                    'target_entity': field_type
                                })

                self.entities[class_decl.name] = EntityInfo(
                    name=class_decl.name,
                    table_name=table_name,
                    fields=fields,
                    relationships=relationships,
                    mapped_to_dtos=[]
                )

    def parse_service(self, file_path: Path):
        tree = self.parse_java_file(file_path)
        if not tree:
            return

        for class_decl in tree.types:
            if any(ann.name == 'Service' for ann in class_decl.annotations):
                methods = []
                used_dtos = set()
                used_entities = set()

                for method in class_decl.methods:
                    methods.append(method.name)
                    
                    if hasattr(method.return_type, 'name'):
                        return_type = method.return_type.name
                        if return_type.endswith('DTO'):
                            used_dtos.add(return_type)
                        elif return_type in self.entities:
                            used_entities.add(return_type)

                    for param in method.parameters:
                        if hasattr(param, 'type'):
                            param_type = param.type.name
                            if param_type.endswith('DTO'):
                                used_dtos.add(param_type)
                            elif param_type in self.entities:
                                used_entities.add(param_type)

                self.services[class_decl.name] = ServiceInfo(
                    name=class_decl.name,
                    methods=methods,
                    used_dtos=list(used_dtos),
                    used_entities=list(used_entities),
                    called_by_controllers=[]
                )

    def analyze_dependencies(self):
        for endpoint in self.endpoints:
            if endpoint.request_dto:
                if endpoint.request_dto in self.dtos:
                    self.dtos[endpoint.request_dto].used_in_controllers.append(endpoint.controller_class)
            if endpoint.response_dto:
                if endpoint.response_dto in self.dtos:
                    self.dtos[endpoint.response_dto].used_in_controllers.append(endpoint.controller_class)

        for dto_name, dto in self.dtos.items():
            for entity_name, entity in self.entities.items():
                matching_fields = set(dto.fields.keys()) & set(entity.fields.keys())
                if matching_fields:
                    dto.mapped_to_entities.append(entity_name)
                    entity.mapped_to_dtos.append(dto_name)

    def parse_project(self) -> DependencyGraph:
        for file_path in self.base_path.rglob("*.java"):
            try:
                content = file_path.read_text(encoding='utf-8')
                
                if '@RestController' in content:
                    self.parse_controller(file_path)
                elif '@Entity' in content:
                    self.parse_entity(file_path)
                elif 'DTO' in file_path.name:
                    self.parse_dto(file_path)
                elif '@Service' in content:
                    self.parse_service(file_path)
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {str(e)}")
                continue

        self.analyze_dependencies()

        return DependencyGraph(
            endpoints=self.endpoints,
            dtos=self.dtos,
            entities=self.entities,
            services=self.services
        )

# Visualizer
class DependencyVisualizer:
    def __init__(self, dependency_graph: DependencyGraph, service_calls: List[Dict] = None):
        self.graph = dependency_graph
        self.service_calls = service_calls or []
        self.dot = graphviz.Digraph(comment='API Dependencies')
        self.dot.attr(rankdir='LR')

    def create_graph(self):
        try:
            self.dot.attr('node', shape='rectangle', style='rounded')
            
            # Create subgraph for service calls if any exist
            if self.service_calls:
                with self.dot.subgraph(name='cluster_service_calls') as c:
                    c.attr(label='Service Calls')
                    for call in self.service_calls:
                        source_id = f"service_{call['source_service']}"
                        target_id = f"service_{call['target_service']}"
                        
                        # Create service nodes if they don't exist
                        c.node(source_id, call['source_service'], color='purple')
                        c.node(target_id, call['target_service'], color='purple')
                        
                        # Create edge with call details
                        edge_label = f"{call['http_method']} {call['path']}\n"
                        if call['has_fallback']:
                            edge_label += "(with fallback)"
                        
                        c.edge(source_id, target_id, edge_label, color='purple', style='bold')
                        
                        # Add DTO connections if present
                        if call.get('request_dto'):
                            c.edge(source_id, f"dto_{call['request_dto']}", 'sends', style='dashed')
                        if call.get('response_dto'):
                            c.edge(target_id, f"dto_{call['response_dto']}", 'returns', style='dashed')
            
            with self.dot.subgraph(name='cluster_endpoints') as c:
                c.attr(label='API Endpoints')
                for endpoint in self.graph.endpoints:
                    node_id = f"endpoint_{endpoint.path}_{endpoint.method}"
                    label = f"{endpoint.method}\n{endpoint.path}"
                    c.node(node_id, label, color='blue')
                    
                    if endpoint.request_dto:
                        self.dot.edge(node_id, f"dto_{endpoint.request_dto}", 'uses')
                    if endpoint.response_dto:
                        self.dot.edge(node_id, f"dto_{endpoint.response_dto}", 'returns')
            
            with self.dot.subgraph(name='cluster_dtos') as c:
                c.attr(label='DTOs')
                for dto_name, dto in self.graph.dtos.items():
                    label = f"{dto_name}\n" + "\n".join(f"{k}: {v}" for k, v in dto.fields.items())
                    c.node(f"dto_{dto_name}", label, color='green')
                    
                    for entity in dto.mapped_to_entities:
                        self.dot.edge(f"dto_{dto_name}", f"entity_{entity}", 'maps to')
            
            with self.dot.subgraph(name='cluster_entities') as c:
                c.attr(label='Database Entities')
                for entity_name, entity in self.graph.entities.items():
                    label = f"{entity_name}\n({entity.table_name})\n" + "\n".join(f"{k}: {v}" for k, v in entity.fields.items())
                    c.node(f"entity_{entity_name}", label, color='red')
                    
                    for rel in entity.relationships:
                        self.dot.edge(
                            f"entity_{entity_name}",
                            f"entity_{rel['target_entity']}",
                            rel['type']
                        )
            
            with self.dot.subgraph(name='cluster_services') as c:
                c.attr(label='Services')
                for service_name, service in self.graph.services.items():
                    label = f"{service_name}\n" + "\n".join(service.methods)
                    c.node(f"service_{service_name}", label, color='orange')
                    
                    for dto in service.used_dtos:
                        self.dot.edge(f"service_{service_name}", f"dto_{dto}", 'uses')
                    for entity in service.used_entities:
                        self.dot.edge(f"service_{service_name}", f"entity_{entity}", 'uses')
        except Exception as e:
            logger.error(f"Error creating graph: {str(e)}")
            raise
    
    def save(self, output_path: str, format: str = 'png'):
        try:
            # Ensure the output directory exists
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            # Try to render the graph
            self.dot.render(output_path, format=format, cleanup=True)
        except Exception as e:
            logger.error(f"Failed to save visualization: {str(e)}")
            if "failed to execute" in str(e) and "dot" in str(e):
                logger.error("Graphviz 'dot' executable not found. Please install Graphviz and ensure it's in your system PATH.")
            raise
    
    def get_impact_analysis(self, dto_name: str) -> Dict[str, any]:
        if dto_name not in self.graph.dtos:
            return {"error": f"DTO {dto_name} not found"}
            
        dto = self.graph.dtos[dto_name]
        
        affected_endpoints = [
            endpoint for endpoint in self.graph.endpoints
            if endpoint.request_dto == dto_name or endpoint.response_dto == dto_name
        ]
        
        affected_services = [
            service_name for service_name, service in self.graph.services.items()
            if dto_name in service.used_dtos
        ]
        
        affected_tables = []
        for entity_name in dto.mapped_to_entities:
            if entity_name in self.graph.entities:
                affected_tables.append(self.graph.entities[entity_name].table_name)
        
        return {
            "dto": dto_name,
            "affected_endpoints": [
                {"method": e.method, "path": e.path} for e in affected_endpoints
            ],
            "affected_services": affected_services,
            "affected_database_tables": affected_tables,
            "field_mappings": dto.fields
        }

def main():
    parser = argparse.ArgumentParser(description='Analyze Java Spring Boot microservices dependencies')
    parser.add_argument('project_path', help='Path to the Java Spring Boot project')
    parser.add_argument('--output', '-o', default='dependencies',
                       help='Output path for visualization (default: dependencies)')
    parser.add_argument('--format', '-f', choices=['png', 'pdf', 'svg'],
                       default='png', help='Output format (default: png)')
    parser.add_argument('--analyze-dto', '-d',
                       help='Analyze impact of changes to specific DTO')
    
    args = parser.parse_args()
    
    try:
        java_parser = JavaSpringParser(args.project_path)
        dependency_graph = java_parser.parse_project()
        visualizer = DependencyVisualizer(dependency_graph)
        
        if args.analyze_dto:
            impact_analysis = visualizer.get_impact_analysis(args.analyze_dto)
            print("\nImpact Analysis:")
            print(json.dumps(impact_analysis, indent=2))
        else:
            try:
                visualizer.create_graph()
                output_path = Path(args.output)
                visualizer.save(str(output_path), args.format)
                logger.info(f"Dependency graph saved to: {output_path}.{args.format}")
            except Exception as e:
                logger.warning("Could not generate visualization (Graphviz may not be installed). Continuing with analysis...")
            
            print("\nProject Summary:")
            print(f"Total Endpoints: {len(dependency_graph.endpoints)}")
            print(f"Total DTOs: {len(dependency_graph.dtos)}")
            print(f"Total Entities: {len(dependency_graph.entities)}")
            print(f"Total Services: {len(dependency_graph.services)}")
    except Exception as e:
        logger.error(f"Error analyzing project: {str(e)}")
        raise

if __name__ == "__main__":
    main()
