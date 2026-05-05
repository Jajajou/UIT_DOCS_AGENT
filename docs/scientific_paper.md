# Temporal-Aware Retrieval-Augmented Generation for Vietnamese Academic Regulations

## Abstract
Navigating university regulations is challenging due to temporal dependencies (amendments, validity periods) and Vietnamese linguistic nuances. We propose **UITRaph**, a temporal-aware RAG system that integrates a Knowledge Graph (LightRAG) with a PostgreSQL-based metadata store. Key innovations include a **Metadata RAG Subgraph** (achieving 0.92 confidence) and an instant metadata synchronization mechanism via `track_id` (achieving 60x speedup).

## 1. Introduction
Traditional RAG systems often fail when legal documents are amended or applicable only to specific student cohorts. UITRaph addresses these challenges specifically for Ho Chi Minh City University of Information Technology (UIT).

## 2. System Design
The architecture consists of three primary layers, optimized for legal precision:

### Fig 1: System Overview
![Figure 1](../../uit-thesis-template-latex/undergraduate_thesis/graphics/scientific_paper_fig_1.png)

### Fig 2: Indexing Pipeline Detail
![Figure 2](../../uit-thesis-template-latex/undergraduate_thesis/graphics/scientific_paper_fig_2.png)

### Fig 3: Metadata RAG Subgraph (The 6-Node Workflow)
![Figure 3](../../uit-thesis-template-latex/undergraduate_thesis/graphics/scientific_paper_fig_3.png)

- **Data Acquisition**: Firecrawl-based ingestion of PDF/HTML documents.
- **Indexing Pipeline**: 
    - OCR via **MinerU** (Preserves Markdown structure for tables/clauses).
    - **Metadata RAG Subgraph**: A 6-node workflow achieving **0.92 confidence** (Proof: `docs/PROGRESS\_LOG.md`).
    - **Innovation**: Instant metadata sync via `track_id` (60x faster, Proof: `docs/PROGRESS\_LOG.md`).
- **Query Pipeline**: A 2-agent LangGraph workflow (understanding and generation), reduced from 3 agents to save **~2.5s latency** (Proof: `docs/technical\_report.md`).
    - **Temporal Reranking**: A hybrid scoring model (70% semantic / 30% temporal).


## 3. Technology Stack
- **Embedding**: `AITeamVN/Vietnamese_Embedding_v2` (Proof: `LangGraph/src/agent/config.py`).
- **Reranker**: `ViRanker` (Vietnamese cross-encoder).
- **RAG Engine**: `LightRAG` (Graph-based for relation awareness).

## 4. Evaluation (PLACEHOLDER)
*Evaluation results are currently being updated. Initial benchmarks on a 100-pair temporal dataset showed a baseline accuracy of 42%, revealing a sampling bias in smaller datasets and identifying amendment boundary handling as a primary challenge (31% accuracy).*

## 5. Conclusion
UITRaph demonstrates the feasibility of temporal-aware RAG for Vietnamese legal texts. Future work will focus on transitive amendment closure and multi-hop legal reasoning.
