import os
import git
import shutil
import logging
from pathlib import Path
from typing import List, Dict
import json
from neo4j_store import Neo4jStore
from analyze import JavaSpringParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RepositoryProcessor:
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        self.neo4j_store = Neo4jStore(neo4j_uri, neo4j_user, neo4j_password)
        self.repos_dir = Path("repos")
        self.repos_dir.mkdir(exist_ok=True)
        
        # Get Git credentials from environment
        self.git_username = os.getenv('GIT_USERNAME')
        self.git_password = os.getenv('GIT_PASSWORD')

    def process_repository(self, repo_url: str):
        try:
            # Extract repository name from URL
            repo_name = repo_url.split('/')[-1].replace('.git', '')
            repo_path = self.repos_dir / repo_name
            
            logger.info(f"Processing repository: {repo_name}")
            
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
                    git_env['GIT_ASKPASS'] = 'echo'
                    git_env['GIT_USERNAME'] = self.git_username
                    git_env['GIT_PASSWORD'] = self.git_password
                    
                    # Clone with credentials in environment
                    git.Repo.clone_from(
                        repo_url, 
                        repo_path,
                        env=git_env,
                        config=['credential.helper=store']
                    )
                else:
                    git.Repo.clone_from(repo_url, repo_path)

            # Parse Java files
            parser = JavaSpringParser(str(repo_path))
            dependency_graph = parser.parse_project()
            
            # Convert to dictionary for Neo4j storage
            graph_dict = {
                'endpoints': [endpoint.dict() for endpoint in dependency_graph.endpoints],
                'dtos': {name: dto.dict() for name, dto in dependency_graph.dtos.items()},
                'entities': {name: entity.dict() for name, entity in dependency_graph.entities.items()},
                'services': {name: service.dict() for name, service in dependency_graph.services.items()}
            }

            # Store in Neo4j
            logger.info(f"Storing dependency data for {repo_name} in Neo4j")
            self.neo4j_store.store_repository_data(repo_name, graph_dict)

            logger.info(f"Successfully processed repository: {repo_name}")
            
            # Optional: Generate and save visualization
            try:
                from analyze import DependencyVisualizer
                visualizer = DependencyVisualizer(dependency_graph)
                visualizer.create_graph()
                visualizer.save(f"graphs/{repo_name}_dependencies", "png")
            except Exception as e:
                logger.warning(f"Failed to generate visualization for {repo_name}: {str(e)}")

        except Exception as e:
            logger.error(f"Error processing repository {repo_url}: {str(e)}")
            raise

    def process_repositories_file(self, file_path: str):
        """Process a file containing repository URLs, one per line."""
        try:
            with open(file_path, 'r') as f:
                repos = [line.strip() for line in f if line.strip()]

            logger.info(f"Found {len(repos)} repositories to process")
            
            for repo_url in repos:
                try:
                    self.process_repository(repo_url)
                except Exception as e:
                    logger.error(f"Failed to process repository {repo_url}: {str(e)}")
                    continue

            # Generate cross-service dependency report
            self._generate_dependency_report()

        except Exception as e:
            logger.error(f"Error processing repositories file: {str(e)}")
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
