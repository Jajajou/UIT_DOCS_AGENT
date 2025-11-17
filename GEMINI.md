# Gemini Project Context: UIT_DOCS_AGENT

This document provides a comprehensive overview of the `UIT_DOCS_AGENT` project, its architecture, and operational procedures.

## Project Overview

This project is a sophisticated, multi-component system designed to create a knowledgeable AI agent based on the content of Ho Chi Minh City University of Information Technology (UIT) websites. It features a complete RAG (Retrieval-Augmented Generation) pipeline, from data ingestion to intelligent query processing.

The system is composed of three main parts:
1.  **Crawling System**: A self-hosted `firecrawl` instance scrapes and ingests documents from specified UIT web pages.
2.  **Knowledge Base**: A `LightRAG` instance processes the crawled documents, creating a searchable knowledge base with a vector database backend.
3.  **AI Agent System**: A multi-agent system built with `LangGraph` that handles both indexing new documents and intelligently answering user queries.

The project is architected as a collection of services orchestrated with Docker and Docker Compose, with key components like `firecrawl` and `LightRAG` included as Git submodules.

### Key Technologies
-   **Backend**: Python, FastAPI
-   **AI/LLM**: LangGraph, LangChain, LightRAG, DeepSeek-OCR
-   **Data Crawling**: Firecrawl, Playwright
-   **Databases**: PostgreSQL with pgvector, Qdrant, Redis
-   **Containerization**: Docker, Docker Compose

## System Architecture

### 1. Data Ingestion Pipeline
Data ingestion is a two-step process involving crawling and indexing.

#### Crawling (`firecrawl/docker-compose.yaml`)
-   A `firecrawl` instance, defined in its own Docker Compose setup, periodically crawls UIT websites based on the configuration in `firecrawl/config.yaml`.
-   It uses a `playwright-service` for rendering JavaScript-heavy pages and `redis` for job queuing.
-   Crawled documents are saved to the shared `./data/` directory.

#### Indexing (`LangGraph/src/agent/indexing_graph.py`)
-   The `indexing_graph` is a LangGraph workflow that processes and indexes new documents.
-   It can be triggered by a user command (e.g., `upload /path/to/file`) or a manual `scan`.
-   For PDF documents, it uses a `DeepSeekOCRClient` to extract high-quality text and layout information.
-   Finally, it uses a `LightRAGAPIClient` to upload the processed documents or text into the `LightRAG` knowledge base.

### 2. Query & Response Pipeline (`LangGraph/src/agent/query_graph.py`)
The query processing is handled by a sophisticated 3-agent RAG pipeline built with LangGraph.

-   **Agent 1: Query Understanding**: Analyzes the user's query, tunes retrieval parameters (e.g., `top_k`, `retrieval_mode`), and can ask clarifying questions if the query is ambiguous.
-   **Retrieval & Reranking**: The system retrieves relevant data (entities, relationships, text chunks) from the `LightRAG` API. A `MultiSourceReranker` then scores and re-ranks all retrieved data to prioritize the most relevant information.
-   **Agent 2: Confidence Assessment**: Evaluates the reranked data to determine a confidence score. If confidence is low, it can ask the user a follow-up question.
-   **Agent 3: Response Generation**: Based on the high-confidence, reranked data, this agent generates the final, context-aware answer for the user. It can produce a full answer, a partial answer, or a fallback response.

### 3. Core Services (`docker-compose.yml`)
-   **`lightrag_uit`**: The core `LightRAG` application that serves the knowledge base API.
-   **`postgres_uit`**: PostgreSQL with `pgvector` for storing vector embeddings.
-   **`qdrant_uit`**: A Qdrant vector database for efficient similarity search.

## Building and Running

The project is designed to be run using Docker and Docker Compose.

### Running the Crawler
```bash
# Navigate to the firecrawl directory
cd firecrawl

# Start all crawling services
docker compose up -d
```

### Running the RAG System & Agent
```bash
# From the project root directory
docker compose up -d
```
The `lightrag_uit` service will expose the knowledge base API, which the LangGraph agent interacts with. The LangGraph agent itself is run as a separate Python application.

## Development Conventions
-   **Modular Architecture**: The project is highly modular. The crawler (`firecrawl`), knowledge base (`LightRAG`), and agent logic (`LangGraph`) are in separate directories/submodules.
-   **Dependency Management**: Python dependencies are managed with `uv` and defined in `pyproject.toml`.
-   **Configuration**: Service configurations are managed through `.env` files. Use the provided `.example` files as templates.
-   **Agent Logic**: The core AI agent logic is defined in the `LangGraph/src/agent/` directory.
    -   `indexing_graph.py`: Defines the data ingestion and indexing workflow.
    -   `query_graph.py`: Defines the multi-agent query processing workflow.
