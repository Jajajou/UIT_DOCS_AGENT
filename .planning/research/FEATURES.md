# Feature Landscape
**Domain:** Vietnamese University Chatbot
**Researched:** 2026-04-29

## Table Stakes

Features users expect. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Vietnamese query understanding | Core requirement | Low | Basic NLP in Vietnamese |
| Document amendment tracking | Academic policies change | High | Critical temporal awareness |
| Cohort-based routing | Students expect policy versioning | High | Required for academic accuracy |
| Historical query support | Legal compliance | Medium | Students may ask about old policies |
| Document version comparison | Academic policy changes | High | Version comparison tools |

## Differentiators

Features that set product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Temporal policy routing | Accurate policy versioning | High | Routes to correct academic year policies |
| Amendment document linking | Cross-references updated policies | High | Links amendments to superseded documents |
| Soft delete handling | Historical document access | Medium | Access to expired documents when needed |
| Confidence scoring | Response quality | Low | Reranking based on document relevance |
| Cohort context awareness | Student-specific routing | High | Routes based on student year |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| English-only processing | Vietnamese universities need Vietnamese | Full Vietnamese support required |
| Real-time amendment processing | Computationally expensive | Batch process amendments |
| Full document versioning | Storage intensive | Metadata-based versioning only |
| Complex permission systems | Not needed for academic documents | Simple role-based access |

Feature Dependencies

Feature A → Feature B (B requires A)
Document amendment tracking → Amendment document linking
Cohort context awareness → Cohort-based routing
Temporal policy routing → Document amendment tracking

## MVP Recommendation

Prioritize:
1. Vietnamese query understanding
2. Document amendment tracking
3. Temporal policy routing

Defer: Document version comparison: requires complex UI to show change history

## Sources

- Internal project evaluation
- Vietnamese university policy analysis