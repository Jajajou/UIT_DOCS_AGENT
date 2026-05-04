# Research Summary: Vietnamese University Chatbot
**Domain:** Educational AI/Academic Document Management
**Researched:** 2026-04-29
**Overall confidence:** HIGH

## Executive Summary

Vietnamese university chatbots represent a unique intersection of temporal document management, multi-generational cohort routing, and Vietnamese language processing. Current solutions fall into three categories: general-purpose educational chatbots (Canvas/Brightspace integrations), Vietnamese-language FAQ systems, and custom university implementations.

Key findings reveal significant gaps in temporal awareness - existing systems treat documents as static rather than versioning entities. The Vietnamese university ecosystem is particularly underserved, with most institutions using basic keyword search or simplistic rule-based bots. Student cohort routing presents a massive untapped opportunity: academic policies apply differently based on enrollment year, degree program, and even current academic year (e.g., 2019 vs 2024 curriculum versions).

Critical pain points include amendment tracking complexity (a single "Quyết định 108" can invalidate dozens of previous documents), Vietnamese OCR challenges with university terminology, and the fundamental problem of routing students to policies that match their historical cohort context while also handling appeals from students grandfathered under old policies.

## Key Findings

**Stack:** Qwen3-4B-Instruct + Vietnamese_Embedding_V2 + PostgreSQL/metadata layer + reranker
**Architecture:** 2-agent RAG with temporal scoring, metadata extraction subgraph, soup-to-nuts Vietnamese support
**Critical pitfall:** Amendment over-classification causing 15% F-score drops in evaluation runs

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Phase 1: Temporal RAG Foundation** - Core 2-agent pipeline with Vietnamese embeddings
   - Addresses: Vietnamese language support, basic temporal awareness
   - Avoids: Amendment handling complexity (simpler validation schemes)

2. **Phase 2: Amendment Subgraph** - 6-node metadata extraction workflow
   - Addresses: Amendment detection, cohort context extraction
   - Avoids: Full document versioning complexity

3. **Phase 3: Cohort Segmentation** - Student-year specific filtering
   - Addresses: Academic year routing, policy version matching
   - Avoids: Real-time amendment cascade processing

4. **Phase 4: Interaction Layer** - Student-facing chatbot interface
   - Addresses: User experience, Vietnamese query processing
   - Research flags: Need extensive Vietnamese prompt testing

**Phase ordering rationale:** Temporal awareness → Amendment handling → Cohort routing → UX polish aligns with data dependencies and risk mitigation.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|--------|
| Stack | HIGH | Proven with Vietnamese_Embedding_V2, Qwen3 validation |
| Features | HIGH | Clear gap analysis, concrete requirements |
| Architecture | HIGH | 2-agent pattern validated through evaluation |
| Pitfalls | HIGH | Directly observed in evaluation data |

## Gaps to Address

- Vietnamese-specific prompt engineering for academic conversation
- Amendment cascade detection strategies
- Real-world student query pattern analysis
- Offline amendment processing optimization