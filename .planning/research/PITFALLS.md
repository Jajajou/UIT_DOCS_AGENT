# Domain Pitfalls
**Domain:** Vietnamese University Chatbot
**Researched:** 2026-04-29

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: Amendment Over-Classification
**What goes wrong:** System classifies amendment documents as standalone policies
**Why it happens:** Vietnamese "quyết định sửa đổi" documents look like regular decisions
**Consequences:** Students receive outdated policies instead of current ones
**Prevention:** Rigorous amendment detection patterns ("sửa đổi", "bổ sung", "thay thế")
**Detection:** Monitor F-scores in evaluation, check amendment misclassifications

### Pitfall 2: Temporal Mood Death
**What goes wrong:** Temporal scoring overstabilizes, penalizing recent documents
**Why it happens:** Administrative bias toward older, established policies
**Consequences:** Students miss current course requirements
**Prevention:** Dynamic temporal weighting based on query context
**Detection:** Test queries about current semester policies

### Pitfall 3: Vietnamese Cohort Context Failure
**What goes wrong:** System fails to identify student graduation years from Vietnamese text
**Why it happens:** Vietnamese ordinal numbers and year expressions are ambiguous
**Consequences:** Unbelievably specific but wrong policy routing
**Prevention:** Use Vietnamese-specific date parsing and cohort inference
**Detection:** Test with Vietnamese phrasing like "sinh viên khóa 2024"

## Moderate Pitfalls

### Pitfall 1: OCR Blocking on Scanned PDFs
**What goes wrong:** Vietnamese OCR fails on scanned university documents
**Prevention:** Retry with DeepSeek-OCR, cached content fallback

### Pitfall 2: Context Window Overflow with Temporal Metadata
**What goes wrong:** Including temporal context exceeds token limits
**Prevention:** Metadata compression, selective context insertion

### Pitfall 3: Redundant Amendment Processing
**What goes wrong:** Processing identical amendments across different documents
**Prevention:** Cache amendment signatures, avoid repeat processing

## Minor Pitfalls

### Pitfall 1: Student Birthday vs Academic Year Confusion
**What goes wrong:** Confusing student birth year with academic enrollment year
**Prevention:** Explicit cohort year extraction, not birth year

### Pitfall 2: Semester vs Calendar Year Routing
**What goes wrong:** Failing to distinguish academic year (2024-2025) from calendar year (2024)
**Prevention:** Strict academic year formatting validation

### Pitfall 3: Document Number Duplication
**What goes wrong:** Multiple documents with same number across different years
**Prevention:** Unique document IDs with year suffix

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| **Amendment detection** | Amendment over-classification | Implement 3-layer validation (LLM + regex + cross-ref) |
| **Vietnamese processing** | Tokenizer failure on academic terms | Use Vietnamese_Embedding_V2, not generic multilingual |
| **Temporal routing** | Cohort context failure | Test Vietnamese year expressions exhaustively |
| **Deployment** | OCR blocking on institutional PDFs | Implement robust content caching and retry logic |

## Sources
- Internal evaluation results showing amendment over-classification
- Vietnamese language processing case studies