import os
import git
import shutil
import logging
from pathlib import Path
from typing import List, Dict
import json
from neo4j_store import Neo4jStore
from analyze import JavaSpringParser
from service_mapping import ServiceMappingManager
from feign_client_parser import FeignClientParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RepositoryProcessor:
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        self.neo4j_store = Neo4jStore(neo4j_uri, neo4j_user, neo4j_password)
        self.service_mapping_manager = ServiceMappingManager()
        self.repos_dir = Path("repos")
        self.repos_dir.mkdir(exist_ok=True)
        
        # Get Git credentials from environment
        self.git_username = os.getenv('GIT_USERNAME')
        self.git_password = os.getenv('GIT_PASSWORD')
        
        # Load service mappings
        self.service_mapping_manager.load_from_repositories_file('repositories.txt')

    def process_local_directory(self, dir_path: str):
        """Process a local directory containing the service code."""
        try:
            # Get repository name and service mapping info
            repo_name = os.path.basename(dir_path.rstrip(os.sep))
            logger.info(f"Looking up service mapping for repo: {repo_name}")
            logger.info(f"Full directory path: {dir_path}")
            logger.info(f"Directory exists: {os.path.exists(dir_path)}")
            if os.path.exists(dir_path):
                logger.info(f"Directory contents: {os.listdir(dir_path)}")
            
            friendly_name = self.service_mapping_manager.get_friendly_name(dir_path)
            service_name = self.service_mapping_manager.get_service_name(dir_path)
            base_path = self.service_mapping_manager.get_base_path(dir_path)
            
            logger.info(f"Service mapping results:")
            logger.info(f"- Friendly name: {friendly_name}")
            logger.info(f"- Service name: {service_name}")
            logger.info(f"- Base path: {base_path}")
            
            if not all([friendly_name, service_name, base_path]):
                logger.error(f"Missing service mapping information for {repo_name}")
                return
                
            logger.info(f"Processing local directory: {repo_name} ({friendly_name})")

            # Load application properties for property resolution
            self.service_mapping_manager.load_application_properties(dir_path)

            # Parse Java files
            logger.info(f"Creating parser for directory: {dir_path}")
            logger.info(f"Directory contents: {os.listdir(dir_path)}")
            logger.info(f"Java files: {list(Path(dir_path).rglob('*.java'))}")
            
            # Parse dependencies
            parser = JavaSpringParser(dir_path)
            logger.info("Parsing project...")
            dependency_graph = parser.parse_project()
            logger.info(f"Found {len(dependency_graph.endpoints)} endpoints, {len(dependency_graph.dtos)} DTOs, {len(dependency_graph.entities)} entities, {len(dependency_graph.services)} services")
            
            # Convert to dictionary for Neo4j storage
            logger.info("Converting to dictionary...")
            graph_dict = {
                'endpoints': [endpoint.model_dump() for endpoint in dependency_graph.endpoints],
                'dtos': {name: dto.model_dump() for name, dto in dependency_graph.dtos.items()},
                'entities': {name: entity.model_dump() for name, entity in dependency_graph.entities.items()},
                'services': {name: service.model_dump() for name, service in dependency_graph.services.items()}
            }

            # Parse FeignClient service calls
            logger.info("Parsing FeignClient service calls...")
            feign_parser = FeignClientParser(self.service_mapping_manager)
            service_calls = feign_parser.extract_service_calls(dir_path)
            logger.info(f"Found {len(service_calls)} service calls")

            # Store in Neo4j
            logger.info(f"Storing dependency data for {repo_name} in Neo4j")
            self.neo4j_store.store_repository_data(
                repo_name, friendly_name, service_name, base_path, graph_dict
            )
            
            # Store service calls
            if service_calls:
                logger.info("Storing service calls in Neo4j")
                self.neo4j_store.store_service_calls(repo_name, service_calls)

            logger.info(f"Successfully processed service: {service_name}")
            
            # Optional: Generate and save visualization if Graphviz is available
            try:
                from analyze import DependencyVisualizer
                visualizer = DependencyVisualizer(dependency_graph, service_calls)
                visualizer.create_graph()
                visualizer.save(os.path.join("graphs", f"{service_name}_dependencies"), "png")
                logger.info(f"Generated visualization for {service_name}")
            except Exception as e:
                logger.warning("Could not generate visualization (Graphviz may not be installed). Continuing with analysis...")

        except Exception as e:
            logger.error(f"Error processing directory {dir_path}: {str(e)}")
            raise

    def process_repository(self, repo_url: str):
        try:
            # Extract repository name from URL
            repo_name = repo_url.split('/')[-1].replace('.git', '')
            repo_path = self.repos_dir / repo_name
            
            # Get service mapping info
            friendly_name = self.service_mapping_manager.get_friendly_name(str(repo_path))
            service_name = self.service_mapping_manager.get_service_name(str(repo_path))
            base_path = self.service_mapping_manager.get_base_path(str(repo_path))
            
            if not all([friendly_name, service_name, base_path]):
                logger.error(f"Missing service mapping information for {repo_name}")
                return
            
            logger.info(f"Processing repository: {repo_name} ({friendly_name})")
            
            # Clone or update repository
            if repo_path.exists():
                logger.info(f"Updating existing repository: {repo_name}")
                repo = git.Repo(repo_path)
                repo.remotes.origin.pull()
            else:
                logger.info(f"Cloning repository: {repo_url}")
                # Set up Git credentials if provided
                if self.git_username and self.git_password:
                    git_env = os.environ.copy()
                    # Use platform-independent way to handle Git credentials
                    git_env['GIT_USERNAME'] = self.git_username
                    git_env['GIT_PASSWORD'] = self.git_password
                    
                    # Clone with credentials in environment
                    git.Repo.clone_from(
                        repo_url, 
                        repo_path,
                        env=git_env,
                        allow_unsafe_options=True,
                        config=['credential.helper=store']
                    )
                else:
                    git.Repo.clone_from(repo_url, repo_path)

            # Load application properties for property resolution
            self.service_mapping_manager.load_application_properties(str(repo_path))

            # Parse Java files for dependencies
            parser = JavaSpringParser(str(repo_path))
            dependency_graph = parser.parse_project()
            
            # Convert to dictionary for Neo4j storage
            graph_dict = {
                'endpoints': [endpoint.model_dump() for endpoint in dependency_graph.endpoints],
                'dtos': {name: dto.model_dump() for name, dto in dependency_graph.dtos.items()},
                'entities': {name: entity.model_dump() for name, entity in dependency_graph.entities.items()},
                'services': {name: service.model_dump() for name, service in dependency_graph.services.items()}
            }

            # Parse FeignClient service calls
            logger.info("Parsing FeignClient service calls...")
            feign_parser = FeignClientParser(self.service_mapping_manager)
            service_calls = feign_parser.extract_service_calls(str(repo_path))
            logger.info(f"Found {len(service_calls)} service calls")

            # Store in Neo4j
            logger.info(f"Storing dependency data for {repo_name} in Neo4j")
            self.neo4j_store.store_repository_data(
                repo_name, friendly_name, service_name, base_path, graph_dict
            )
            
            # Store service calls
            if service_calls:
                logger.info("Storing service calls in Neo4j")
                self.neo4j_store.store_service_calls(repo_name, service_calls)

            logger.info(f"Successfully processed repository: {repo_name}")
            
            # Optional: Generate and save visualization
            try:
                from analyze import DependencyVisualizer
                visualizer = DependencyVisualizer(dependency_graph, service_calls)
                visualizer.create_graph()
                visualizer.save(os.path.join("graphs", f"{repo_name}_dependencies"), "png")
            except Exception as e:
                logger.warning(f"Failed to generate visualization for {repo_name}: {str(e)}")

        except Exception as e:
            logger.error(f"Error processing repository {repo_url}: {str(e)}")
            raise

    def process_repositories_file(self, file_path: str):
        """Process a file containing repository URLs or local directories, one per line."""
        try:
            with open(file_path, 'r') as f:
                entries = [line.strip() for line in f if line.strip() and not line.startswith('#')]

            logger.info(f"Found {len(entries)} entries to process")
            
            for entry in entries:
                try:
                    # Split the entry into path and metadata
                    import shlex
                    parts = shlex.split(entry)
                    if len(parts) >= 4:
                        dir_path = parts[0]
                        # Convert Windows paths to proper format
                        dir_path = os.path.normpath(dir_path)
                        logger.info(f"Processing directory: {dir_path}")
                        logger.info(f"Full entry: {entry}")
                        
                        # Check if directory exists
                        if os.path.exists(dir_path):
                            logger.info(f"Directory exists at: {dir_path}")
                            logger.info(f"Contents: {os.listdir(dir_path)}")
                            self.process_local_directory(dir_path)
                        else:
                            logger.error(f"Directory not found: {dir_path}")
                            logger.error(f"Current working directory: {os.getcwd()}")
                    else:
                        self.process_repository(entry)
                except Exception as e:
                    logger.error(f"Failed to process entry {entry}: {str(e)}")
                    continue

            # Generate comprehensive analysis
            self._generate_comprehensive_analysis()
        except Exception as e:
            logger.error(f"Error processing repositories file: {str(e)}")
            raise
        finally:
            self.neo4j_store.close()

    def _generate_comprehensive_analysis(self):
        """Generate a comprehensive analysis of all components."""
        try:
            # 1. Cross-service dependencies
            dependencies = self.neo4j_store.get_cross_service_dependencies()
            
            # 2. Get all DTOs and their impact analysis
            dto_analysis = {}
            for repo_name, repo_data in self.neo4j_store.get_all_repositories():
                for dto in repo_data.get('dtos', []):
                    try:
                        from analyze import JavaSpringParser, DependencyVisualizer
                        parser = JavaSpringParser(str(self.repos_dir / repo_name))
                        dependency_graph = parser.parse_project()
                        visualizer = DependencyVisualizer(dependency_graph)
                        dto_name = dto.get('name')
                        if dto_name:
                            dto_analysis[f"{repo_name}/{dto_name}"] = visualizer.get_impact_analysis(dto_name)
                    except Exception as e:
                        logger.warning(f"Failed to analyze DTO {dto_name} in {repo_name}: {str(e)}")

            # 3. Generate comprehensive report
            report = {
                "cross_service_dependencies": dependencies,
                "dto_analysis": dto_analysis,
                "summary": {
                    "total_dependencies": len(dependencies),
                    "affected_repositories": len(set(
                        [d["from_repo"] for d in dependencies] +
                        [d["to_repo"] for d in dependencies]
                    )),
                    "total_dtos_analyzed": len(dto_analysis)
                },
                "components": {}
            }

            # Process each repository's data
            for repo_name, repo_data in self.neo4j_store.get_all_repositories():
                report["components"][repo_name] = {
                    "endpoints": [
                        {
                            "path": endpoint.get("path"),
                            "method": endpoint.get("method"),
                            "controller": endpoint.get("controller_class"),
                            "request_dto": endpoint.get("request_dto"),
                            "response_dto": endpoint.get("response_dto")
                        }
                        for endpoint in repo_data.get('endpoints', [])
                    ],
                    "services": [
                        {
                            "name": service.get("name"),
                            "methods": service.get("methods", []),
                            "used_dtos": service.get("used_dtos", []),
                            "used_entities": service.get("used_entities", [])
                        }
                        for service in repo_data.get('services', [])
                    ],
                    "entities": [
                        {
                            "name": entity.get("name"),
                            "table": entity.get("table_name"),
                            "fields": {
                                field.split(':')[0]: field.split(':')[1]
                                for field in (entity.get("fields", "") or "").split(',')
                                if field and ':' in field
                            },
                            "relationships": entity.get("relationships", [])
                        }
                        for entity in repo_data.get('entities', [])
                    ]
                }

            # Save comprehensive report
            with open('dependency_analysis.json', 'w') as f:
                json.dump(report, f, indent=2)
                
            logger.info("Generated comprehensive analysis: dependency_analysis.json")
            
            # 4. Try to generate visualizations if Graphviz is available
            try:
                # Create graphs directory if it doesn't exist
                Path("graphs").mkdir(exist_ok=True)
                
                for repo_name, repo_data in self.neo4j_store.get_all_repositories():
                    try:
                        parser = JavaSpringParser(str(self.repos_dir / repo_name))
                        dependency_graph = parser.parse_project()
                        
                        # Get service calls for visualization
                        feign_parser = FeignClientParser(self.service_mapping_manager)
                        service_calls = feign_parser.extract_service_calls(str(self.repos_dir / repo_name))
                        
                        visualizer = DependencyVisualizer(dependency_graph, service_calls)
                        visualizer.create_graph()
                        visualizer.save(os.path.join("graphs", f"{repo_name}_dependencies"), "png")
                        logger.info(f"Generated visualization for {repo_name}")
                    except Exception as e:
                        logger.warning("Could not generate visualization (Graphviz may not be installed). Continuing with analysis...")
            except Exception as e:
                logger.warning("Could not create graphs directory. Skipping visualizations.")
            
        except Exception as e:
            logger.error(f"Error generating comprehensive analysis: {str(e)}")
            raise
        finally:
            self.neo4j_store.close()

    def _generate_dependency_report(self):
        """Generate a report of cross-service dependencies."""
        try:
            dependencies = self.neo4j_store.get_cross_service_dependencies()
            
            report = {
                "cross_service_dependencies": dependencies,
                "summary": {
                    "total_dependencies": len(dependencies),
                    "affected_repositories": len(set(
                        [d["from_repo"] for d in dependencies] +
                        [d["to_repo"] for d in dependencies]
                    ))
                }
            }

            # Save report
            with open('dependency_report.json', 'w') as f:
                json.dump(report, f, indent=2)
                
            logger.info("Generated cross-service dependency report: dependency_report.json")
            
        except Exception as e:
            logger.error(f"Error generating dependency report: {str(e)}")

def main():
    # Get configuration from environment
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD', 'password123')
    repositories_file = os.getenv('REPOSITORIES_FILE', 'repositories.txt')

    # Create processor and process repositories
    processor = RepositoryProcessor(neo4j_uri, neo4j_user, neo4j_password)
    processor.process_repositories_file(repositories_file)

if __name__ == "__main__":
    main()
