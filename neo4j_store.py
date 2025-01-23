from neo4j import GraphDatabase
from typing import Dict, List, Optional
import logging

class Neo4jStore:
    def __init__(self, uri: str, username: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self._init_constraints()

    def _init_constraints(self):
        with self.driver.session() as session:
            # Create constraints for unique identifiers
            constraints = [
                "CREATE CONSTRAINT endpoint_path IF NOT EXISTS FOR (e:Endpoint) REQUIRE e.path IS UNIQUE",
                "CREATE CONSTRAINT dto_name IF NOT EXISTS FOR (d:DTO) REQUIRE d.name IS UNIQUE",
                "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
                "CREATE CONSTRAINT service_name IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE",
                "CREATE CONSTRAINT repository_name IF NOT EXISTS FOR (r:Repository) REQUIRE r.name IS UNIQUE"
            ]
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    logging.warning(f"Constraint creation failed: {str(e)}")

    def store_repository_data(self, repo_name: str, dependency_data: Dict):
        with self.driver.session() as session:
            # Create repository node
            session.run("""
                MERGE (r:Repository {name: $repo_name})
            """, repo_name=repo_name)

            # Store endpoints
            for endpoint in dependency_data.get('endpoints', []):
                self._store_endpoint(session, repo_name, endpoint)

            # Store DTOs
            for dto_name, dto_info in dependency_data.get('dtos', {}).items():
                self._store_dto(session, repo_name, dto_name, dto_info)

            # Store entities
            for entity_name, entity_info in dependency_data.get('entities', {}).items():
                self._store_entity(session, repo_name, entity_name, entity_info)

            # Store services
            for service_name, service_info in dependency_data.get('services', {}).items():
                self._store_service(session, repo_name, service_name, service_info)

    def _store_endpoint(self, session, repo_name: str, endpoint: Dict):
        session.run("""
            MATCH (r:Repository {name: $repo_name})
            MERGE (e:Endpoint {
                path: $path,
                method: $method,
                controller_class: $controller_class,
                method_name: $method_name
            })
            MERGE (e)-[:BELONGS_TO]->(r)
            WITH e
            FOREACH (dto_name IN CASE WHEN $request_dto IS NOT NULL 
                    THEN [$request_dto] ELSE [] END |
                MERGE (d:DTO {name: dto_name})
                MERGE (e)-[:USES_REQUEST_DTO]->(d))
            FOREACH (dto_name IN CASE WHEN $response_dto IS NOT NULL 
                    THEN [$response_dto] ELSE [] END |
                MERGE (d:DTO {name: dto_name})
                MERGE (e)-[:RETURNS_RESPONSE_DTO]->(d))
        """, repo_name=repo_name, **endpoint)

    def _store_dto(self, session, repo_name: str, dto_name: str, dto_info: Dict):
        # Convert fields to a string representation
        fields_str = ','.join([f"{k}:{v}" for k, v in dto_info.get('fields', {}).items()])
        
        session.run("""
            MATCH (r:Repository {name: $repo_name})
            MERGE (d:DTO {name: $dto_name})
            SET d.fields = $fields_str
            MERGE (d)-[:BELONGS_TO]->(r)
            WITH d
            UNWIND $used_in_controllers AS controller
            MERGE (c:Controller {name: controller})
            MERGE (d)-[:USED_IN]->(c)
            WITH d
            UNWIND $mapped_to_entities AS entity
            MERGE (e:Entity {name: entity})
            MERGE (d)-[:MAPS_TO]->(e)
        """, repo_name=repo_name, dto_name=dto_name, fields_str=fields_str,
             used_in_controllers=dto_info.get('used_in_controllers', []),
             mapped_to_entities=dto_info.get('mapped_to_entities', []))

    def _store_entity(self, session, repo_name: str, entity_name: str, entity_info: Dict):
        # Convert fields to a string representation
        fields_str = ','.join([f"{k}:{v}" for k, v in entity_info.get('fields', {}).items()])
        
        session.run("""
            MATCH (r:Repository {name: $repo_name})
            MERGE (e:Entity {name: $entity_name})
            SET e.table_name = $table_name,
                e.fields = $fields_str
            MERGE (e)-[:BELONGS_TO]->(r)
            WITH e
            UNWIND $relationships AS rel
            MERGE (target:Entity {name: rel.target_entity})
            MERGE (e)-[:RELATES_TO {type: rel.type, field: rel.field}]->(target)
        """, repo_name=repo_name, entity_name=entity_name,
             table_name=entity_info.get('table_name'),
             fields_str=fields_str,
             relationships=entity_info.get('relationships', []))

    def _store_service(self, session, repo_name: str, service_name: str, service_info: Dict):
        session.run("""
            MATCH (r:Repository {name: $repo_name})
            MERGE (s:Service {name: $service_name})
            SET s.methods = $methods
            MERGE (s)-[:BELONGS_TO]->(r)
            WITH s
            UNWIND $used_dtos AS dto_name
            MERGE (d:DTO {name: dto_name})
            MERGE (s)-[:USES_DTO]->(d)
            WITH s
            UNWIND $used_entities AS entity_name
            MERGE (e:Entity {name: entity_name})
            MERGE (s)-[:USES_ENTITY]->(e)
        """, repo_name=repo_name, service_name=service_name,
             methods=service_info.get('methods', []),
             used_dtos=service_info.get('used_dtos', []),
             used_entities=service_info.get('used_entities', []))

    def get_impact_analysis(self, dto_name: str) -> Dict:
        with self.driver.session() as session:
            result = session.run("""
                MATCH (d:DTO {name: $dto_name})
                OPTIONAL MATCH (d)<-[:USES_REQUEST_DTO|RETURNS_RESPONSE_DTO]-(e:Endpoint)
                OPTIONAL MATCH (d)<-[:USES_DTO]-(s:Service)
                OPTIONAL MATCH (d)-[:MAPS_TO]->(entity:Entity)
                RETURN {
                    dto: d.name,
                    affected_endpoints: collect(DISTINCT {
                        method: e.method,
                        path: e.path
                    }),
                    affected_services: collect(DISTINCT s.name),
                    affected_tables: collect(DISTINCT entity.table_name),
                    field_mappings: d.fields
                } as impact
            """, dto_name=dto_name)
            
            return result.single()["impact"]

    def get_cross_service_dependencies(self) -> List[Dict]:
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r1:Repository)-[:CONTAINS]->(s1:Service)-[:USES_DTO]->(d:DTO)<-[:USES_DTO]-(s2:Service)<-[:CONTAINS]-(r2:Repository)
                WHERE r1 <> r2
                RETURN {
                    from_repo: r1.name,
                    from_service: s1.name,
                    dto: d.name,
                    to_service: s2.name,
                    to_repo: r2.name
                } as dependency
            """)
            
            return [record["dependency"] for record in result]

    def close(self):
        self.driver.close()
