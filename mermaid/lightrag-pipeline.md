# LightRAG Pipeline - Luồng Xử Lý Dữ Liệu

## Sơ Đồ Pipeline Stages

```mermaid
flowchart LR
    subgraph Input_Layer["Lớp Đầu Vào"]
        Input[Chèn Văn Bản<br/>phương thức ainsert]
        Upload[Tải File Lên<br/>document_routes.py]
    end
    
    subgraph Processing_Pipeline["Luồng Xử Lý"]
        Chunk[Chia Khối<br/>chunking_by_token_size<br/>operate.py:66-118]
        Extract[Trích Xuất Thực Thể<br/>extract_entities<br/>operate.py:1082+]
        Merge[Gộp Nút và Cạnh<br/>merge_nodes_and_edges<br/>operate.py]
        Update[Cập Nhật Cache<br/>update_chunk_cache_list<br/>utils.py]
    end
    
    subgraph Storage_Persistence["Lưu Trữ Bền Vững"]
        S1[text_chunks<br/>BaseKVStorage]
        S2[full_docs<br/>BaseKVStorage]
        S3[entities_vdb<br/>BaseVectorStorage]
        S4[relationships_vdb<br/>BaseVectorStorage]
        S5[chunk_entity_relation_graph<br/>BaseGraphStorage]
        S6[llm_response_cache<br/>BaseKVStorage]
        S7[doc_status<br/>DocStatusStorage]
    end
    
    Input --> Chunk
    Upload --> S2
    Upload --> S7
    
    Chunk --> S1
    Chunk --> Extract
    Extract --> Update
    Extract --> Merge
    
    Merge --> S3
    Merge --> S4
    Merge --> S5
    Merge --> S6
    
    style Input fill:#fff,stroke:#333,stroke-width:2px
    style Upload fill:#fff,stroke:#333,stroke-width:2px
    style Chunk fill:#fff,stroke:#333,stroke-width:2px
    style Extract fill:#fff,stroke:#333,stroke-width:2px
    style Merge fill:#fff,stroke:#333,stroke-width:2px
    style Update fill:#fff,stroke:#333,stroke-width:2px
    style S1 fill:#fff,stroke:#333,stroke-width:2px
    style S2 fill:#fff,stroke:#333,stroke-width:2px
    style S3 fill:#fff,stroke:#333,stroke-width:2px
    style S4 fill:#fff,stroke:#333,stroke-width:2px
    style S5 fill:#fff,stroke:#333,stroke-width:2px
    style S6 fill:#fff,stroke:#333,stroke-width:2px
    style S7 fill:#fff,stroke:#333,stroke-width:2px
    style Input_Layer fill:#fff,stroke:#333,stroke-width:1px
    style Processing_Pipeline fill:#fff,stroke:#333,stroke-width:1px
    style Storage_Persistence fill:#fff,stroke:#333,stroke-width:1px
```

## Chi Tiết Từng Giai Đoạn

### 1. Chunking
**Hàm:** `chunking_by_token_size`

**Chức năng:** 
- Chia tài liệu thành các chunks nhỏ có độ dài chồng lấp
- Mặc định: 1200 tokens, overlap 100 tokens
- Đảm bảo ngữ cảnh liên tục giữa các chunks

### 2. Entity Extraction
**Hàm:** `extract_entities`

**Chức năng:**
- Sử dụng LLM để trích xuất entities và relationships từ mỗi chunk
- Hỗ trợ gleaning iterations (lặp lại để cải thiện độ chính xác)
- Tạo ra graph structure từ text

### 3. Merging
**Hàm:** `merge_nodes_and_edges`

**Chức năng:**
- Gộp entities/relationships từ nhiều chunks
- Áp dụng map-reduce summarization khi cần
- Loại bỏ trùng lặp và normalize dữ liệu

### 4. Persistence
**Storage Instances:**

Lưu trữ dữ liệu đã xử lý qua 7 storage instances được quản lý bởi class `LightRAG`:

