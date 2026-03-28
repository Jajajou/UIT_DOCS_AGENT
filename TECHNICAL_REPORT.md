# TECHNICAL REPORT: UIT DATA CRAWLING & KNOWLEDGE BASE SYSTEM

**Project Name:** UIT Docs Agent Data Pipeline  
**Date:** November 27, 2025  
**Version:** 1.1  
**Status:** Production Ready

---

## 1. Executive Summary

Dự án này xây dựng một hệ thống thu thập và xử lý dữ liệu tự động (Data Pipeline) nhằm tạo lập cơ sở tri thức (Knowledge Base) cho trợ lý ảo AI của trường Đại học Công nghệ Thông tin (UIT). Hệ thống sử dụng **Firecrawl** làm nòng cốt để thu thập dữ liệu từ các cổng thông tin đào tạo, kết hợp với quy trình xử lý dữ liệu đa tầng (filtering, deduplication, cleaning) để đảm bảo chất lượng dữ liệu đầu vào cho hệ thống RAG (Retrieval-Augmented Generation).

Kết quả đạt được là bộ dữ liệu sạch gồm **739 trang tài liệu** chất lượng cao, bao gồm chương trình đào tạo, quy định, và thông báo, sẵn sàng cho việc vector hóa và truy xuất.

---

## 2. System Architecture (Kiến Trúc Hệ Thống)

Hệ thống được thiết kế theo kiến trúc Microservices, bao gồm các thành phần chính sau:

### 2.1 High-Level Architecture

```mermaid
graph TD
    A[Seed URLs & Config] -->|Input| B(Firecrawl Engine)
    B -->|Raw HTML| C{Data Processing Pipeline}
    
    subgraph "Crawling Layer"
    B1[Redis Queue] <--> B
    B2[Playwright Renderer] <--> B
    end
    
    subgraph "Processing Layer"
    C -->|Step 1| D[Pattern Filtering]
    D -->|Step 2| E[Deduplication Engine]
    E -->|Step 3| F[Content Cleaning]
    end
    
    subgraph "Storage Layer"
    F -->|Structured Data| G[Metadata Store (JSON/SQL)]
    F -->|Embeddings| H[Vector DB (Qdrant/Pgvector)]
    F -->|Entities| I[Knowledge Graph (LightRAG)]
    end
```

### 2.2 Core Components

1.  **Crawl Engine (Firecrawl):** Service chịu trách nhiệm điều hướng, render JavaScript và trích xuất HTML thô.
2.  **Job Queue (Redis):** Quản lý hàng đợi URL, đảm bảo rate limiting và khả năng resume khi lỗi.
3.  **Processing Unit:** Module Python thực hiện các logic lọc, làm sạch và chuẩn hóa dữ liệu.
4.  **Storage:** Hệ thống lưu trữ đa dạng cho metadata, vector embeddings và graph data.

---

## 3. Detailed Workflow (Quy Trình Chi Tiết)

Đây là phần trọng tâm mô tả luồng dữ liệu từ URL ban đầu đến khi trở thành tri thức trong Database.

### Phase 1: Initialization & Configuration (Khởi Tạo)

Quy trình bắt đầu bằng việc xác định phạm vi và cấu hình:

1.  **Seed Selection:**
    *   Input: Danh sách 40+ URL gốc (Seed URLs) từ `daa.uit.edu.vn` và `tuyensinh.uit.edu.vn`.
    *   Strategy: Chọn các trang mục lục (Index pages) như "Danh sách CTDT", "Thông báo chung" để tối đa hóa khả năng discovery.

2.  **Configuration Loading:**
    *   Load `config.yaml`: Xác định `max_depth` (3), `rate_limit` (10 req/min), và các patterns.
    *   Khởi tạo Redis queue rỗng hoặc load trạng thái cũ (nếu resume).

**Code Illustration (Config):**
```yaml
# config.yaml
crawl_config:
  seed_urls:
    - https://daa.uit.edu.vn/content/cong-thong-tin-dao-tao
  max_depth: 3
  rate_limit: 10  # requests per minute
  include_patterns:
    - /content/.*
    - /thongbao.*
  exclude_patterns:
    - \.(pdf|doc|docx)$
    - /admin/.*
```

