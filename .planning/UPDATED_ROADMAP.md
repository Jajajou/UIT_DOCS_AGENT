# UIT Student Chatbot Thesis - Implementation Roadmap

This roadmap transforms the existing UIT Documents Agent into a production-ready student chatbot system through three strategic phases, each delivering proven user value while building toward the complete temporal intelligence system.

## Project Phases

| Phase | Duration | Core Deliverable | User Impact | Effort |
|---|---|---|---|---|
| **Phase 1: MVP Chat Interface** | 2-3 weeks | Working chat interface for basic queries | Students can ask questions about current documents | Medium-High |
| **Phase 2: Temporal Intelligence** | 2-3 weeks | Smart document handling + historical queries | Accurate answers about document versions, amendments, expiration | High |
| **Phase 3: Production Monitoring** | 2-3 weeks | Scalable deployment + analytics dashboard | Students get reliable service with performance insights | Medium |

---

## Phase 1: MVP Chat Interface

**Goal:** Create a functional web interface that allows students to interact with UIT documents through a chat interface

**Requirements Addressed:**
- **FR-01**: Vietnamese-first interface with web chat
- **UR-01**: Vietnamese natual language processing
- **AR-01**: RAG-based retrieval system integration
- **PR-01**: Response latency ≤ 3 seconds achieved

### Success Criteria
1. **Student can ask questions** through web interface and receive formatted Vietnamese answers with source citations
2. **Interface responds** within 3 seconds for 95% of queries
3. **Sources are clickable** - students can access original document PDFs for 90% of references
4. **Mobile responsive** - fully functional on phone screens without horizontal scrolling
5. **Natural Vietnamese conversation** - appropriate tone and vocabulary for students

### Implementation Milestones

**Week 1: Foundation & API Integration**
- **M1.1** (Day 1-2): React/Next.js project scaffold with Vietnamese font support
- **M1.2** (Day 3-4): LangGraph API integration with streaming responses
- **M1.3** (Day 5): FastAPI wrapper for web-safe access

**Week 2: Polish & Testing**
- **M2.1** (Day 6): Mobile responsive optimization
- **M2.2** (Day 7): Error handling & graceful fallbacks
- **M2.3** (Day 8-10): User acceptance testing with 5 students

**Estimated Effort:** 2-3 weeks (8-12 hours total development)
**Complexity:** Medium - leveraging existing LangGraph pipeline

---

## Phase 2: Temporal Intelligence Enhancements

**Goal:** Enhance the system with temporal awareness capabilities to handle document versions, amendments, and expiration - the core innovation of the thesis

**Requirements Addressed:**
- **FR-01**: Amendment chain awareness ("Document 108 amends 141")
- **FR-05**: Validity period tracking with expiration detection
- **FR-06**: Amendment relationship tracking with Vietnamese context
- **FR-07**: Real-time temporal warnings for expired policies
- **FR-08**: High-confidence retrieval (≥ 80% accuracy)

### Success Criteria
1. **Amendment accuracy**: System correctly returns the 2024 version when asked about superseded documents
2. **Expiration handled**: "Quy chế đào tạo 2020-2021" returns "Đã thay thế bởi quy chế 2024-2025"
3. **Cohort targeting**: "Điều kiện tốt nghiệp cho khóa 2021-2025" returns correct requirements
4. **Historical awareness**: "Quy định tốt nghiệp vào năm 2022?" accurately reflects 2022 regulations
5. **Confidence transparent**: System explains uncertainty when ambiguity exists in Vietnamese
6. **Real-time warnings**: Students get alerts about expired policies in natural Vietnamese

### Implementation Milestones

**Week 1: Temporal System Integration**
- **M3.1** (Day 11-12): PostgreSQL metadata queries + temporal scoring integration
- **M3.2** (Day 13): Amendment chain visualization in responses
- **M3.3** (Day 14): Document lifecycle awareness in Agent 3 prompts

**Week 2: Cohort & Historical Processing**
- **M4.1** (Day 15): Cohort year detection from queries using Vietnamese
- **M4.2** (Day 16): Academic calendar integration (2024-2025 structure)
- **M4.3** (Day 17-19): Comprehensive testing on 20 historical document scenarios

**Estimated Effort:** 2-3 weeks (12-15 hours development + testing)
**Complexity:** High - core thesis innovation

---

## Phase 3: Production Deployment and Monitoring

**Goal:** Deploy a scalable, monitored production system serving 10,000+ monthly students with performance insights and A/B testing capability

