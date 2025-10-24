# Kiến Trúc LightRAG - Phiên Bản Đơn Giản

## Sơ Đồ Luồng Đơn Giản

```mermaid
flowchart TD
    Start([Người Dùng]) --> |Gửi Request| API[API Server<br/>FastAPI]
    
    API --> Route{Loại Request?}
    
    Route --> |Upload/Delete| Doc[Xử Lý Tài Liệu<br/>document_routes]
    Route --> |Truy Vấn| Query[Thực Thi Truy Vấn<br/>query_routes]
    Route --> |Lấy Graph| Graph[Truy Xuất Đồ Thị<br/>graph_routes]
    
    Doc --> Core[Core LightRAG<br/>operate.py]
    Query --> Core
    Graph --> Core
    
    Core --> |Cần xử lý text| LLM[LLM Models<br/>OpenAI/Ollama]
    Core --> |Lưu/Đọc Vector| Vector[(Vector Storage<br/>Milvus/Nano)]
    Core --> |Lưu/Đọc Graph| GraphDB[(Graph Storage<br/>Neo4j/NetworkX)]
    Core --> |Lưu/Đọc Data| KV[(Key-Value Storage<br/>JSON)]
    
    LLM --> |Kết quả| Result[Kết Quả]
    Vector --> |Kết quả| Result
    GraphDB --> |Kết quả| Result
    KV --> |Kết quả| Result
    
    Result --> API
    API --> |Trả Response| End([Người Dùng])
    
    style Start fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style End fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style API fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style Route fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style Core fill:#fff,stroke:#333,stroke-width:3px,color:#000
    style LLM fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style Vector fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style GraphDB fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style KV fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style Result fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style Doc fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style Query fill:#fff,stroke:#333,stroke-width:2px,color:#000
    style Graph fill:#fff,stroke:#333,stroke-width:2px,color:#000
```

## Giải Thích Luồng Xử Lý

### Bước 1: Nhận Request
- Người dùng gửi request đến **API Server** (FastAPI)

### Bước 2: Phân Loại Request
API Server phân loại request thành 3 loại:
1. **Upload/Delete Tài Liệu** → `document_routes.py`
2. **Truy Vấn Dữ Liệu** → `query_routes.py`
3. **Lấy Thông Tin Graph** → `graph_routes.py`

### Bước 3: Xử Lý Core
Tất cả requests đều đi qua **Core LightRAG** (`operate.py`) để:
- Chia nhỏ văn bản (chunking)
- Trích xuất entities và relationships
- Tạo embeddings
- Thực hiện truy vấn

### Bước 4: Tương Tác Storage
Core sử dụng 3 loại storage:
- **Vector Storage**: Lưu embeddings (Milvus/NanoVectorDB)
- **Graph Storage**: Lưu đồ thị tri thức (Neo4j/NetworkX)
- **Key-Value Storage**: Lưu metadata (JSON)

### Bước 5: Gọi LLM
Khi cần xử lý ngôn ngữ tự nhiên, Core gọi:
- OpenAI GPT models
- Ollama (local models)
- Azure OpenAI
- Bedrock, HuggingFace

### Bước 6: Trả Kết Quả
- Kết quả từ các storage và LLM được tổng hợp
- API Server trả response cho người dùng

---

## Sơ Đồ Thành Phần Chi Tiết

```mermaid
graph LR
    subgraph Client["Ứng Dụng Client"]
        A1[Python App]
        A2[Web UI]
        A3[Chatbot]
    end
    
    subgraph Server["API Server"]
        B1[FastAPI Server]
    end
    
    subgraph Routes["API Routes"]
        C1[Documents]
        C2[Queries]
        C3[Graph]
        C4[Ollama API]
    end
    
    subgraph Core["Core Engine"]
        D1[LightRAG Core<br/>operate.py]
    end
    
    subgraph AI["AI Services"]
        E1[LLM Models]
        E2[Embeddings]
    end
    
    subgraph Storage["Storage Layer"]
        F1[Vectors]
        F2[Graphs]
        F3[Key-Value]
    end
    
    Client --> Server
    Server --> Routes
    Routes --> Core
    Core --> AI
    Core --> Storage
    
    style Client fill:#fff,stroke:#333,stroke-width:2px
    style Server fill:#fff,stroke:#333,stroke-width:2px
    style Routes fill:#fff,stroke:#333,stroke-width:2px
    style Core fill:#fff,stroke:#333,stroke-width:2px
    style AI fill:#fff,stroke:#333,stroke-width:2px
    style Storage fill:#fff,stroke:#333,stroke-width:2px
```

---

## So Sánh Storage Implementations

```mermaid
graph TD
    subgraph VectorDB["Vector Database"]
        V1[NanoVectorDB<br/>Nhỏ gọn, nhanh<br/>Lưu local]
        V2[Milvus<br/>Quy mô lớn<br/>Phân tán]
    end
    
    subgraph GraphDB["Graph Database"]
        G1[NetworkX<br/>Trong bộ nhớ<br/>Phân tích]
        G2[Neo4j<br/>Production ready<br/>Cypher query]
    end
    
    subgraph KVDB["Key-Value Store"]
        K1[JSON Storage<br/>File-based<br/>Dễ debug]
    end
    
    Core[Core LightRAG] --> VectorDB
    Core --> GraphDB
    Core --> KVDB
    
    style V1 fill:#fff,stroke:#333,stroke-width:2px
    style V2 fill:#fff,stroke:#333,stroke-width:2px
    style G1 fill:#fff,stroke:#333,stroke-width:2px
    style G2 fill:#fff,stroke:#333,stroke-width:2px
    style K1 fill:#fff,stroke:#333,stroke-width:2px
    style Core fill:#fff,stroke:#333,stroke-width:2px
```

---

## Ưu Điểm Kiến Trúc

✅ **Module hóa cao**: Dễ bảo trì và mở rộng

✅ **Abstraction tốt**: Dễ thay đổi implementation

✅ **Async/Await**: Xử lý đồng thời hiệu quả

✅ **Multi-storage**: Tối ưu cho từng loại dữ liệu

✅ **LLM agnostic**: Hỗ trợ nhiều nhà cung cấp

✅ **Graph + Vector**: Kết hợp sức mạnh cả hai
