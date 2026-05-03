# UIT Student Chatbot - Thesis Project

## Project Context
Building intelligent Q&A chatbot for Ho Chi Minh City University of Information Technology (UIT) students with advanced temporal and cohort-aware document retrieval capabilities.

## Problem Statement

**Challenge:** UIT students struggle to find correct academic information across thousands of documents spanning multiple academic years with complex temporal relationships (amendments, replacements, expiry dates, cohort-specific policies).

**Current Pain Points:**
- Students can't distinguish active vs expired policies
- Amendment documents cause confusion (returning old superseded policies)
- Cohort-specific policies aren't properly routed (2025 cohort policy vs 2026 policy)
- No temporal understanding of document validity periods
- Vietnamese document processing limitations

## Project Foundation
**Existing System Architecture:**
- **Index Pipeline:** Firecrawl → LightRAG (graph-based RAG) → PostgreSQL metadata storage
- **Temporal Engine:** 6-node metadata RAG subgraph with confidence scoring
- **Query Pipeline:** 2-agent retrieval with temporal reranking
- **Live Components:** DeepSeek-OCR for PDF processing, Vietnamese embeddings, cohort detection

**Current Features (v0.3.2):**
- ✅ Document indexing with temporal metadata extraction
- ✅ Amendment/amends relationship detection
- ✅ Validity period tracking (valid_from/to)
- ✅ Cohort year extraction and routing
- ✅ Vietnamese language processing
- ✅ Confidence-based retrieval with fallbacks

**Next Phase Requirements:**
- Enhanced chatbot interface for students
- Real-time temporal warnings (expiry, amendments)
- Cohort-specific query routing optimization
- Academic calendar integration
- Multi-format support (PDFs, web pages)

## Target Users
**Primary:** UIT undergraduate students (15,000+ active)
**Secondary:** Graduate students, faculty, administration
**Use Cases:**
- Academic policy questions
- Course registration guidance
- Scholarship/credit requirements
- Graduation prerequisites
- Document status inquiries (missing/expired)

## Technical Constraints
**Timeline:** Thesis defense this week
**Existing Infrastructure:** Docker services (LightRAG, PostgreSQL, Qdrant)
**Models:** Qwen3-4B-Instruct, Vietnamese_Embedding_V2, ViRanker reranker
**Data:** ~2,800 Vietnamese academic documents across 2020-2025 academic years
**Performance:** 3-second response target, 80%+ accuracy on student queries