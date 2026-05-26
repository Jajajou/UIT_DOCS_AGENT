# LangGraph API Documentation for HL

This document provides technical details for interacting with the LangGraph services of the UIT Docs Agent.

## Base URL

- **Internal:** `http://localhost:2024`
- **Tailscale (Public Funnel):** `https://jajajou-bro.tail402a6.ts.net`

## Assistants

| Name | Graph ID | Assistant ID | Description |
|------|----------|--------------|-------------|
| **RetrievalGraph** | `retrieval` | `5bbc8364-e383-5087-8a2f-b6d27677f7a1` | Temporal-aware RAG for querying UIT docs. |
| **IndexGraph** | `index` | `7574d698-9ca8-5f8c-b908-365f58787a06` | Document indexing and metadata extraction. |

---

## 1. Querying (RetrievalGraph)

Used to ask questions about UIT documents.

### Endpoint
`POST /runs/wait`

### Request Body
```json
{
  "assistant_id": "5bbc8364-e383-5087-8a2f-b6d27677f7a1",
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "Your question here"
      }
    ]
  },
  "config": {
    "configurable": {
      "thread_id": "unique-session-id"
    }
  }
}
```

### Response Highlights
- `final_answer`: The primary response string (Vietnamese).
- `logs`: Execution steps (Retrieved entities, Reranking, etc.).
- `retrieved_chunks`: Source document fragments used for the answer.
- `query_confidence`: Score indicating query clarity.

---

## 2. Indexing (IndexGraph)

Used to upload and index new documents.

### Endpoint
`POST /runs/wait`

### Request Body (File Upload)
Supports absolute paths on the server.

```json
{
  "assistant_id": "7574d698-9ca8-5f8c-b908-365f58787a06",
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "upload /path/to/your/document.pdf"
      }
    ]
  },
  "config": {
    "configurable": {
      "thread_id": "indexing-session-id"
    }
  }
}
```

### Request Body (Scan Command)
Triggers a scan of the input directory for new files.

```json
{
  "assistant_id": "7574d698-9ca8-5f8c-b908-365f58787a06",
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "scan"
      }
    ]
  }
}
```

### Human-in-the-Loop (HITL) Workflow

The `IndexGraph` includes a mandatory human review step for temporal metadata during file uploads. This ensures 100% accuracy for policy-critical dates and document links.

#### 1. Metadata Schema Reference
The system extracts the following 7 fields, all of which are editable during review:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `document_number` | `string` | Official ID | `"108/QĐ-ĐHCNTT"` |
| `document_type` | `string` | Classification | `"Quyết định"`, `"Thông báo"` |
| `issuing_authority`| `string` | Who signed it | `"Hiệu trưởng"`, `"Phòng Đào tạo"` |
| `valid_from` | `string` | Effective date | `"2024-09-01"` |
| `valid_until` | `string` | Expiration date | `null` |
| `cohort_years` | `list` | Target student groups | `[2024, 2025]` or `["*"]` |
| `amends_documents` | `list` | Previous docs replaced | `["141/QĐ-ĐHCNTT"]` |

> **Note on Dates:** The backend accepts `DD/MM/YYYY`, `DD-MM-YYYY`, and `YYYY-MM-DD`. It will automatically normalize everything to `YYYY-MM-DD` for the database.

#### 2. The Interrupt
When you trigger an `upload`, the run will pause and return an `interrupt` state containing the current auto-extracted metadata.

**Response from /runs/wait (Example):**
```json
{
  "__interrupt__": [
    {
      "value": {
        "action": "review_temporal_tags",
        "metadata": {
          "document_number": "108/QĐ-ĐHCNTT",
          "document_type": "Quyết định",
          "issuing_authority": "Hiệu trưởng",
          "valid_from": "2024-09-01",
          "valid_until": null,
          "cohort_years": [2024],
          "amends_documents": ["141/QĐ-ĐHCNTT"]
        },
        "human_feedback": null,
        "loop_count": 0
      },
      "id": "interrupt_id_uuid"
    }
  ]
}
```

#### 3. How to Respond (Resume Payloads)
To continue indexing, you must send a `MetadataReviewAction` payload to the resume endpoint.

**Endpoint:** `POST /runs/{run_id}/resume`

**Action A: Approve As-Is**
Use this if the AI extracted everything perfectly.
```json
{
  "action": "approved"
}
```

**Action B: Edit & Approve (Manual Override)**
Use this to fix specific fields. Any field you include in the payload will **overwrite** the AI's extraction.
```json
{
  "action": "approved",
  "document_number": "Correct-Number-123",
  "valid_from": "10/02/2026",
  "cohort_years": [2024, 2025, 2026]
}
```

**Action C: Reject with Feedback (The 1-Retry Loop)**
If the extraction is completely wrong, you can provide notes. The system will jump back, run the LLM again with your notes injected into the prompt, and pause for a second review. 
*Note: Only 1 retry is allowed to prevent infinite loops.*
```json
{
  "action": "rejected",
  "feedback": "The year is actually 2026, look at the signature on page 2."
}
```

#### 4. Post-Approval Behavior
Once "approved" is received:
1. The metadata is validated against the Pydantic schema.
2. The graph resumes to `upload_to_lightrag`.
3. The verified metadata is saved to the `temporal_metadata` table.
4. If `amends_documents` contains doc numbers, the system automatically creates "amends" edges in the Knowledge Graph.

---

## 3. Useful Endpoints

- **Assistant Search:** `POST /assistants/search` (Body: `{}`)
- **Thread History:** `GET /threads/{thread_id}/history`
- **Service Info:** `GET /info`
- **Health Check:** `GET /ok`

## Known Issues & Fixes

### 2026-05-26: HITL interrupt showed `metadata: {}` (empty)

**Root cause:** `MetadataRAGState` (subgraph state) was missing the `document_metadata` field declaration. LangGraph subgraph-as-node merges output to parent via shared key names — undeclared keys are silently dropped. So `format_metadata_node` returned `document_metadata` but it never surfaced to the parent `review_temporal_tags_node`.

**Fix:** Added `document_metadata: NotRequired[Dict[str, Any]]` to `MetadataRAGState`.

**Result:** `interrupt` payload now correctly shows the extracted metadata under `metadata`.

---

## Validation Status
- **Retrieval:** VERIFIED with query "What is the UIT Docs Agent?".
- **Indexing:** VERIFIED with file "missingdoc.md".
- **HITL metadata population:** FIXED 2026-05-26 — interrupt now shows extracted fields.
