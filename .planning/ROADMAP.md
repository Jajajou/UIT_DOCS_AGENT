## ROADMAP CREATED

**Files written:**
- .planning/ROADMAP.md
- .planning/STATE.md

**Updated:**
- .planning/REQUIREMENTS.md (traceability section)

### Summary

**Phases:** 3
**Granularity:** Standard
**Coverage:** 16/16 requirements mapped ✓

| Phase | Goal | Requirements | Status |
|-------|------|--------------|--------|
| 1 - MVP Chat Interface | Students can interact with UIT documents through a simple web interface | FR-01, FR-02, FR-03, FR-04 | Pending |
| 2 - Temporal Intelligence | Enhanced temporal awareness for document versions, amendments, and expiration | FR-05, FR-06, FR-07, FR-08, FR-09, FR-10 | Planned |
| 3 - Production Monitoring | Scalable deployment with analytics and monitoring | PR-01, PR-02, PR-04, PR-05 | Pending |

### Success Criteria Preview

**Phase 1: MVP Chat Interface**
1. Student can ask questions through web interface and receive formatted answers with source citations
2. Interface responds within 5 seconds for 95% of queries
3. Sources are clickable - student can access original document PDFs for 90% of references
4. Mobile responsive - fully functional on phone screens without horizontal scrolling
5. Error handled gracefully - "I'm sorry, I don't have information about this topic" when no documents match

**Phase 2: Temporal Intelligence**
1. Amendment accurate - when asked about "Thông tư 12/2024" which replaced an older version, returns the 2024 version correctly
2. Expiration handled - "Quy chế đào tạo 2020-2021" returns "Đã thay thế bởi quy chế 2024-2025"
3. Cohort targeting - "Điều kiện tốt nghiệp cho khóa 2021-2025" returns correct requirements for that cohort
4. Historical awareness - "Quy định tốt nghiệp vào năm 2022?" accurately reflects 2022 regulations
5. Confidence transparent - when ambiguity exists, system explains: "Dưới 80% chắc chắn - có thể liên quan đến QĐ 108/2024 nữa"

**Phase 3: Production Deployment and Monitoring**
1. System scales smoothly - handles 100 concurrent users without degradation
2. Performance visible - dashboard shows 95% queries answered in < 3 seconds
3. Error rate low - < 1% user-visible errors, automatically tracked
4. Document freshness maintained - expired docs archived within 24h of expiration
5. A/B testing active - can deploy new extraction models without downtime
6. Monitoring complete - alerts trigger within 5 minutes of system issues

### Phase 2: Temporal Intelligence
**Goal:** Enhanced temporal awareness for document versions, amendments, and expiration.
**Plans:** 3 plans

Plans:
- [ ] 02-01-PLAN.md — Setup environment, implement ping_service.py for automated archival, and test foundation.
- [ ] 02-02-PLAN.md — Enhance Vietnamese temporal extraction with dateparser/underthesea and implement bidirectional amendment linking.
- [ ] 02-03-PLAN.md — Refine temporal RAG reranking, cohort routing, and confidence transparency in responses.

### Files Ready for Review

User can review actual files in the editor or via SDK queries.
