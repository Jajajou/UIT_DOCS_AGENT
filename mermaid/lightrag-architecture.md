# Kiến Trúc LightRAG - Hệ Thống RAG Nâng Cao

## Sơ Đồ Kiến Trúc Tổng Quan

```mermaid
graph TB
    subgraph clients["Ứng Dụng Khách Hàng"]
        python["Ứng Dụng Python<br/>(Import LightRAG)"]
        web["Trình Duyệt Web<br/>(React UI)"]
        ai["AI Chatbot<br/>(Ollama API)"]
    end

    subgraph api["Tầng API Server"]
        lightning["lightning_server.py<br/>FastAPI Application"]
    end

    subgraph routes["API Routes"]
        doc["document_routes.py<br/>Upload, Insert, Delete"]
        query["query_routes.py<br/>Query Execution"]
        graph_route["graph_routes.py<br/>Graph Retrieval"]
        ollama["ollama_api.py<br/>Ollama Compatibility"]
    end

    subgraph core["Core Framework<br/>LightRAG class<br/>(lightrag.py)"]
        operate["operate.py<br/>chunking by token size<br/>extract entities<br/>merge nodes and edges<br/>llp_query, naive_query"]
    end

    subgraph llm["Tích Hợp LLM"]
        llm_model["llm_model_func:<br/>priority_limit_async_func_call"]
        embed["embedding_func:<br/>EmbeddingFunc.wrapper"]
    end

    subgraph llm_providers["Nhà Cung Cấp LLM"]
        openai_llm["OpenAI, Ollama, Azure,<br/>Bedrock, HuggingFace"]
    end

    subgraph storage["Trừu Tượng Hóa Storage"]
        base_kv["BaseKVStorage<br/>(base.py)"]
        base_vector["BaseVectorStorage<br/>(base.py)"]
        base_graph["BaseGraphStorage<br/>(base.py)"]
        doc_status["DocStatusStorage<br/>(base.py)"]
    end

    subgraph implementations["Triển Khai Storage"]
        json_impl["JsonKVStorage"]
        nano_impl["NanoVectorDBStorage"]
        milvus_impl["MilvusVectorDBStorage"]
        networkx_impl["NetworkXStorage"]
        neo4j_impl["Neo4jStorage"]
    end

    python --> lightning
    web --> lightning
    ai --> lightning
    
    lightning --> doc
    lightning --> query
    lightning --> graph_route
    lightning --> ollama
    
    doc --> operate
    query --> operate
    graph_route --> operate
    ollama --> operate
    
    operate --> llm_model
    operate --> embed
    operate --> base_kv
    operate --> base_vector
    operate --> base_graph
    
    llm_model --> openai_llm
    embed --> openai_llm
    
    base_kv --> json_impl
    base_vector --> nano_impl
    base_vector --> milvus_impl
    base_graph --> networkx_impl
    base_graph --> neo4j_impl

    style clients fill:#fff,stroke:#333,stroke-width:2px
    style api fill:#fff,stroke:#333,stroke-width:2px
    style routes fill:#fff,stroke:#333,stroke-width:2px
    style core fill:#fff,stroke:#333,stroke-width:2px
    style llm fill:#fff,stroke:#333,stroke-width:2px
    style llm_providers fill:#fff,stroke:#333,stroke-width:2px
    style storage fill:#fff,stroke:#333,stroke-width:2px
    style implementations fill:#fff,stroke:#333,stroke-width:2px
```

## Mô Tả Chi Tiết

### 1. Tầng Ứng Dụng Khách Hàng
- **Python Application**: Ứng dụng Python import thư viện LightRAG
- **Web Browser**: Giao diện React UI
- **AI Chatbot**: Tích hợp với Ollama API

### 2. Tầng API Server
- **lightning_server.py**: Ứng dụng FastAPI làm API Gateway

### 3. API Routes
- **document_routes.py**: Xử lý upload, insert, delete tài liệu
- **query_routes.py**: Thực thi các truy vấn
- **graph_routes.py**: Truy xuất dữ liệu đồ thị
- **ollama_api.py**: API tương thích với Ollama

### 4. Core Framework
- **operate.py**: Xử lý chunking, extract entities, merge nodes/edges, thực hiện truy vấn

### 5. Tích Hợp LLM
- **llm_model_func**: Gọi các model LLM với giới hạn ưu tiên
- **embedding_func**: Tạo embeddings cho văn bản

### 6. Storage Abstraction
- **BaseKVStorage**: Lưu trữ key-value
- **BaseVectorStorage**: Lưu trữ vector embeddings
- **BaseGraphStorage**: Lưu trữ đồ thị tri thức
- **DocStatusStorage**: Theo dõi trạng thái tài liệu

### 7. Storage Implementations
- **JsonKVStorage**: Lưu trữ KV bằng JSON
- **NanoVectorDBStorage**: Vector DB nhỏ gọn
- **MilvusVectorDBStorage**: Vector DB quy mô lớn
- **NetworkXStorage**: Đồ thị với NetworkX
- **Neo4jStorage**: Đồ thị với Neo4j

## Luồng Dữ Liệu

1. **Client** gửi request → **API Server**
2. **API Server** route request đến **API Routes** tương ứng
3. **API Routes** gọi **Core Framework** (operate.py)
4. **Core** sử dụng:
   - **LLM Integration** để xử lý văn bản
   - **Storage Abstraction** để lưu/đọc dữ liệu
5. **Storage Implementations** thực hiện lưu trữ thực tế

## Đặc Điểm Nổi Bật

- ✅ **Kiến trúc module hóa**: Tách biệt rõ ràng các layer
- ✅ **Abstraction Pattern**: Dễ dàng thay đổi storage backend
- ✅ **Multiple LLM Support**: Hỗ trợ nhiều nhà cung cấp LLM
- ✅ **Graph + Vector**: Kết hợp đồ thị tri thức và vector search
- ✅ **FastAPI**: API hiệu suất cao, async/await
- ✅ **Ollama Compatible**: Tích hợp với local LLM models
