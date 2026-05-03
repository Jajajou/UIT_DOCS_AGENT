# UIT Student Chatbot Thesis Implementation Roadmap

**Project**: Advanced Temporal-Aware RAG Chatbot for UIT Documents
**Architecture**: 2-Agent RAG System with Vietnamese Language Support
**Timeline**: 6-8 weeks (adjustable based on complexity)
**User Impact**: ~30,000 UIT students and faculty

---

## 🎯 Executive Summary

This roadmap transforms the existing UIT Documents Agent into a production-ready student chatbot system through three strategic phases. Each phase delivers tangible user value while building toward the complete temporal intelligence system.

| Phase | Duration | Core Deliverable | User Impact |
|---|---|---|---|
| Phase 1: MVP Chat Interface | 2-3 weeks | Working chat interface for basic queries | Students can ask questions about current documents |
| Phase 2: Temporal Enhancements | 2-3 weeks | Smart document handling + historical queries | Accurate answers about document versions, amendments, expiration |
| Phase 3: Production Monitoring | 2-3 weeks | Scalable deployment + analytics dashboard | Students get reliable service with performance insights |

---

## Phase 1: MVP Chat Interface (Foundation)
**Goal**: Students can interact with UIT documents through a simple web interface
**Dependencies**: Existing 2-agent RAG system (v0.2.0)
**Duration**: 2-3 weeks
**Effort**: Medium-High (requires full-stack integration)

### Core Requirements
- REQ-01: Web-based chat interface (React/Next.js)
- REQ-02: API integration layer for LangGraph retrieval
- REQ-03: Basic authentication (student ID validation)
- REQ-04: Error handling and fallbacks
- REQ-05: Responsive design for mobile devices

### Success Criteria (Observable Behaviors)
1. **Student can ask questions** through web interface and receive formatted answers with source citations
2. **Interface responds** within 5 seconds for 95% of queries
3. **Sources are clickable** - student can access original document PDFs for 90% of references
4. **Mobile responsive** - fully functional on phone screens without horizontal scrolling
5. **Error handled gracefully** - "I'm sorry, I don't have information about this topic" when no documents match

### Implementation Milestones
| Week | Milestone | Tasks | Validation |
|---|---|---|---|
| Week 1 | Chat UI Foundation | • React/Next.js setup<br>• Vercel deployment config<br>• Basic chat component<br>• Tailwind styling | UI renders, messages display |
| Week 1.5 | API Integration | • LangGraph API client<br>• Query streaming support<br>• Error boundary components<br>• Loading states | Can query from UI |
| Week 2 | Source References | • PDF viewer integration<br>• Hyperlink generation<br>• Document metadata display<br>• Citation formatting | Links work, references clear |
| Week 2.5 | Polish & Auth | • Login with student ID<br>• Rate limiting<br>• Mobile optimization<br>• Performance monitoring | Mobile responsive, auth working |

### Technical Stack
- **Frontend**: Next.js 14 + TypeScript + Tailwind CSS
- **Backend**: LangGraph API integration (REST + WebSocket)
- **Authentication**: JWT token system with student ID validation
- **Deployment**: Vercel (frontend) + Containerized LangGraph (backend)

### Key Architecture Notes
- Utilize existing query_graph.py as-is
- Wrap with FastAPI or similar for web access layer
- Implement proper rate limiting (10 req/min per student)
- Add caching layer for common questions

---

## Phase 2: Temporal Intelligence Enhancements (Core Innovation)
**Goal**: Accurate handling of document versions, amendments, and expiration
**Dependencies**: MVP chat interface, metadata extraction system
**Duration**: 2-3 weeks
**Effort**: High (core thesis innovation)

### Core Requirements
- REQ-06: Amendment chain awareness ("Document 108 amends 141")
- REQ-07: Expiration handling (return 2024 quy chế, not expired 2020 version)
- REQ-08: Historical query capability (show "what was valid in 2023?")
- REQ-09: Cohort-based filtering ("which documents apply to 2025 cohort?")
- REQ-10: Confidence displays in responses

