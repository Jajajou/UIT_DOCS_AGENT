# 🔥 So Sánh 3 Phiên Bản Crawler

## 📊 Bảng So Sánh Nhanh

| Tiêu chí | Custom Crawler ⭐ | Firecrawl Self-Hosted | Firecrawl Cloud API |
|----------|-------------------|----------------------|---------------------|
| **Chi phí** | 🟢 Miễn phí | 🟢 Miễn phí | 🔴 $20+/tháng |
| **RAM** | 🟢 512MB | 🔴 2-3GB | 🟢 512MB |
| **Containers** | 🟢 1 | 🔴 5 | 🟢 1 |
| **Setup** | 🟢 2 phút | 🟡 5-10 phút | 🟢 2 phút |
| **JavaScript** | 🔴 Không | 🟢 Có (Playwright) | 🟢 Có (Playwright) |
| **Anti-bot** | 🟡 Cơ bản | 🟢 Nâng cao | 🟢 Nâng cao |
| **API key** | 🟢 Không cần | 🟢 Không cần | 🔴 Bắt buộc |
| **Bảo trì** | 🟢 Đơn giản | 🔴 Phức tạp | 🟢 Không cần |
| **Tốc độ** | 🟢 Nhanh | 🟡 Trung bình | 🟡 Phụ thuộc API |
| **Debug** | 🟢 Dễ | 🔴 Khó | 🟡 Trung bình |

## 🎯 Khuyến Nghị Sử Dụng

### ⭐ Custom Crawler (uit_crawler/)
**→ KHUYÊN DÙNG CHO UIT**

✅ **Dùng khi:**
- Crawl website nội bộ/đơn giản (như UIT)
- Muốn giải pháp nhẹ nhàng (512MB RAM)
- Không cần JavaScript rendering
- Muốn dễ debug và maintain
- Ưu tiên tốc độ và đơn giản

❌ **KHÔNG dùng khi:**
- Website có anti-bot mạnh
- Cần render JavaScript phức tạp
- Cần chụp screenshot

**📂 Location:** `uit_crawler/`

---

### 🔥 Firecrawl Self-Hosted (firecrawl_version/)
**→ DÙNG CHO WEBSITE PHỨC TẠP**

✅ **Dùng khi:**
- Website có JavaScript rendering
- Có anti-bot/captcha
- Muốn UI quản lý (Bull Queue)
- Có đủ tài nguyên (2-3GB RAM)
- Muốn tính năng chuyên nghiệp
- Không muốn trả phí API

❌ **KHÔNG dùng khi:**
- Website đơn giản (overkill)
- RAM hạn chế (<4GB)
- Muốn giải pháp nhẹ
- Không có kinh nghiệm Docker

**📂 Location:** `firecrawl_version/`

---

### ☁️ Firecrawl Cloud API
**→ DÙNG KHI CẦN TIỆN LỢI**

✅ **Dùng khi:**
- Muốn managed service
- Không muốn tự host
- Ngân sách cho phép ($20+/tháng)
- Cần hỗ trợ kỹ thuật chuyên nghiệp

❌ **KHÔNG dùng khi:**
- Muốn miễn phí
- Crawl nhiều (tốn credit)
- Muốn kiểm soát hoàn toàn
- Data nhạy cảm (phải ở local)

**📂 Location:** Không có code (dùng API từ firecrawl.dev)

## 📈 Chi Tiết So Sánh

### 1. Kiến Trúc

#### Custom Crawler
```
┌─────────────────┐
│  Python Script  │ → Requests + BeautifulSoup
│   (main.py)     │ → BFS crawling
└────────┬────────┘
         │
         ▼
    ┌─────────┐
    │  Data   │
    └─────────┘
```

#### Firecrawl Self-Hosted
```
┌───────────────────────────────────────┐
│  Redis + PostgreSQL + Playwright      │
│              ↓                        │
│      Firecrawl API (Node.js)          │
└──────────────┬────────────────────────┘
               │
               ▼
       ┌───────────────┐
       │ Python Wrapper │
       └───────┬───────┘
               │
               ▼
          ┌─────────┐
          │  Data   │
          └─────────┘
```

#### Firecrawl Cloud API
```
┌─────────────────┐        HTTPS
│ Python Wrapper  │ ───────────────► Firecrawl Cloud
└────────┬────────┘                  (api.firecrawl.dev)
         │
         ▼
    ┌─────────┐
    │  Data   │
    └─────────┘
```

### 2. Dependencies

| | Custom | Self-Hosted | Cloud API |
|---|--------|-------------|-----------|
| **Python** | requests, BeautifulSoup, pyyaml | firecrawl-py | firecrawl-py |
| **Services** | None | Redis, PostgreSQL, Playwright | None |
| **Docker images** | python:3.11-slim | 5 images (~2GB) | python:3.11-slim |

### 3. Tính Năng

