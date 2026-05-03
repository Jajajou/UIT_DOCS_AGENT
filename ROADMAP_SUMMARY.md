## ROADMAP DRAFT

**Phases:** 3
**Granularity:** Standard
**Coverage:** 16/16 requirements mapped

### Phase Structure

| Phase | Goal | Requirements | Success Criteria |
|-------|------|--------------|------------------|
| 1 - MVP Chat Interface | Students can interact with UIT documents through a simple web interface | REQ-01, REQ-02, REQ-03, REQ-04, REQ-05 | 5 criteria |
| 2 - Temporal Intelligence Enhancements | Accurate handling of document versions, amendments, and expiration | REQ-06, REQ-07, REQ-08, REQ-09, REQ-10 | 5 criteria |
| 3 - Production Deployment and Monitoring | Scalable, monitored production system serving 10,000+ monthly users | REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16 | 6 criteria |

### Success Criteria Preview

**Phase 1: MVP Chat Interface**
1. Student can ask questions through web interface and receive formatted answers with source citations
2. Interface responds within 5 seconds for 95% of queries
3. Sources are clickable - student can access original document PDFs for 90% of references
4. Mobile responsive - fully functional on phone screens without horizontal scrolling
5. Error handled gracefully - "I'm sorry, I don't have information about this topic" when no documents match

**Phase 2: Temporal Intelligence Enhancements**
1. Amendment accurate: When asked about "Document 108" which replaced an older version, returns the correct version
2. Expiration handled: "Quy chế đào tạo 2020-2021" returns "Đã thay thế bởi quy chế 2024-2025"
3. Cohort targeting: "Điều kiện tốt nghiệp cho khóa 2021-2025" returns correct requirements for that cohort
4. Historical awareness: "Quy định tốt nghiệp vào năm 2022?" accurately reflects 2022 regulations
5. Confidence transparent: When ambiguity exists, system explains uncertainty to user

**Phase 3: Production Deployment and Monitoring**
1. System scales smoothly - handles 100 concurrent users without degradation
2. Performance visible - dashboard shows 95% queries answered in < 3 seconds
3. Error rate low - < 1% user-visible errors, automatically tracked
4. Document freshness maintained - expired docs archived within 24h of expiration
5. A/B testing active - can deploy new extraction models without downtime
6. Monitoring complete - alerts trigger within 5 minutes of system issues

### Coverage

✓ All 16 requirements mapped
✓ No orphaned requirements

### Awaiting

Approve roadmap or provide feedback for revision.