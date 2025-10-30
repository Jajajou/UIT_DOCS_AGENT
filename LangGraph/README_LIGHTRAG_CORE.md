# LightRAG Core Integration Guide

## Tổng quan

Dự án đã được chuyển đổi từ việc gọi LightRAG API sang sử dụng **LightRAG Core** trực tiếp trong LangGraph workflow. Điều này mang lại các lợi ích:

- ✅ Không cần chạy LightRAG Server riêng
- ✅ Giảm độ trễ (không có network overhead)
- ✅ Kiểm soát đầy đủ cấu hình và prompts
- ✅ Tích hợp sâu hơn với LangGraph
- ✅ Sử dụng custom prompts tối ưu cho chatbot công tác sinh viên

## Thay đổi chính

### 1. Prompt System - XML Format

Tất cả prompts đã được chuyển sang **XML format** để phù hợp với Qwen3-4B-Instruct và tối ưu cho ngữ cảnh university chatbot:

- **Entity Extraction**: Tập trung vào các thực thể liên quan công tác sinh viên (quy chế, học bổng, tổ chức, thủ tục...)
- **Response Generation**: Tối ưu cho việc trả lời câu hỏi sinh viên với ngôn ngữ chuyên nghiệp
- **Language**: Toàn bộ prompts và ví dụ bằng tiếng Việt

### 2. LightRAG Core Module

File mới: `src/agent/lightrag_core.py`

- `LightRAGCore`: Wrapper class cho LightRAG library
- `get_lightrag_core()`: Singleton pattern để tái sử dụng instance
- Hỗ trợ async operations cho LangGraph

### 3. Updated Graphs

#### Query Graph (`query_graph.py`)
- Thay thế `LightRAGAPIClient` bằng `LightRAGCore`
- Node `call_lightrag_core` thay cho `call_query_api`
- Async query execution

#### Indexing Graph (`indexing_graph.py`)
- Thay thế API calls bằng core library
- Node `upload_to_lightrag` giờ là async
- Đọc file content trực tiếp thay vì upload qua API
- Loại bỏ chức năng "scan" (không áp dụng cho core mode)

### 4. Custom Prompts

File: `src/agent/prompt.py`

Các prompt chính:
- `entity_extraction_system_prompt`: Trích xuất thực thể với XML structure
- `entity_extraction_examples`: Ví dụ về quy chế, học bổng, phòng ban
- `rag_response`: Prompt trả lời câu hỏi sinh viên
- `keywords_extraction`: Trích xuất từ khóa tiếng Việt

## Cấu hình

### 1. Environment Variables

Copy và chỉnh sửa file `.env`:

```bash
cp .env.example .env
```

### 2. LLM Configuration

Sử dụng Hugging Face Router với Qwen3-4B-Instruct:

```env
LLM_MODEL=Qwen/Qwen3-4B-Instruct
LLM_BINDING_HOST=https://router.huggingface.co/v1
OPENAI_API_KEY=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. Embedding Configuration

Sử dụng BGE-M3 qua Ollama hoặc embedding service:

```env
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_BINDING_HOST=http://localhost:11434
EMBEDDING_DIM=1024
```

### 4. Storage Configuration

**Default (File-based):**
```env
LIGHTRAG_KV_STORAGE=JsonKVStorage
LIGHTRAG_VECTOR_STORAGE=NanoVectorDBStorage
LIGHTRAG_GRAPH_STORAGE=NetworkXStorage
LIGHTRAG_DOC_STATUS_STORAGE=JsonDocStatusStorage
```

**PostgreSQL (Recommended for production):**
```env
LIGHTRAG_KV_STORAGE=PGKVStorage
LIGHTRAG_VECTOR_STORAGE=PGVectorStorage
LIGHTRAG_GRAPH_STORAGE=PGGraphStorage
LIGHTRAG_DOC_STATUS_STORAGE=PGDocStatusStorage

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_DATABASE=lightrag_db
```

**Qdrant (For vector storage):**
```env
LIGHTRAG_VECTOR_STORAGE=QdrantVectorDBStorage
QDRANT_URL=http://localhost:6333
```

## Installation

### 1. Install Dependencies

```bash
cd LangGraph
pip install -e .
```

Hoặc cài đặt trực tiếp:

```bash
pip install lightrag-hku
```

### 2. Setup Storage

**For PostgreSQL:**
```bash
# Create database
createdb lightrag_db

