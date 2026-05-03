# Technology Stack
**Project:** Vietnamese University Chatbot
**Researched:** 2026-04-29

## Recommended Stack

### Core Framework
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Qwen/Qwen3-4B-Instruct | 2026 | LLM Framework | Proven Vietnamese language capabilities, temporal document understanding |
| Vietnamese_Embedding_V2 | latest | Text embeddings | State-of-the-art Vietnamese semantic search |
| PostgreSQL | 15+ | Metadata storage | Temporal metadata, document versioning |
| LangGraph | latest | RAG orchestration | Multi-agent workflow management |

### Database
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Qdrant | latest | Vector storage | Fast similarity search |
| PostgreSQL | latest | Metadata persistence | Temporal document tracking |

### Infrastructure
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker | latest | Container orchestration | Reproducible environments |
| FastAPI | latest | API layer | Real-time query processing |

### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| LangChain | latest | Agent orchestration | Multi-step workflows |
| Pydantic | 2.0+ | Data validation | Structured output typing |
| Reranker | latest | Result scoring | Temporal + semantic scoring |
| Vietnamese_Embedding_V2 | latest | Semantic search | Document understanding |
| DeepSeek-OCR | 2.0+ | Document processing | PDF text extraction |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| LLM | Qwen3/Qwen3-4B | GPT-4 | Better Vietnamese support in Qwen3 |
| Embedding | Vietnamese_Embedding_V2 | multilingual-256 | Proven performance on Vietnamese text |
| RAG | LightRAG | other frameworks | Built-in temporal scoring support |