### Phase 2: Crawling Execution (Thu Thập)

Firecrawl thực hiện vòng lặp thu thập dữ liệu:

1.  **URL Discovery:**
    *   Từ Seed URL, Firecrawl render trang bằng **Playwright**.
    *   Trích xuất tất cả thẻ `<a>` (links).
    *   **Normalization:** Chuẩn hóa URL (lowercase, remove fragment, sort query params) ngay lập tức.

2.  **Filtering (Pre-Crawl):**
    *   Kiểm tra URL mới phát hiện với `include_patterns` (ví dụ: phải chứa `/content/` hoặc `/thongbao`).
    *   Kiểm tra với `exclude_patterns` (loại bỏ `.pdf`, `/admin`).
    *   Kiểm tra `visited_set` trong Redis để tránh vòng lặp vô hạn.

**Code Illustration (Filtering Logic):**
```python
import re

def should_crawl(url, config):
    # 1. Check exclude patterns
    for pattern in config['exclude_patterns']:
        if re.search(pattern, url):
            return False
            
    # 2. Check include patterns
    for pattern in config['include_patterns']:
        if re.search(pattern, url):
            return True
            
    return False
```

3.  **Queueing:**
    *   Các URL hợp lệ được đẩy vào Redis Queue.
    *   Worker lấy URL từ Queue theo cơ chế FIFO.

4.  **Rendering & Extraction:**
    *   Playwright mở headless browser.
    *   Đợi dynamic content load (network idle).
    *   Lấy `document.body.innerHTML` và convert sang Markdown/Text.

### Phase 3: Data Processing & Cleaning (Xử Lý)

Dữ liệu thô (Raw Data) đi qua pipeline làm sạch nghiêm ngặt:

1.  **Duplicate Detection (Phát hiện trùng lặp):**
    *   **Level 1 (URL):** Đã xử lý ở Phase 2.
    *   **Level 2 (Content Hash):** Tạo MD5 hash của nội dung text đã chuẩn hóa. Nếu hash trùng với trang đã lưu -> Discard.
    *   **Level 3 (Semantic - Optional):** So sánh vector similarity để loại bỏ các trang có nội dung "gần giống" (near-duplicates).

**Code Illustration (Deduplication):**
```python
import hashlib

def get_content_hash(content):
    # Normalize content: lowercase, remove extra spaces
    normalized = " ".join(content.lower().split())
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()

def is_duplicate(content, seen_hashes):
    content_hash = get_content_hash(content)
    if content_hash in seen_hashes:
        return True
    seen_hashes.add(content_hash)
    return False
```

2.  **Boilerplate Removal (Loại bỏ nhiễu):**
    *   **Header/Footer:** Sử dụng thư viện `trafilatura` hoặc custom regex để loại bỏ `<nav>`, `<footer>`, `.sidebar`.
    *   **Noise Reduction:** Loại bỏ các đoạn text ngắn vô nghĩa ("Click here", "Read more"), quảng cáo, menu điều hướng.

**Code Illustration (Cleaning):**
```python
from bs4 import BeautifulSoup

def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove header, footer, nav
    for tag in soup(['header', 'footer', 'nav', 'script', 'style']):
        tag.decompose()
        
    # Remove specific Drupal sidebar classes
    for div in soup.find_all("div", class_=["sidebar", "region-sidebar-first"]):
        div.decompose()
        
    return soup.get_text(separator='\n')
```

3.  **Metadata Extraction:**
    *   Trích xuất Title, Date, Author, Category từ HTML structure hoặc URL path.
    *   Gán nhãn category tự động dựa trên URL pattern (ví dụ: URL chứa `thong-bao` -> Category: "Announcement").

### Phase 4: Storage & Indexing (Lưu Trữ)

Dữ liệu sạch được lưu trữ theo 3 định dạng phục vụ các mục đích khác nhau:

1.  **Raw/Metadata Storage (JSONL):**
    *   Lưu trữ `url`, `title`, `content` (markdown), `timestamp` vào file `metadata.jsonl`.
    *   Mục đích: Backup, audit, và re-indexing sau này.

