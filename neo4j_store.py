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
                "CREATE CONSTRAINT endpoint_id IF NOT EXISTS FOR (e:Endpoint) REQUIRE e.unique_id IS UNIQUE",
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
        logging.info(f"Storing data for repository: {repo_name}")
        logging.info(f"Data to store: {dependency_data}")
        
        try:
            with self.driver.session() as session:
                # Create repository node
                session.run("""
                    MERGE (r:Repository {name: $repo_name})
                """, repo_name=repo_name)
                logging.info("Created repository node")

                # Store endpoints
                logging.info("Storing endpoints...")
                for endpoint in dependency_data.get('endpoints', []):
                    try:
                        self._store_endpoint(session, repo_name, endpoint)
                        logging.info(f"Stored endpoint: {endpoint.get('path')}")
                    except Exception as e:
                        logging.error(f"Error storing endpoint: {str(e)}")

                # Store DTOs
                logging.info("Storing DTOs...")
                for dto_name, dto_info in dependency_data.get('dtos', {}).items():
                    try:
                        self._store_dto(session, repo_name, dto_name, dto_info)
                        logging.info(f"Stored DTO: {dto_name}")
                    except Exception as e:
                        logging.error(f"Error storing DTO: {str(e)}")

                # Store entities
                logging.info("Storing entities...")
                for entity_name, entity_info in dependency_data.get('entities', {}).items():
                    try:
                        self._store_entity(session, repo_name, entity_name, entity_info)
                        logging.info(f"Stored entity: {entity_name}")
                    except Exception as e:
                        logging.error(f"Error storing entity: {str(e)}")

                # Store services
                logging.info("Storing services...")
                for service_name, service_info in dependency_data.get('services', {}).items():
                    try:
                        self._store_service(session, repo_name, service_name, service_info)
                        logging.info(f"Stored service: {service_name}")
                    except Exception as e:
                        logging.error(f"Error storing service: {str(e)}")
                
                logging.info("Completed storing repository data")
        except Exception as e:
            logging.error(f"Error storing repository data: {str(e)}")
            raise

    def _store_endpoint(self, session, repo_name: str, endpoint: Dict):
        session.run("""
            MATCH (r:Repository {name: $repo_name})
            MERGE (e:Endpoint {
                path: $path,
                method: $method,
                controller_class: $controller_class,
                method_name: $method_name,
                repository: $repo_name,
                unique_id: $repo_name + '_' + $controller_class + '_' + $method_name
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
            MERGE (e)-[:RELATES_TO {
                type: rel.type,
                field: rel.field
            }]->(target)
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
            MERGE (s)-[:USES_DTO {methods: $methods}]->(d)
            WITH s
            UNWIND $used_entities AS entity_name
            MERGE (e:Entity {name: entity_name})
            MERGE (s)-[:USES_ENTITY {methods: $methods}]->(e)
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

    def get_all_repositories(self):
        """Get all repositories and their data from Neo4j."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Repository)
                OPTIONAL MATCH (r)<-[:BELONGS_TO]-(e:Endpoint)
                OPTIONAL MATCH (r)<-[:BELONGS_TO]-(d:DTO)
                OPTIONAL MATCH (r)<-[:BELONGS_TO]-(en:Entity)
                OPTIONAL MATCH (r)<-[:BELONGS_TO]-(s:Service)
                WITH r,
                     collect(DISTINCT {
                         path: e.path,
                         method: e.method,
                         controller_class: e.controller_class,
                         method_name: e.method_name,
                         request_dto: e.request_dto,
                         response_dto: e.response_dto
                     }) as endpoints,
                     collect(DISTINCT {
                         name: d.name,
                         fields: d.fields,
                         used_in_controllers: [],
                         mapped_to_entities: []
                     }) as dtos,
                     collect(DISTINCT {
                         name: en.name,
                         table_name: en.table_name,
                         fields: en.fields,
                         relationships: []
                     }) as entities,
                     collect(DISTINCT {
                         name: s.name,
                         methods: s.methods,
                         used_dtos: [],
                         used_entities: []
                     }) as services
                RETURN r.name as repo_name, {
                    endpoints: endpoints,
                    dtos: dtos,
                    entities: entities,
                    services: services
                } as repo_data
            """)
            return [(record["repo_name"], record["repo_data"]) for record in result]

    def close(self):
        self.driver.close()
