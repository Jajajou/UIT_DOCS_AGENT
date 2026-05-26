## ROADMAP CREATED

**Files written:**
- .planning/ROADMAP.md
- .planning/STATE.md

**Updated:**
- .planning/REQUIREMENTS.md (traceability section)

### Summary

**Phases:** 4
**Granularity:** Standard
**Coverage:** 16/16 requirements mapped + 3 bug fixes

| Phase | Goal | Requirements | Status |
|-------|------|--------------|--------|
| 1 - MVP Chat Interface | Students can interact with UIT documents through a simple web interface | FR-01, FR-02, FR-03, FR-04 | Pending |
| 2 - Temporal Intelligence | Enhanced temporal awareness for document versions, amendments, and expiration | FR-05, FR-06, FR-07, FR-08, FR-09, FR-10 | Planned |
| 3 - Production Monitoring | Scalable deployment with analytics and monitoring | PR-01, PR-02, PR-04, PR-05 | Pending |
| 4 - Sprint A Bug Fixes | Fix citation URL, education_system routing, amendment chain SQL patches | BUG-A1, BUG-A2, BUG-A3 | In Progress |

### Success Criteria Preview

**Phase 1: MVP Chat Interface**
1. Student can ask questions through web interface and receive formatted answers with source citations
2. Interface responds within 5 seconds for 95% of queries
3. Sources are clickable - student can access original document PDFs for 90% of references
4. Mobile responsive - fully functional on phone screens without horizontal scrolling
5. Error handled gracefully - "I'm sorry, I don't have information about this topic" when no documents match

**Phase 2: Temporal Intelligence**
1. Amendment accurate - when asked about "Thong tu 12/2024" which replaced an older version, returns the 2024 version correctly
2. Expiration handled - "Quy che dao tao 2020-2021" returns "Da thay the boi quy che 2024-2025"
3. Cohort targeting - "Dieu kien tot nghiep cho khoa 2021-2025" returns correct requirements for that cohort
4. Historical awareness - "Quy dinh tot nghiep vao nam 2022?" accurately reflects 2022 regulations
5. Confidence transparent - when ambiguity exists, system explains: "Duoi 80% chac chan - co the lien quan den QD 108/2024 nua"

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
- [ ] 02-01-PLAN.md -- Setup environment, implement ping_service.py for automated archival, and test foundation.
- [ ] 02-02-PLAN.md -- Enhance Vietnamese temporal extraction with dateparser/underthesea and implement bidirectional amendment linking.
- [ ] 02-03-PLAN.md -- Refine temporal RAG reranking, cohort routing, and confidence transparency in responses.

### Files Ready for Review

User can review actual files in the editor or via SDK queries.

### Phase 4: Sprint A: System Completeness Bug Fixes -- citation URL, education_system routing, amendment chain SQL patches

**Goal:** Fix 3 concrete correctness bugs that cause wrong/broken responses regardless of retrieval quality. Expected gain: +0.8-1.2pp acc@1 (0.767->~0.776).
**Requirements:** BUG-A1, BUG-A2, BUG-A3
**Depends on:** None (independent bug fixes on existing codebase)
**Plans:** 3 plans

Plans:
- [ ] 04-01-PLAN.md -- Fix citation URLs: resolve file_path to HTTP URLs via get_url()
- [ ] 04-02-PLAN.md -- Patch amendment chain SQL for tu xa Quy che dao tao (790->1393->507)
- [ ] 04-03-PLAN.md -- Add education_system field (chinh_quy/tu_xa/tien_tien/song_nganh) to DB, Qdrant, Agent 1, retrieval filter