1. **full_docs** - Key-Value storage cho tài liệu gốc
2. **text_chunks** - Key-Value storage cho các chunks
3. **llm_response_cache** - Cache responses từ LLM
4. **chunk_entity_relation_graph** - Graph storage cho entities/relations
5. **entities_vdb** - Vector DB cho entity embeddings
6. **relationships_vdb** - Vector DB cho relationship embeddings  
7. **chunks_vdb** - Vector DB cho chunk embeddings

### 5. Query Modes

**4 chế độ truy vấn:**

1. **naive**: Truy vấn đơn giản trực tiếp
2. **local**: Tìm kiếm local context xung quanh entities
3. **global**: Tìm kiếm toàn cục trong graph
4. **hybrid**: Kết hợp local + global search

---

## Sơ Đồ Chi Tiết Storage Layer

```mermaid
graph TB
    subgraph Documents["Input Layer"]
        Doc1[Document 1]
        Doc2[Document 2]
        Doc3[Document N]
    end
    
    subgraph Processing["Processing Layer"]
        P1[Chunking]
        P2[Extraction]
        P3[Merging]
    end
    
    subgraph Storage["Storage Layer - 7 Instances"]
        S1[full_docs<br/>KV Store]
        S2[text_chunks<br/>KV Store]
        S3[llm_cache<br/>KV Store]
        S4[entity_graph<br/>Graph DB]
        S5[entities_vdb<br/>Vector DB]
        S6[relations_vdb<br/>Vector DB]
        S7[chunks_vdb<br/>Vector DB]
    end
    
    subgraph Query["Query Layer"]
        Q1[naive]
        Q2[local]
        Q3[global]
        Q4[hybrid]
    end
    
    Documents --> Processing
    Processing --> Storage
    Storage --> Query
    
    style Documents fill:#fff,stroke:#333,stroke-width:2px
    style Processing fill:#fff,stroke:#333,stroke-width:2px
    style Storage fill:#fff,stroke:#333,stroke-width:3px
    style Query fill:#fff,stroke:#333,stroke-width:2px
```

---

## Luồng Dữ Liệu Chi Tiết

```mermaid
sequenceDiagram
    participant User as Người Dùng
    participant API as API Server
    participant Core as Core Engine
    participant LLM as LLM Service
    participant Storage as Storage Layer
    
    User->>API: Upload Document
    API->>Core: Process Document
    
    Core->>Core: Chunking (1200 tokens)
    Core->>LLM: Extract Entities
    LLM-->>Core: Entities + Relations
    Core->>Core: Merge & Deduplicate
    Core->>Storage: Save to 7 Storages
    Storage-->>Core: Confirm Saved
    Core-->>API: Processing Complete
    API-->>User: Success Response
    
    User->>API: Query Request
    API->>Core: Execute Query (mode: hybrid)
    Core->>Storage: Retrieve from Vector DB
    Core->>Storage: Retrieve from Graph DB
    Core->>LLM: Generate Answer
    LLM-->>Core: Final Answer
    Core-->>API: Query Result
    API-->>User: Return Answer
```

---

## So Sánh Query Modes

| Mode | Tốc Độ | Độ Chính Xác | Use Case |
|------|--------|--------------|----------|
| **naive** | ⚡⚡⚡ Rất nhanh | ⭐⭐ Trung bình | Truy vấn đơn giản, keyword search |
| **local** | ⚡⚡ Nhanh | ⭐⭐⭐ Tốt | Tìm kiếm trong ngữ cảnh local |
| **global** | ⚡ Chậm | ⭐⭐⭐⭐ Rất tốt | Phân tích toàn cục, tổng hợp |
| **hybrid** | ⚡⚡ Nhanh | ⭐⭐⭐⭐⭐ Xuất sắc | Kết hợp ưu điểm cả hai |

---

## Ưu Điểm Pipeline

✅ **Chunking thông minh**: Overlap tokens giữ ngữ cảnh

✅ **Entity-centric**: Tập trung vào entities và relationships

✅ **Multi-storage**: Tối ưu cho từng loại dữ liệu

✅ **Flexible queries**: 4 modes phù hợp mọi use case

✅ **Caching**: LLM response cache tăng tốc độ

✅ **Scalable**: Xử lý được lượng lớn documents