2.  **Vector Indexing (Qdrant/Pgvector):**
    *   **Chunking:** Chia nhỏ văn bản thành các đoạn (chunks) 512-1024 tokens (có overlap).
    *   **Embedding:** Sử dụng model (ví dụ: `text-embedding-3-small` hoặc `bge-m3`) để chuyển text thành vector.
    *   **Upsert:** Lưu vector + payload vào Vector DB.

3.  **Knowledge Graph Construction (LightRAG):**
    *   Sử dụng LLM để trích xuất Entities (Môn học, Giảng viên, Khoa) và Relationships (Thuộc về, Giảng dạy).
    *   Xây dựng đồ thị tri thức để phục vụ các câu hỏi phức tạp (Multi-hop reasoning).

---

## 4. Technical Stack & Rationale

| Component | Technology | Lý do lựa chọn |
|-----------|------------|----------------|
| **Crawler** | **Firecrawl** | Khả năng xử lý JS tốt hơn BeautifulSoup, API đơn giản, output Markdown sạch. |
| **Browser Engine** | **Playwright** | Render chính xác các trang Single Page App (SPA) của UIT, bypass bot detection cơ bản. |
| **Queue** | **Redis** | Tốc độ cao, persistence, hỗ trợ distributed crawling nếu cần scale. |
| **Vector DB** | **Qdrant / Pgvector** | Qdrant cho hiệu năng cao chuyên biệt; Pgvector nếu muốn tích hợp chặt với relational data. |
| **Graph RAG** | **LightRAG** | Framework mới giúp kết hợp Vector Search và Graph Search, tăng độ chính xác cho RAG. |

---

## 5. Data Analysis & Quality Assurance

### 5.1 Dataset Statistics
*   **Tổng số trang:** 739 trang.
*   **Dung lượng:** ~500MB (Raw), ~76MB (Metadata JSON).
*   **Phân loại:**
    *   Chương trình đào tạo (CTDT): ~40%
    *   Thông báo: ~30%
    *   Quy định/Quy chế: ~20%
    *   Khác: ~10%

### 5.2 Quality Metrics
*   **Success Rate:** 100% (không có lỗi crash trong lần chạy cuối).
*   **Skipped Pages:** 42 trang (5.4%) - chủ yếu là file binary hoặc trang login/admin.
*   **Cleanliness:** 95% boilerplate (header/footer) đã được loại bỏ thành công.

---

## 6. Challenges & Solutions

1.  **Vấn đề:** Website UIT sử dụng Drupal, URL sinh ra đôi khi có tham số động (`?q=node/123`) gây trùng lặp.
    *   **Giải pháp:** Áp dụng quy tắc **Canonical URL** nghiêm ngặt và Content Hashing để phát hiện trùng lặp nội dung dù URL khác nhau.

2.  **Vấn đề:** Tốc độ crawl chậm do server phản hồi lâu.
    *   **Giải pháp:** Sử dụng **AsyncIO** trong Python để thực hiện concurrent requests (giới hạn 5-10 concurrent) thay vì sequential.

3.  **Vấn đề:** Nội dung rác (Menu, Sidebar) làm nhiễu kết quả tìm kiếm vector.
    *   **Giải pháp:** Tinh chỉnh thuật toán **Boilerplate Removal** dựa trên Text Density và CSS Selectors đặc thù của theme Drupal UIT.

---

## 7. Conclusion & Future Work

Hệ thống Data Pipeline hiện tại đã hoạt động ổn định và tạo ra bộ dữ liệu chất lượng cao cho UIT Docs Agent. Quy trình workflow được tự động hóa từ khâu thu thập đến lưu trữ.

**Kế hoạch tiếp theo:**
*   **Incremental Crawling:** Thiết lập cronjob để chỉ crawl những trang mới hoặc thay đổi hàng tuần thay vì crawl lại toàn bộ.
*   **Advanced Chunking:** Cải thiện chiến lược chia chunk dựa trên cấu trúc ngữ nghĩa (Semantic Chunking) thay vì fixed size.
*   **Evaluation:** Xây dựng bộ test set (Golden Dataset) để đánh giá độ chính xác của RAG trên dữ liệu đã crawl.

