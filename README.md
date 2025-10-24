# UIT Docs Crawler

Web crawler cho website UIT sử dụng Firecrawl self-hosted.

## Yêu cầu

- Docker (cấp 4GB+ RAM)
- 8GB+ RAM hệ thống
- 10GB+ dung lượng trống

## Cách chạy

### 1. Cài đặt

```bash
# Clone repo
git clone https://github.com/Jajajou/UIT_DOCS_AGENT.git
cd UIT_DOCS_AGENT

# Copy file cấu hình
cp .env.example .env
```

### 2. Chạy

```bash
# Khởi động tất cả services
docker compose up -d

# Lần đầu chạy mất 5-10 phút để khởi tạo
```

### 3. Kiểm tra

```bash
# Xem trạng thái
docker compose ps

# Xem log crawler
docker logs firecrawl-uit-crawler -f

# Xem tất cả log
docker compose logs -f
```

### 4. Truy cập Bull Queue UI

Mở trình duyệt: http://localhost:3002/admin/CHANGEME/queues

(Đổi `CHANGEME` thành giá trị `BULL_AUTH_KEY` trong file `.env`)

## Cấu hình

Chỉnh sửa file `.env`:

```bash
# Thời gian chạy lại (giờ)
SCHEDULE_HOURS=24

# Số worker song song
MAX_WORKERS=3

# Chạy 1 lần rồi dừng
RUN_ONCE=false
```

Chỉnh sửa file `config.yaml` để thay đổi URL crawl:

```yaml
seed_urls:
  - https://daa.uit.edu.vn/qui-che-qui-dinh-qui-trinh
  - https://daa.uit.edu.vn/thongbaochinhquy

max_depth: 3

include_patterns:
  - /qui-dinh
  - /thong-bao

exclude_patterns:
  - /news
  - /blog
```

## Kết quả

Dữ liệu crawl được lưu trong thư mục `data/`:

```
data/
├── daa/
│   ├── chuong-trinh-dao-tao/
│   ├── quy-dinh/
│   ├── quy-trinh/
│   └── thong-bao/
├── metadata.json
├── metadata.jsonl
├── crawl_stats.json
└── failed_urls.jsonl
```

## Dừng crawler

```bash
# Dừng tất cả services
docker compose down

# Dừng và xóa dữ liệu
docker compose down -v
```

## Xử lý lỗi

### Services không khởi động

```bash
# Kiểm tra log
docker logs firecrawl-api

# Khởi động lại
docker compose restart

# Kiểm tra Docker đã cấp đủ 4GB RAM
```

### Hết bộ nhớ

- Tăng RAM cho Docker lên 4GB+
- Giảm `MAX_WORKERS` xuống 2 hoặc 1
- Đóng các ứng dụng khác

### Kết nối bị từ chối

- Đợi 5-10 phút cho lần khởi động đầu
- Kiểm tra: `docker compose ps`
- Tất cả services phải "healthy"

## Tài nguyên

- RAM: ~2-3GB (5 containers)
- CPU: 2+ cores
- Disk: ~10GB

## License

MIT
