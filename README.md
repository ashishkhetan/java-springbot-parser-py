# Java Spring Boot Microservices Dependency Analyzer

This tool analyzes Java Spring Boot microservices to map dependencies between services, DTOs, and database entities, storing the results in Neo4j for advanced querying and visualization.

## Features

- Analyzes multiple Spring Boot repositories
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

2. Configure repositories to analyze:
Edit `repositories.txt` and add your Spring Boot repository URLs:
```
https://github.com/your-org/service1.git
https://github.com/your-org/service2.git
```

3. Start the services:
```bash
docker-compose up --build
```

This will:
- Start Neo4j database
- Build and start the parser service
- Process all repositories in repositories.txt
- Store dependency data in Neo4j

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
RETURN d.name, r.name
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

- `graphs/`: Contains generated dependency visualizations for each repository
- `dependency_report.json`: Cross-service dependency analysis report
- Neo4j database: Contains all dependency data for advanced querying

## Environment Variables

Configure these in `.env` file:
- `NEO4J_URI`: Neo4j connection URI
- `NEO4J_USER`: Neo4j username
- `NEO4J_PASSWORD`: Neo4j password
- `REPOSITORIES_FILE`: Path to repositories list file

## Architecture

1. **Repository Processing**:
   - Clones/updates Git repositories
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
docker-compose up --build
```

2. To reset all data:
```bash
docker-compose down -v
rm -rf repos graphs dependency_report.json
docker-compose up --build
```

3. To view logs:
```bash
docker-compose logs -f parser  # Parser service logs
docker-compose logs -f neo4j   # Neo4j logs