### Success Criteria (Observable Behaviors)
1. **Amendment accurate**: When asked about "Thông tư 12/2024" which replaced an older version, returns the 2024 version correctly
2. **Expiration handled**: "Quy chế đào tạo 2020-2021" returns "Đã thay thế bởi quy chế 2024-2025"
3. **Cohort targeting**: "Điều kiện tốt nghiệp cho khóa 2021-2025" returns correct requirements for their cohort
4. **Historical awareness**: "Quy định tốt nghiệp vào năm 2022?" accurately reflects 2022 regulations
5. **Confidence transparent**: When ambiguity exists, system explains: "Dưới 80% chắc chắn - có thể liên quan đến QĐ 108/2024 nữa"

### Implementation Milestones
| Week | Milestone | Tasks | Validation |
|---|---|---|---|
| Week 1 | Temporal Metadata Integration | • Integrate metadata_rag_subgraph (92% confidence system)<br>• PostgreSQL metadata queries<br>• Temporal re-ranking (30% weight)<br>• Amendment chain resolution | Test temporal queries working |
| Week 1.5 | Query Enhancement | • Agent 3 upgrade for temporal context<br>• Context-aware prompts with date filters<br>• Historical scope parameters<br>• Amendment chain traversal | Cross-date queries accurate |
| Week 2 | Confidence & Explanation | • Confidence threshold tuning (0.8 for definite)<n• Add explanation layer for ambiguous cases<br>• Visual confidence indicators<br>• Fallback clarification prompts | Low-confidence cases handled |
| Week 2.5 | Integration Testing | • Test 50+ temporal scenarios
• Amendment chain validation
• Expiration boundary testing
• Historical accuracy verification | All scenarios work |

### Key Technical Components
- **Temporal Query Handling**: Extend Agent 1 to detect date references
- **Metadata Enrichment**: Pre-query temporal metadata from PostgreSQL
- **Amendment Logic**: `find_amended_documents()` function with PostgreSQL joins
- **Historical Filters**: Parameter system for "date of validity" queries
- **Confidence System**: Weighted scoring (40% completeness + 40% LLM + 20% chunk quality)

### Testing Strategy
- Create test set of 20 historical documents with amendments
- Validate amendment chain resolution accuracy
- Test expiration boundary conditions
- User acceptance testing with 10 students

---

## Phase 3: Production Deployment & Monitoring (Scale)
**Goal**: Scalable, monitored production system serving 10,000+ monthly users
**Dependencies**: Temporal enhancements + stable MVP
**Duration**: 2-3 weeks
**Effort**: Medium (configuration and optimization)

### Core Requirements
- REQ-11: Scalable container deployment
- REQ-12: Analytics dashboard for usage monitoring
- REQ-13: A/B testing system for prompt/extraction improvements
- REQ-14: Performance monitoring (P95 latency < 3s)
- REQ-15: Automated archival of expired documents
- REQ-16: Error tracking and alerting

### Success Criteria (Observable Behaviors)
1. **System scales smoothly** - handles 100 concurrent users without degradation
2. **Performance visible** - dashboard shows 95% queries answered in < 3 seconds
3. **Error rate low** - < 1% user-visible errors, automatically tracked
4. **Document freshness maintained** - expired docs archived within 24h of expiration
5. **A/B testing active** - can deploy new extraction models without downtime
6. **Monitoring complete** - alerts trigger within 5 minutes of system issues

