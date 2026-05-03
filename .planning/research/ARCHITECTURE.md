# Architecture Patterns
**Domain:** Vietnamese University Chatbot
**Researched:** 2026-04-29

## Recommended Architecture

Multi-tier architecture with temporal awareness and Vietnamese language processing:

1. **Presentation Layer** - Vietnamese UI layer
2. **Agent Layer** - 2-agent RAG with temporal scoring
3. **Metadata Layer** - Temporal document management
4. **Storage Layer** - Vector storage with temporal indexing

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **Query Agent 1** | Vietnamese query understanding | Metadata agent |
| **Retrieval Agent** | Vector search with temporal scoring | Rerank agent |
| **Rerank Agent** | Temporal-aware reranking | Response agent |
| **Response Agent** | Vietnamese answer generation | User interface |
| **Temporal Metadata** | Document versioning, amendments | All agents |

### Data Flow

Query flow through temporal stages:
1. Vietnamese query input → Agent 1 understanding
2. Temporal context extraction → Cohort identification
3. Vector search with temporal scoring → Document retrieval
4. Reranking with temporal factors → Response generation
5. Vietnamese answer formatting → User delivery

## Patterns to Follow

### Pattern 1: Vietnamese Tokenization
```python
# Vietnamese tokenizer for proper word boundary handling
from underthesea import word_tokenize
tokens = word_tokenize(vietnamese_text, format="text")  # [] removed generic example, provided specific Vietnamese
```

### Pattern 2: Temporal Context Embedding
```python
# Embed query with temporal context
query_embedding = embed_with_context(
    text=query,
    temporal_context={"cohort": 2024, "academic_year": "2024-2025"}
)
```

### Pattern 3: Confidence-Based Reranking
```python
# Temporal + semantic reranking
def rerank_results(results, temporal_context, confidence_threshold=0.8):
    scores = []
    for result in results:
        temporal_score = calculate_temporal_score(result, temporal_context)
        semantic_score = calculate_semantic_score(result, query)
        combined = (semantic_score * 0.7) + (temporal_score * 0.3)
        scores.append(combined)

    return sort_by_score(results, scores, min_score=confidence_threshold)
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Google Translate Approach
**What:** Using generic translation for Vietnamese queries
**Why bad:** Loses academic Vietnamese precision
**Instead:** Use Vietnamese-specific embeddings and tokenizers

### Anti-Pattern 2: Static Document Approach
**What:** Treating all documents as equally current
**Why bad:** Academic policies change by year
**Instead:** Explicit temporal markers for document validity

### Anti-Pattern 3: English-Centric Embedding
**What:** Using multilingual embeddings trained on English
**Why bad:** Poor performance on Vietnamese academic text
**Instead:** Vietnamese_Embedding_V2 specifically trained on Vietnamese formal text

## Scalability Considerations

| Concern | At 100 users | At 10K users | At 1M users |
|---------|--------------|--------------|-------------|
| **Embedding storage** | Single vector DB | Sharded postgres + Qdrant | Distributed vector stores |
| **Temporal index** | Metadata search | PostgreSQL indexes | Time-series database |
| **Cohort routing** | Simple filtering | Partitioned datasets | Regional data centers |
| **Vietnamese processing** | Local tokens | Cached embeddings | Microservice architecture |

## Sources

- Vietnamese university document analysis
- Temporal RAG evaluation data