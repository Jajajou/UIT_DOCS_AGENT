# UIT_DOCS_AGENT: AI Agent for Ho Chi Minh City University of Information Technology Documents

This project develops a sophisticated, multi-component AI agent to process and answer queries based on content from Ho Chi Minh City University of Information Technology (UIT) websites. It features a complete RAG (Retrieval-Augmented Generation) pipeline, from data ingestion to intelligent query processing, orchestrated with Docker and Docker Compose.

## Project Overview

The `UIT_DOCS_AGENT` system comprises three main parts:

1.  **Crawling System**: A self-hosted `firecrawl` instance responsible for scraping and ingesting documents from specified UIT web pages.
2.  **Knowledge Base**: A `LightRAG` instance that processes crawled documents, creating a searchable knowledge base with a vector database backend.
3.  **AI Agent System**: A multi-agent system built with `LangGraph` that manages both indexing new documents and intelligently answering user queries.

**Key Innovation:** Temporal-aware RAG with Vietnamese document pattern recognition, cohort-specific retrieval, and RAG-based metadata extraction using a 6-node subgraph (0.92 confidence). The system handles document amendments, validity periods, and student cohort mappings to ensure users always get the most current and relevant information.

## Key Technologies

*   **Backend**: Python, FastAPI
*   **AI/LLM**: LangGraph, LangChain, LightRAG, DeepSeek-OCR
*   **Data Crawling**: Firecrawl, Playwright
*   **Databases**: PostgreSQL with pgvector, Qdrant, Redis
*   **Containerization**: Docker, Docker Compose

## System Architecture

The system is designed with a modular architecture, enabling scalable data ingestion and intelligent query processing.

### 1. Data Ingestion Pipeline

Data ingestion is a two-step process: crawling and indexing.

#### Crawling (`firecrawl/docker-compose.yaml`)

A `firecrawl` instance periodically crawls UIT websites based on the configuration in `firecrawl/config.yaml`. It utilizes a `playwright-service` for rendering JavaScript-heavy pages and `redis` for job queuing. Crawled documents are saved to the shared `./data/` directory.

#### Indexing (`LangGraph/src/agent/indexing_graph.py`)

The `indexing_graph` (a LangGraph workflow) processes and indexes new documents. It can be triggered by user commands (e.g., `upload /path/to/file`) or a manual `scan`. For PDF documents, it:

1. Uses `DeepSeekOCRClient` for high-quality text and layout extraction
2. Extracts temporal metadata using the **Metadata RAG Subgraph** (6-node workflow):
   - Chunks document with Vietnamese embeddings
   - RAG retrieval for metadata fields (document number, dates, cohorts, amendments)
   - Confidence scoring and Pydantic validation
   - Achieves 0.92 confidence on test documents
3. Uploads content and metadata to the `LightRAG` knowledge base via `LightRAGAPIClient`
4. Saves temporal metadata to PostgreSQL for temporal-aware retrieval

### 2. Query & Response Pipeline (`LangGraph/src/agent/query_graph.py`)

A sophisticated 3-agent RAG pipeline built with LangGraph handles query processing:

*   **Agent 1: Query Understanding**: Analyzes the user's query, tunes retrieval parameters (e.g., `top_k`, `retrieval_mode`), and can ask clarifying questions.
*   **Retrieval & Reranking**: Retrieves relevant data (entities, relationships, text chunks) from the `LightRAG` API. A `MultiSourceReranker` (Vietnamese cross-encoder ViRanker) scores and re-ranks this data for optimal relevance. **Temporal scoring** applies penalties to expired or amended documents (70% semantic + 30% temporal).
*   **Agent 2: Confidence Assessment**: Evaluates reranked data for a confidence score. Low confidence may trigger follow-up questions. Applies freshness penalties for expired documents.
*   **Agent 3: Response Generation**: Generates a context-aware answer (full, partial, or fallback) based on high-confidence, reranked data. Can include expiration warnings for documents nearing their validity period.

### 3. Core Services (`docker-compose.yml`)

The main Docker Compose setup orchestrates these services:

*   **`lightrag_uit`**: The core `LightRAG` application, serving the knowledge base API.
*   **`postgres_uit`**: PostgreSQL with `pgvector` for storing vector embeddings.
*   **`qdrant_uit`**: A Qdrant vector database for efficient similarity search.

## Building and Running

The project is designed to be run using Docker and Docker Compose. Ensure you have Docker installed and allocated at least 4GB of RAM, and your system has 8GB+ RAM and 10GB+ free disk space.

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Jajajou/UIT_DOCS_AGENT.git
cd UIT_DOCS_AGENT

# Copy example environment files
cp .env.example .env
cp env.lightrag.example env.lightrag
```

### 2. Configuration

*   **Main Configuration**: Edit `.env` for general project settings.
    ```bash
    # Crawler schedule in hours (e.g., 24 for daily)
    SCHEDULE_HOURS=24
    # Maximum concurrent workers for crawling
    MAX_WORKERS=3
    # Set to true to run the crawler once and then stop
    RUN_ONCE=false
    # Authentication key for Bull Queue UI (replace CHANGEME)
    BULL_AUTH_KEY=CHANGEME
    ```
*   **LightRAG Configuration**: Edit `env.lightrag` for LightRAG specific settings.
*   **Crawler URLs**: Modify `firecrawl/config.yaml` to change the URLs to be crawled and specify `include_patterns` and `exclude_patterns`.

### 3. Running Services

```bash
# Start all services (crawler, LightRAG, databases)
docker compose up -d

# The first run may take 5-10 minutes for initialization.
```

### 4. Checking Status and Logs

```bash
# Check service status
docker compose ps

# View crawler logs
docker logs firecrawl-uit-crawler -f

# View all service logs
docker compose logs -f
```

### 5. Accessing Bull Queue UI

Open your browser to: `http://localhost:3002/admin/YOUR_BULL_AUTH_KEY/queues`
(Replace `YOUR_BULL_AUTH_KEY` with the value set in your `.env` file for `BULL_AUTH_KEY`).

## Stopping Services

```bash
# Stop all services
docker compose down

# Stop services and remove associated volumes (data)
docker compose down -v
```

## Troubleshooting

*   **Services not starting**:
    *   Check logs: `docker logs <service_name>` (e.g., `docker logs firecrawl-api`)
    *   Restart services: `docker compose restart`
    *   Ensure Docker has at least 4GB RAM allocated.
*   **Out of Memory**:
    *   Increase Docker RAM allocation to 4GB+.
    *   Reduce `MAX_WORKERS` in `.env` to 1 or 2.
    *   Close other demanding applications.
*   **Connection Refused**:
    *   Allow 5-10 minutes for initial startup.
    *   Verify all services are "healthy" with `docker compose ps`.

## Development Conventions

*   **Modular Architecture**: The project is highly modular, with separate directories/submodules for the crawler (`firecrawl`), knowledge base (`LightRAG`), and agent logic (`LangGraph`).
*   **Dependency Management**: Python dependencies are managed with `uv` and defined in `pyproject.toml`.
*   **Configuration**: Service configurations are managed through `.env` files. Use the provided `.example` files as templates.
*   **Agent Logic**: The core AI agent logic is defined in `LangGraph/src/agent/` directory:
    *   `indexing_graph.py`: Defines the data ingestion and indexing workflow.
    *   `query_graph.py`: Defines the multi-agent query processing workflow.

## License

MIT