# LightRAG will auto-create tables on first run
```

**For Qdrant:**
```bash
# Run Qdrant with Docker
docker run -p 6333:6333 qdrant/qdrant
```

## Usage

### 1. Run LangGraph Server

```bash
cd LangGraph
langgraph dev
```

### 2. Indexing Documents

**Via Chat UI:**
```
upload /path/to/documents/
```

**Via Graph Tab:**
```json
{
  "source_type": "file",
  "input_source": "/path/to/document.pdf"
}
```

### 3. Query

**Via Chat UI:**
```
Sinh viên cần tích lũy bao nhiêu tín chỉ để tốt nghiệp?
```

**Via Graph Tab:**
```json
{
  "query": "Sinh viên cần tích lũy bao nhiêu tín chỉ để tốt nghiệp?",
  "mode": "mix",
  "top_k": 60
}
```

## Entity Types

Các loại thực thể được tối ưu cho university chatbot:

- `organization`: Phòng ban, khoa, đơn vị (Phòng Đào tạo, Phòng CTSV...)
- `person`: Sinh viên, cán bộ, giảng viên
- `regulation`: Quy chế, quy định, quy trình
- `procedure`: Thủ tục hành chính
- `scholarship`: Học bổng, hỗ trợ tài chính
- `system`: Hệ thống thông tin (Portal, LMS...)
- `location`: Địa điểm, phòng học, cơ sở
- `event`: Sự kiện, hoạt động sinh viên
- `document`: Văn bản, tài liệu
- `other`: Các thực thể khác

## Query Modes

- `local`: Tìm kiếm dựa trên entities cục bộ
- `global`: Tìm kiếm dựa trên relationships toàn cục
- `hybrid`: Kết hợp local và global
- `naive`: Tìm kiếm đơn giản trên chunks
- `mix`: Kết hợp knowledge graph và vector search (recommended)

## Troubleshooting

### 1. Import Error

```
ModuleNotFoundError: No module named 'lightrag'
```

**Solution:**
```bash
pip install lightrag-hku
```

### 2. Storage Initialization Error

```
AttributeError: __aenter__
```

**Solution:** Đảm bảo gọi `await lightrag_core.initialize()` trước khi sử dụng.

### 3. LLM Timeout

```
Timeout waiting for LLM response
```

**Solution:** Tăng timeout trong `.env`:
```env
LLM_TIMEOUT=1800
```

### 4. Embedding Dimension Mismatch

```
Vector dimension mismatch
```

**Solution:** Xóa vector storage và rebuild:
```bash
rm -rf ./rag_storage/vdb_*
```

## Performance Tips

1. **Use PostgreSQL** cho production thay vì file-based storage
2. **Enable LLM Cache** để tăng tốc entity extraction:
   ```env
   ENABLE_LLM_CACHE=true
   ```
3. **Adjust MAX_ASYNC** dựa trên tài nguyên server:
   ```env
   MAX_ASYNC=4  # Tăng nếu có nhiều CPU/RAM
   ```
4. **Use Reranker** để cải thiện retrieval quality (cấu hình trong env.lightrag)

## Migration from API Mode

Nếu bạn đang có data từ LightRAG Server:

1. Export data từ server (nếu có API export)
2. Hoặc copy working directory:
   ```bash
   cp -r /path/to/server/data ./rag_storage
   ```
3. Đảm bảo cấu hình storage backend giống nhau

## Next Steps

- [ ] Thêm confidence scoring cho responses
- [ ] Implement fallback mechanism (liên hệ cố vấn khi không chắc chắn)
- [ ] Thêm conversation memory với PostgreSQL backend
- [ ] Tối ưu prompts dựa trên feedback từ sinh viên
- [ ] A/B testing các query modes

## Support

Nếu gặp vấn đề, vui lòng:
1. Check logs: `LIGHTRAG_LOG_LEVEL=DEBUG`
2. Xem LightRAG documentation: https://github.com/HKUDS/LightRAG
3. Tạo issue trên GitHub repo
