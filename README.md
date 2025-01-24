# Java Spring Boot Microservices Dependency Analyzer

This tool analyzes Java Spring Boot microservices to map dependencies between services, DTOs, and database entities, storing the results in Neo4j for advanced querying and visualization.

## Features

- Analyzes multiple Spring Boot repositories (both public and private)
- Supports analyzing local service directories
- Maps dependencies between:
  - REST endpoints
  - DTOs (Data Transfer Objects)
  - Database entities
  - Services
- Stores dependency data in Neo4j graph database
- Generates visual dependency graphs
- Provides cross-service dependency analysis
- Supports Docker deployment

## Prerequisites

- Docker and Docker Compose
- Git (for cloning repositories)
- Graphviz (for visualization)

## Setup

1. Clone this repository:
```bash
git clone <this-repo-url>
cd <repo-directory>
```

2. Create a `.env` file with the following configuration:
```env
# Neo4j Configuration
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123

# Git Authentication (for private repositories)
GIT_USERNAME=your_github_username
GIT_PASSWORD=your_github_password_or_token

# Local Services Directory (optional)
SERVICES_DIR=/path/to/your/services
```

3. Configure services to analyze:
Edit `repositories.txt` and add either repository URLs or local directory paths:
```
# Git repositories
https://github.com/org/public-repo.git
https://github.com/org/private-repo.git

# Local directories (paths relative to SERVICES_DIR)
/my-service
/another-service
```

You can analyze services from:
- Git repositories (both public and private)
- Local directories (services already on your machine)

4. Start the services:
```bash
docker-compose up --build -d
```

This will:
- Start Neo4j database
- Build and start the parser service
- Process all repositories and local directories in repositories.txt
- Store dependency data in Neo4j

## Local Development

For local development and debugging, you can use Python virtual environments instead of Docker. Below are instructions for both Windows and macOS:

### Windows Setup

1. Create a Python virtual environment:
```powershell
python -m venv venv
.\venv\Scripts\activate
```

2. Install dependencies:
```powershell
pip install -r requirements.txt
```

3. Install Graphviz:
- Download the Windows installer from https://graphviz.org/download/
- Run the installer
- Add Graphviz to your system PATH (the installer should do this automatically)

### macOS Setup

1. Create a Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install Graphviz using Homebrew:
```bash
brew install graphviz
```

### Common Setup (Both Platforms)

4. Configure your .env file for local development:
```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
SERVICES_DIR=/path/to/your/services
```

5. Start Neo4j using Docker:
```bash
docker-compose up neo4j -d
```

6. Run the Python scripts:
```bash
# Process repositories
python process_repositories.py

# Analyze dependencies
python analyze.py
```

This setup allows you to:
- Use your IDE's debugging features
- Make code changes without rebuilding Docker containers
- Run scripts individually for testing
- Set breakpoints and inspect variables

## Authentication

### Private Repositories
The tool supports authentication for private repositories through environment variables:

1. **GitHub**:
   - Set `GIT_USERNAME` and `GIT_PASSWORD` in your `.env` file
   - For `GIT_PASSWORD`, you can use a personal access token (recommended)
   - Use regular HTTPS URLs in `repositories.txt`

2. **Self-hosted Bitbucket**:
   - Set `GIT_USERNAME` and `GIT_PASSWORD` in your `.env` file
   - Use your Bitbucket username and password/token
   - Use standard HTTPS URLs without credentials:
   ```
   https://bitbucket.your-domain.com/scm/project/repo.git
   ```
   - The tool uses Git's credential system, which is compatible with enterprise environments

Note: The tool no longer supports embedding credentials in URLs as this method is not compatible with some enterprise environments.

## Local Directory Analysis

To analyze services from your local machine:

1. Set the `SERVICES_DIR` environment variable in `.env`:
```env
SERVICES_DIR=/path/to/your/services
```

2. Add local directory paths to `repositories.txt`:
```
# Local directories are specified relative to SERVICES_DIR
/service1
/service2/backend
```

3. The tool will analyze these directories directly without cloning.

## Accessing Results

### Neo4j Browser
1. Open `http://localhost:7474` in your browser
2. Login with:
   - Username: neo4j
   - Password: password123

### Sample Queries

1. Find all DTOs used across services:
```cypher
MATCH (d:DTO)-[:BELONGS_TO]->(r:Repository)
RETURN d.name, d.fields, r.name
```

2. Find cross-service dependencies:
```cypher
MATCH (r1:Repository)-[:CONTAINS]->(s1:Service)-[:USES_DTO]->(d:DTO)<-[:USES_DTO]-(s2:Service)<-[:CONTAINS]-(r2:Repository)
WHERE r1 <> r2
RETURN r1.name, s1.name, d.name, s2.name, r2.name
```

3. Impact analysis for a DTO:
```cypher
MATCH (d:DTO {name: 'UserLocationDTO'})
OPTIONAL MATCH (d)<-[:USES_REQUEST_DTO|RETURNS_RESPONSE_DTO]-(e:Endpoint)
OPTIONAL MATCH (d)<-[:USES_DTO]-(s:Service)
OPTIONAL MATCH (d)-[:MAPS_TO]->(entity:Entity)
RETURN d.name, 
       collect(DISTINCT e.path) as affected_endpoints,
       collect(DISTINCT s.name) as affected_services,
       collect(DISTINCT entity.table_name) as affected_tables
```

## Generated Files

- `graphs/`: Contains generated dependency visualizations for each repository/service
- `dependency_report.json`: Cross-service dependency analysis report
- Neo4j database: Contains all dependency data for advanced querying

## Environment Variables

Configure these in `.env` file:
- `NEO4J_URI`: Neo4j connection URI (default: bolt://neo4j:7687)
- `NEO4J_USER`: Neo4j username (default: neo4j)
- `NEO4J_PASSWORD`: Neo4j password (default: password123)
- `REPOSITORIES_FILE`: Path to repositories list file (default: repositories.txt)
- `GIT_USERNAME`: GitHub/Bitbucket username for private repositories
- `GIT_PASSWORD`: GitHub/Bitbucket password or personal access token
- `SERVICES_DIR`: Path to directory containing local services (optional)

## Architecture

1. **Service Processing**:
   - Clones/updates Git repositories (with authentication if needed)
   - Analyzes local service directories
   - Parses Java source files
   - Extracts dependency information

2. **Data Storage**:
   - Stores dependency data in Neo4j
   - Creates relationships between components
   - Enables complex dependency queries

3. **Visualization**:
   - Generates dependency graphs
   - Shows relationships between components
   - Color-coded by component type

## Troubleshooting

1. If Neo4j fails to start:
```bash
docker-compose down -v
docker-compose up --build -d
```

2. To reset all data:
```bash
docker-compose down -v
rm -rf repos graphs dependency_report.json
docker-compose up --build -d
```

3. To view logs:
```bash
docker-compose logs -f parser  # Parser service logs
docker-compose logs -f neo4j   # Neo4j logs
```

4. If authentication fails for private repositories:
   - Verify GIT_USERNAME and GIT_PASSWORD in .env
   - For GitHub, ensure your personal access token has repo scope
   - Check the parser logs for detailed error messages:
   ```bash
   docker-compose logs parser
   ```

5. After changing environment variables in `.env`:
   - Restart the services to apply the changes:
   ```bash
   docker-compose down
   docker-compose up --build -d
   ```

6. If local directory analysis fails:
   - Verify SERVICES_DIR path in .env is correct
   - Ensure the paths in repositories.txt are relative to SERVICES_DIR
   - Check file permissions for the mounted directories