### Implementation Milestones
| Week | Milestone | Tasks | Validation |
|---|---|---|---|
| Week 1 | Container Optimization | • Multi-instance LangGraph deployment<br>• Redis caching layer<br>• Load balancer configuration<br>• Connection pooling | Load test passes |
| Week 1.5 | Analytics & Monitoring | • Prometheus/Grafana setup<br>• Custom metrics dashboard<br>• P95 latency alerts<br>• Error rate monitoring | Dashboard displays real data |
| Week 2 | A/B Testing System | • Feature toggle system<br>• Prompt variant testing<br>• Statistical significance monitoring<br>• Rollback capability | Can test extraction variants |
| Week 2.5 | Production Hardening | • SSL/HTTPS setup
• Rate limiting refinement
• Backup strategy
• Disaster recovery testing | All systems green |

### Technical Architecture
- **Scaling**: Kubernetes deployment with auto-scaling (2-10 replicas)
- **Caching**: Redis for frequently asked questions
- **Monitoring**: Prometheus metrics, Grafana dashboards
- **Analytics**: Custom telemetry for temporal features usage
- **Backups**: Daily PostgreSQL backups + RAG storage snapshots

### Production Metrics
- **Core KPIs**: Response time, accuracy, user satisfaction
- **Temporal KPIs**: Amendment resolution rate, historical query success rate
- **Infrastructure KPIs**: Latency, error rates, resource utilization

---

## 📊 Platform-Specific Optimizations

### Workflow Automation
```bash
# Development workflow integration
./scripts/dev-start.sh     # Start all services locally
./scripts/deploy-staging.sh  # Deploy to staging environment
./scripts/deploy-prod.sh   # Production deployment with zero-downtime
./scripts/health-check.sh  # Comprehensive system health check
```

### Git Workflows
- **Main branch**: Always stable, production ready
- **Develop branch**: Integration point for features
- **Feature branches**: Each phase milestone
- **Release tags**: V0.3.0 (Phase 1), v0.4.0 (Phase 2), v1.0.0 (Phase 3)

### Thesis Documentation Integration
- **Phase 1 deliverables**: GitHub Pages Jekyll blog post
- **Phase 2 research**: A/B testing results with standardized effect size calculations
- **Phase 3 analysis**: Production usage patterns and temporal feature adoption

---

## 🎯 Risk Management & Mitigation

### Technical Risks
| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Vietnamese OCR accuracy low | Medium | High | Always include DeepSeek-OCR fallback, test on real documents |
| Temporal extraction fails for complex docs | Medium | Medium | Build monitoring for extraction confidence < 0.7 |
| Scalability bottlenecks | Low | High | Load testing with production query patterns |
| Auth system complexity | Low | Medium | Start with simple JWT, upgrade to SSO later |

### User Experience Risks
- **Risk**: Students misuse temporal queries causing confusion
  **Mitigation**: Build contextual help for date-based queries
- **Risk**: Complex amendment chains confusing users
  **Mitigation**: Visual timeline display for amendment relationships

---

## ✅ Go/No-Go Criteria

### Phase 1 Launch
- [ ] Can students successfully ask 100+ common UIT questions?
- [ ] Mobile interface tested on 5 different devices
- [ ] < 5% timeout rate for standard queries

### Phase 2 Launch
- [ ] 85%+ accuracy on amendment chain resolutions
- [ ] Historical queries work for last 4 academic years
- [ ] > 80% user satisfaction on temporal features

### Phase 3 Launch
- [ ] Handles 1000+ concurrent users
- [ ] P95 latency < 3 seconds
- [ ] Error rate < 1%

---

## 🚀 Next Steps

1. **Immediate**: Set up roadmap tracking (create Jira/Linear tickets)
2. **Week 1**: Finalize technical architecture for each phase
3. **Week 2**: Begin Phase 1 development with user testing schedule
4. **Ongoing**: Weekly progress reviews and course corrections

**Total Estimation**: 6-8 weeks for complete thesis-ready system
**Critical Path**: Parallel development of UI and temporal logic possible
**Success Measure**: 500+ active student users by thesis defense

---

*Last Updated: 2026-04-29*
*Owner: Thesis Student*
*Stakeholders: UIT Faculty, Student Body*