| Tính năng | Custom | Self-Hosted | Cloud API |
|-----------|--------|-------------|-----------|
| **HTML crawling** | ✅ | ✅ | ✅ |
| **PDF download** | ✅ | ✅ | ✅ |
| **DOCX parsing** | ✅ | ✅ | ✅ |
| **JavaScript rendering** | ❌ | ✅ | ✅ |
| **Screenshot** | ❌ | ✅ | ✅ |
| **LLM markdown** | ❌ | ✅ | ✅ |
| **Anti-bot bypass** | 🟡 Basic | ✅ | ✅ |
| **Rate limiting** | ✅ | ✅ | ✅ |
| **Robots.txt** | ✅ | ✅ | ✅ |
| **Scheduled crawl** | ✅ | ✅ | ✅ |
| **Bull Queue UI** | ❌ | ✅ | ❌ |

### 4. Performance

#### Crawl 100 trang UIT:

| Metric | Custom | Self-Hosted | Cloud API |
|--------|--------|-------------|-----------|
| **Thời gian** | ~5 phút | ~8-10 phút | ~6-8 phút |
| **RAM** | 200-300MB | 2-3GB | 200MB |
| **CPU** | Low | High | Low |
| **Network** | Minimal | Minimal | Medium |

### 5. Chi Phí (1 năm)

#### Hardware:

| | Custom | Self-Hosted | Cloud API |
|---|--------|-------------|-----------|
| **RAM required** | 512MB VPS | 4GB VPS | 512MB VPS |
| **VPS cost** | $5/mo × 12 = $60 | $20/mo × 12 = $240 | $5/mo × 12 = $60 |
| **API cost** | $0 | $0 | $20/mo × 12 = $240 |
| **Total/year** | **$60** | **$240** | **$300** |

#### Self-hosted (local):
- Custom: **$0** (chạy trên máy hiện có)
- Self-Hosted: **$0** (cần 4GB+ RAM)
- Cloud API: **$240/year** (API fee)

### 6. Maintainability

#### Custom Crawler
- ✅ Code đơn giản (450 LOC main.py)
- ✅ Dễ debug
- ✅ Dễ customize
- ✅ Ít dependencies

#### Firecrawl Self-Hosted
- ❌ Nhiều services phải quản lý
- ❌ Khó debug (5 containers)
- ❌ Update phức tạp
- ❌ Cần hiểu Docker + Node.js

#### Firecrawl Cloud API
- ✅ Không cần maintain
- ✅ Auto-updates
- 🟡 Phụ thuộc uptime của Firecrawl
- 🟡 Ít control

## 🎓 Decision Tree

```
Bạn cần crawl website gì?
│
├─ Website đơn giản (như UIT)
│  ├─ Không có JavaScript phức tạp? → Custom Crawler ⭐
│  └─ Có JavaScript? → Firecrawl Self-Hosted
│
├─ Website có anti-bot mạnh
│  ├─ Có đủ RAM (4GB+)? → Firecrawl Self-Hosted
│  └─ RAM hạn chế? → Firecrawl Cloud API
│
└─ Cần managed service
   └─ → Firecrawl Cloud API
```

## 📋 Checklist Lựa Chọn

### Chọn Custom Crawler nếu:
- [ ] Website không có JavaScript phức tạp
- [ ] RAM hạn chế (<4GB)
- [ ] Muốn solution đơn giản
- [ ] Không cần tính năng nâng cao
- [ ] Ưu tiên tốc độ & maintainability

### Chọn Firecrawl Self-Hosted nếu:
- [ ] Website có JavaScript rendering
- [ ] Có anti-bot/captcha
- [ ] Có đủ RAM (4GB+)
- [ ] Muốn Bull Queue UI
- [ ] Muốn miễn phí nhưng có tính năng pro
- [ ] Có kinh nghiệm Docker

### Chọn Firecrawl Cloud API nếu:
- [ ] Ngân sách cho phép ($20+/tháng)
- [ ] Không muốn tự host
- [ ] Cần hỗ trợ chuyên nghiệp
- [ ] Crawl ít, không thường xuyên

## 🏆 Kết Luận

### Cho UIT Documentation Crawler:

**🥇 KHUYÊN DÙNG: Custom Crawler (uit_crawler/)**

**Lý do:**
1. ✅ Website UIT đơn giản, không cần JavaScript
2. ✅ Nhẹ nhàng (512MB RAM)
3. ✅ Nhanh và ổn định
4. ✅ Dễ maintain
5. ✅ Miễn phí
6. ✅ Đủ tính năng (BFS, rate limit, scheduling)

**🥈 Thay thế: Firecrawl Self-Hosted**
- Nếu cần tính năng nâng cao
- Nếu có đủ tài nguyên (4GB+ RAM)
- Nếu muốn Bull Queue UI để monitor

**🥉 Không khuyên: Firecrawl Cloud API**
- Tốn tiền ($20+/tháng)
- Không cần thiết cho UIT
- Custom crawler đã đủ

---

**📂 Thư mục:**
- Custom: `uit_crawler/`
- Self-Hosted: `firecrawl_version/`
- Cloud: Không có (dùng API key)

**🔗 Xem thêm:**
- [Why Custom Crawler?](../WHY_CUSTOM_CRAWLER.md)
- [Detailed Comparison](../DETAILED_COMPARISON.md)
- [Migration Guide](../MIGRATION_COMPLETE.md)
