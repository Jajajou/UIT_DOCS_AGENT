# UIT_DOCS_AGENT Implementation Roadmap

This document outlines the implementation roadmap for the UIT student chatbot thesis project, organized into three distinct phases that build upon each other to deliver a complete temporal-aware RAG system.

## Project Phases

This roadmap is structured around three progressive phases:
1. **MVP Chat Interface**: Building a functional web interface for the existing RAG system
2. **Temporal Intelligence Enhancements**: Enhancing the system with temporal awareness capabilities
3. **Production Deployment and Monitoring**: Scaling and monitoring for production deployment

Each phase delivers tangible user value while building toward the complete temporal intelligence system.

---

## Phase 1: MVP Chat Interface

**Goal**: Create a functional web interface that allows students to interact with UIT documents through a chat interface

**Requirements Addressed**:
- REQ-01: Web-based chat interface (React/Next.js)
- REQ-02: API integration layer for LangGraph retrieval
- REQ-03: Basic authentication (student ID validation)
- REQ-04: Error handling and fallbacks
- REQ-05: Responsive design for mobile devices

### Success Criteria

1. **Student can ask questions** through web interface and receive formatted answers with source citations
2. **Interface responds** within 5 seconds for 95% of queries
3. **Sources are clickable** - student can access original document PDFs for 90% of references
4. **Mobile responsive** - fully functional on phone screens without horizontal scrolling
5. **Error handled gracefully** - "I'm sorry, I don't have information about this topic" when no documents match

### Implementation Milestones

1. **Frontend Development** (Week 1)
   - React/Next.js setup with chat interface components
   - Basic styling with Tailwind CSS
   - Mobile-responsive design implementation

2. **API Integration** (Week 1.5)
   - LangGraph API client implementation
   - Query streaming support
   - Error boundary components

3. **UI Polish & Authentication** (Week 2)
   - Login with student ID implementation
   - Rate limiting implementation
   - Mobile optimization and performance monitoring

### Effort Estimation
- **Development**: 2-3 weeks
- **Complexity**: Medium
- **Team Size**: 1 developer

---

## Phase 2: Temporal Intelligence Enhancements

**Goal**: Enhance the system with temporal awareness capabilities to handle document versions, amendments, and expiration

**Requirements Addressed**:
- REQ-06: Amendment chain awareness ("Document 108 amends 141")
- REQ-07: Expiration handling (return 2024 quy chế, not expired 2020 version)
- REQ-08: Historical query capability (show "what was valid in 2023?")
- REQ-09: Cohort-based filtering ("which documents apply to 2025 cohort?")
- REQ-10: Confidence displays in responses

### Success Criteria

1. **Amendment accurate**: System correctly returns the 2024 version when asked about documents with amendments
2. **Expiration handled**: System correctly handles document expiration and replacement
3. **Cohort targeting**: System can filter information by student cohort
4. **Historical awareness**: System can answer "what was valid in 2022?" type questions
5. **Confidence transparent**: System explains uncertainty when ambiguity exists

### Implementation Milestones

1. **Temporal Metadata Integration** (Week 1)
   - Integrate metadata_rag_subgraph (92% confidence system)
   - PostgreSQL metadata queries implementation
   - Temporal re-ranking (30% weight)

2. **Query Enhancement** (Week 1.5)
   - Agent 3 upgrade for temporal context
   - Context-aware prompts with date filters
   - Historical scope parameters

3. **Integration Testing** (Week 2)
   - Test 50+ temporal scenarios
   - Amendment chain validation
   - Expiration boundary testing

### Effort Estimation
- **Development**: 2-3 weeks
- **Complexity**: High
- **Team Size**: 1 developer

---

## Phase 3: Production Deployment and Monitoring

**Goal**: Deploy a scalable, monitored production system serving 10,000+ monthly users with performance insights and A/B testing capability

**Requirements Addressed**:
- REQ-11: Scalable container deployment
- REQ-12: Analytics dashboard for usage monitoring
- REQ-13: A/B testing system for prompt/extraction improvements
- REQ-14: Performance monitoring (P95 latency < 3s)
- REQ-15: Automated archival of expired documents
- REQ-16: Error tracking and alerting

### Success Criteria

1. **System scales smoothly** - handles 100 concurrent users without degradation
2. **Performance visible** - dashboard shows 95% queries answered in < 3 seconds
3. **Error rate low** - < 1% user-visible errors, automatically tracked
4. **Document freshness maintained** - expired docs archived within 24h of expiration
5. **A/B testing active** - can deploy new extraction models without downtime
6. **Monitoring complete** - alerts trigger within 5 minutes of system issues

### Implementation Milestones

1. **Container Optimization** (Week 1)
   - Multi-instance LangGraph deployment
   - Redis caching layer
   - Load balancer configuration

2. **Analytics & Monitoring** (Week 1.5)
   - Prometheus/Grafana setup
   - Custom metrics dashboard
   - P95 latency alerts

3. **Production Hardening** (Week 2)
   - SSL/HTTPS setup
   - Rate limiting refinement
   - Backup strategy
   - Disaster recovery testing

### Effort Estimation
- **Development**: 2-3 weeks
- **Complexity**: Medium
- **Team Size**: 1 developer

---

## Requirements Coverage

This roadmap ensures 100% requirement coverage with no orphaned requirements:

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-01 | Phase 1 | Web-based chat interface |
| REQ-02 | Phase 1 | API integration layer |
| REQ-03 | Phase 1 | Basic authentication |
| REQ-04 | Phase 1 | Error handling |
| REQ-05 | Phase 1 | Responsive design |
| REQ-06 | Phase 2 | Amendment chain awareness |
| REQ-07 | Phase 2 | Expiration handling |
| REQ-08 | Phase 2 | Historical query capability |
| REQ-09 | Phase 2 | Cohort-based filtering |
| REQ-10 | Phase 2 | Confidence displays |
| REQ-11 | Phase 3 | Scalable deployment |
| REQ-12 | Phase 3 | Analytics dashboard |
| REQ-13 | Phase 3 | A/B testing system |
| REQ-14 | Phase 3 | Performance monitoring |
| REQ-15 | Phase 3 | Automated archival |
| REQ-16 | Phase 3 | Error tracking |

The roadmap ensures all requirements are mapped to exactly one phase, following the principle of requirement coverage validation.