**Requirements Addressed:**
- **PR-02**: Support 15,000+ concurrent active students
- **PR-04**: 99.9% uptime for student access
- **PR-05**: Horizontal scaling capability
- **AR-02**: Multi-agent processing pipeline
- **AR-03**: Docker containerization with monitoring
- **SR-01, SR-02, SR-03**: Security compliance

### Success Criteria
1. **System scales smoothly** - handles 100 concurrent users without degradation
2. **Performance visible** - dashboard shows 95% queries answered in < 3 seconds
3. **Error rate low** - < 1% user-visible errors, automatically tracked
4. **Document freshness maintained** - expired docs archived within 24h automatically
5. **A/B testing active** - can deploy new extraction models without downtime
6. **Monitoring complete** - alerts trigger within 5 minutes, student-facing dashboard
7. **Security compliant** - GDPR compliance for student data with proper authentication

### Implementation Milestones

**Week 1: Scalability & Security**
- **M5.1** (Day 20-21): Multi-instance LangGraph deployment with load balancing
- **M5.2** (Day 22): JWT authentication + university SSO integration
- **M5.3** (Day 23): Rate limiting (10 req/min per student) + data privacy compliance

**Week 2: Monitoring & Analytics**
- **M6.1** (Day 24-25): Prometheus/Grafana dashboard with student metrics
- **M6.2** (Day 26): A/B testing system for temporal feature improvements
- **M6.3** (Day 27-28): Comprehensive stress testing and disaster recovery

**Estimated Effort:** 2-3 weeks (10-12 hours configuration + testing)
**Complexity:** Medium - infrastructure and configuration focus

---

## Architecture Evolution

**Existing Foundation**: 2-Agent RAG pipeline (HTTP-based)
**Phase 1 Extension**: Web interface layer (FastAPI + React)
**Phase 2 Enhancement**: Temporal metadata queries (PostgreSQL)
**Phase 3 Scaling**: Container orchestration + monitoring

```
Phase 1: [React/Next.js] → [FastAPI] → [LangGraph] → [LightRAG] → [PostgreSQL]
Phase 2: [Enhanced with Temporal Queries + Confidence Scoring]
Phase 3: [Scalable + Monitored + Secured Production System]
```

## Go/No-Go Decision Points

### Phase 1 Launch Gate
- [ ] **Functionality**: 10 key student questions answered correctly
- [ ] **Performance**: All queries < 3 seconds
- [ ] **Accessibility**: Full WCAG 2.1 compliance
- [ ] **Mobile**: Tested on 5 different devices

### Phase 2 Launch Gate
- [ ] **Accuracy**: 85%+ accuracy on amendment chain resolution across 20 test cases
- [ ] **Language**: Perfect Vietnamese accuracy and cultural appropriateness
- [ ] **Historical**: Queries work across 2020-2025 academic years
- [ ] **Cohort**: Multi-cohort testing passed with 90%+ precision

### Phase 3 Launch Gate
- [ ] **Scale**: Handles 1000+ concurrent users without degradation
- [ ] **Uptime**: 99.9% measured over 7 days
- [ ] **Security**: Security scan passed, privacy audit complete
- [ ] **Monitoring**: Full observability with student-friendly metrics

## Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation Strategy |
|---|---|---|---|
| Vietnamese temporal processing accuracy drops | Medium | High | Dedicated Vietnamese temporal test suite (50+ scenarios) |
| University SSO integration complexity | Low | Medium | Start with JWT + upgrade path to full SSO |
| Browser compatibility issues | Low | Medium | Progressive web app approach with fallbacks |
| PostgreSQL query performance under load | Medium | High | Optimized indexes + Redis caching layer |
| OCR failure on complex Vietnamese PDFs | Low | Medium | Machine learning model improvements + manual review queue |

## Total Timeline & Effort

**Phase 1 (MVP Chat Interface)**: 2-3 weeks, 8-12 hours development
**Phase 2 (Temporal Intelligence)**: 2-3 weeks, 12-15 hours development
**Phase 3 (Production Monitoring)**: 2-3 weeks, 10-12 hours configuration

**Total Project Duration**: 6-8 weeks
**Total Development Effort**: 30-39 hours concentrated work
**User Impact**: 500+ active student users by thesis defense

The roadmap leverages the existing 2-agent RAG system foundation while building out the specific features needed for a production student chatbot with advanced temporal intelligence capabilities.