# 🔥 UIT Documentation Crawler# 🔥 UIT Documentation CrawlerUIT_DOCS_AGENT



> Crawl và extract nội dung từ website daa.uit.edu.vn

> **Local web crawler** for UIT (University of Information Technology) documentation website with smart crawling features, SSL bypass for internal networks, and comprehensive data extraction.

## 📚 Tổng quan

[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

Project này cung cấp **2 phiên bản crawler**:[![Python](https://img.shields.io/badge/Python-3.11-green.svg)](https://www.python.org/)

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

1. **Custom Crawler** (`uit_crawler/`) - ⭐ **KHUYÊN DÙNG**

   - Đơn giản, nhẹ nhàng (512MB RAM)## 📋 Table of Contents

   - 1 container, dễ maintain

   - Đủ tính năng cho UIT- [Features](#-features)

- [Quick Start](#-quick-start)

2. **Firecrawl Self-Hosted** (`firecrawl_version/`)- [Project Structure](#-project-structure)

   - Chuyên nghiệp, nhiều tính năng- [Configuration](#-configuration)

   - 5 containers, JavaScript rendering- [Usage](#-usage)

   - Nặng hơn (2-3GB RAM)- [Output Data](#-output-data)

- [Advanced Configuration](#-advanced-configuration)

## 🚀 Quick Start- [Troubleshooting](#-troubleshooting)



### Option 1: Custom Crawler (Recommended)## ✨ Features



```bash### Core Capabilities

# 1. Edit seed URLs (optional)- 🌐 **Local-only crawler** - No external API dependencies

nano .env- 🔒 **SSL verification bypass** - Works with internal UIT network (self-signed certificates)

- 🤖 **robots.txt compliance** - Respects crawl-delay and disallow rules (configurable)

# 2. Start crawler- 📊 **Multiple data formats** - HTML, PDF, DOCX, text extraction

docker compose up -d --build- 🔄 **Smart scheduling** - Automatic recurring crawls every 24 hours

- 🚦 **Rate limiting** - Configurable request delays and bandwidth throttling

# 3. Monitor logs- 📝 **Comprehensive logging** - Track all crawling activities

docker logs firecrawl-uit -f

### Advanced Features

# 4. Check results- ⏰ **Time windows** - Run only during specified hours (e.g., off-peak times)

ls -lh data/- 🔀 **Jittered pacing** - Random delays to appear more human-like

```- 🔁 **Backoff on errors** - Automatic retry with exponential backoff on 429/503

- 🎯 **Pattern matching** - Include/exclude URL patterns for targeted crawling

### Option 2: Firecrawl Self-Hosted- 📏 **Depth control** - Limit crawling depth (default: 3 levels)

- 🌐 **Host network mode** - Access internal UIT servers (10.204.2.x)

```bash

# 1. Go to firecrawl_version## 🚀 Quick Start

cd firecrawl_version

### Prerequisites

# 2. Configure (optional)- Docker Desktop installed and running

cp .env.example .env- Git (for cloning the repository)

- Access to UIT internal network (for internal URLs)

# 3. Start (takes 5-10 mins first time)

docker compose up -d### Installation



# 4. Monitor1. **Clone the repository**

docker logs firecrawl-uit-crawler -f```bash

```git clone https://github.com/Jajajou/UIT_DOCS_AGENT.git

cd UIT_DOCS_AGENT

## 📂 Cấu trúc Project```



```2. **Review/Edit configuration** (optional)

uit_firecrawl_new/```bash

├── uit_crawler/              # Custom crawler (⭐ recommended)# Edit .env file to customize URLs and settings

│   ├── main.py               # Core crawlernotepad .env  # Windows

│   ├── utils/                # Helper modulesnano .env     # Linux/Mac

│   ├── config.yaml           # Base config```

│   └── Dockerfile

│3. **Start crawling**

├── firecrawl_version/        # Firecrawl self-hosted version```bash

│   ├── main.py               # Wrapper script# Build and run in background

│   ├── docker-compose.yml    # 5 services stackdocker compose up -d --build

│   ├── README.md             # Full documentation

│   └── QUICKSTART.md# Or run once and exit

│docker compose run --rm app

├── firecrawl/                # Official Firecrawl (git submodule)```

│   └── ...                   # Reference only

│4. **Monitor progress**

├── docs/                     # Documentation```bash

│   ├── WHY_CUSTOM_CRAWLER.md# View logs

│   ├── COMPARISON_ALL_VERSIONS.mddocker logs firecrawl-uit -f

│   └── ...

│# Check data

├── docker-compose.yml        # Custom crawler composels data/html    # HTML files

└── .env                      # Configurationls data/pdf     # PDF files

```ls data/text    # Extracted text

```

## 📊 So sánh

## 📁 Project Structure

| Feature | Custom Crawler | Firecrawl Self-Hosted |

|---------|---------------|----------------------|```

| **RAM** | 512MB | 2-3GB |firecrawl-uit-local-advanced/

| **Containers** | 1 | 5 |├── .env                    # Environment configuration

| **Setup time** | 2 phút | 5-10 phút |├── .gitignore             # Git ignore rules

| **JavaScript** | ❌ | ✅ |├── docker-compose.yml     # Docker compose configuration

| **Markdown** | ❌ | ✅ |├── README.md              # This file

| **PDF Download** | ✅ | ✅ |├── data/                  # Output directory (crawled data)

| **Complexity** | Đơn giản | Phức tạp |│   ├── html/             # Raw HTML pages

│   ├── pdf/              # Downloaded PDF files

## 📖 Documentation│   ├── docs/             # Office documents (DOCX, XLS, etc.)

│   ├── text/             # Extracted text from files

Xem chi tiết trong folder `docs/`:│   ├── metadata.json     # Complete metadata (JSON)

│   └── metadata.jsonl    # Line-delimited metadata

- [WHY_CUSTOM_CRAWLER.md](docs/WHY_CUSTOM_CRAWLER.md) - Lý do chọn custom crawler├── firecrawl/            # Crawler application

- [COMPARISON_ALL_VERSIONS.md](docs/COMPARISON_ALL_VERSIONS.md) - So sánh 3 phiên bản│   ├── main.py           # Main crawler script

- [DOCUMENTATION_INDEX.md](docs/DOCUMENTATION_INDEX.md) - Index toàn bộ docs│   ├── config.yaml       # Base configuration

│   ├── Dockerfile        # Docker image definition

## ⚙️ Configuration│   └── utils/            # Utility modules

│       ├── downloader.py # File download handler

Edit file `.env`:│       ├── parser.py     # Content parsing

│       ├── ratelimit.py  # Rate limiting

```bash│       └── storage.py    # Data storage

# 35 seed URLs for UIT documentation└── logs/                 # Application logs

SEED_URLS=https://daa.uit.edu.vn/qui-che-qui-dinh-qui-trinh,...    └── firecrawl.log     # Main log file

```

# Crawl behavior

MAX_DEPTH=3## ⚙️ Configuration

CONCURRENCY=2

RATE_LIMIT=1### Environment Variables (.env)



# Schedule (crawl every 24 hours)The crawler is configured via the `.env` file. Key settings:

SCHEDULE_HOURS=24

RUN_ONCE=false#### Crawl Targets

``````bash

# Multiple URLs separated by commas

## 📁 OutputSEED_URLS=https://daa.uit.edu.vn/qui-che-qui-dinh-qui-trinh,https://daa.uit.edu.vn/thongbaochinhquy,...



```# URL patterns to include

data/INCLUDE_PATTERNS=/qui-che,/quy-dinh,/ctdt-khoa,/cqui,/tu-xa

├── html/           # Raw HTML files

├── pdf/            # Downloaded PDFs# URL patterns to exclude

├── text/           # Extracted textEXCLUDE_PATTERNS=/tin-tuc,/news,/blog

└── metadata.json   # Metadata```

```

#### Crawl Behavior

## 🔧 Common Commands```bash

MAX_DEPTH=3              # How deep to follow links (0-10)

```bashCONCURRENCY=2            # Parallel requests (1-5 recommended)

# Start crawlerRATE_LIMIT=1             # Delay between requests in seconds

docker compose up -dRESPECT_ROBOTS=false     # robots.txt compliance (false for internal sites)

```

# Stop crawler

docker compose down#### Scheduling

```bash

# View logsSCHEDULE_HOURS=24        # Hours between crawl runs

docker logs firecrawl-uit -fRUN_ONCE=false          # Set to true for one-time crawl

ACTIVE_WINDOW=          # Time ranges: "01:00-05:00,12:00-13:00"

# Restart with new configWINDOW_TZ=Asia/Ho_Chi_Minh

docker compose down && docker compose up -d --build```



# Clean all data#### Performance

docker compose down -v```bash

rm -rf data/ logs/BANDWIDTH_BPS=0          # Bandwidth limit (0 = unlimited)

```JITTER_MAX=0.5          # Random delay variance (seconds)

```

## 🆘 Troubleshooting

### Current Crawl Targets

### Container keeps restarting

**Solution**: Check logs with `docker logs firecrawl-uit`The crawler is configured to crawl:



### No files downloaded**📚 Training Programs (Chương trình đào tạo)**

**Solution**: - Regular programs: 2012-2025 (13 years)

1. Check seed URLs in `.env`- Distance learning: 2008, 2013, 2018-2024 (8 years)

2. Verify network connectivity

3. Check `INCLUDE_PATTERNS` and `EXCLUDE_PATTERNS`**📋 Regulations & Guidelines**

- University regulations

### Out of memory- Training guidelines

**Solution**: - Announcements (regular & distance learning)

- Custom crawler: Should work with 512MB- Administrative procedures

- Firecrawl: Need 4GB+ Docker memory

See `.env` file for complete list of URLs.

## 📚 More Info

## 🎯 Usage

- [Firecrawl Self-Hosted Guide](firecrawl_version/README.md)

- [Full Documentation](docs/DOCUMENTATION_INDEX.md)### Basic Commands

- [Migration History](docs/MIGRATION_COMPLETE.md)

**Start crawler (background)**

## 🏆 Recommendation```bash

docker compose up -d

**Cho UIT use case**: Dùng **Custom Crawler** (uit_crawler/)```

- ✅ Đơn giản, nhẹ, nhanh

- ✅ Đủ tính năng**View real-time logs**

- ✅ Dễ maintain```bash

docker logs firecrawl-uit -f

**Cho website phức tạp**: Dùng **Firecrawl Self-Hosted**```

- ✅ JavaScript rendering

- ✅ Advanced anti-bot**Stop crawler**

- ❌ Nặng hơn```bash

docker compose down

---```



**Made with ❤️ for UIT****Restart crawler**

```bash
docker compose restart
```

**Run once and exit**
```bash
docker compose run --rm -e RUN_ONCE=true app
```

### Check Results

**View statistics**
```powershell
# Count files
(Get-ChildItem data\html -File).Count   # HTML files
(Get-ChildItem data\pdf -File).Count    # PDF files

# Check total size
(Get-ChildItem data -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
```

## 📊 Output Data

### Data Structure

After crawling, data is organized as:

```
data/
├── html/               # Raw HTML files
│   └── _qui-che-qui-dinh-qui-trinh,-06a1251ebe.html
├── pdf/                # PDF documents
│   └── _sites_daa_files_202310_quy_che.pdf
├── text/               # Extracted text
│   └── _sites_daa_files_202310_quy_che.txt
├── docs/               # Office documents
│   └── form_dang_ky.xls
├── metadata.json       # All metadata (JSON array)
└── metadata.jsonl      # Line-delimited JSON
```

### Metadata Format

Each crawled page/file has metadata:
```json
{
  "title": "Quy chế quy định quy trình",
  "url": "https://daa.uit.edu.vn/qui-che-qui-dinh-qui-trinh",
  "type": "html",
  "content": "Full text content...",
  "download_path": "/data/html/_qui-che-qui-dinh-qui-trinh.html",
  "date": "2024-01-15",
  "source": "daa.uit.edu.vn"
}
```

### Current Statistics

After full crawl:
- **HTML files**: ~86 pages
- **PDF documents**: ~131 files
- **Text files**: ~131 extracted texts
- **Total size**: ~267 MB

## 🔧 Advanced Configuration

### Custom Crawl Schedule

Run only during off-peak hours:
```bash
# Edit .env
ACTIVE_WINDOW=01:00-05:00,22:00-23:59
SCHEDULE_HOURS=24
```

### Bandwidth Limiting

Limit bandwidth to be polite:
```bash
BANDWIDTH_BPS=100000    # ~100 KB/s
JITTER_MAX=1.0          # Add random delays
```

### Add More URLs

Edit `.env` and add to `SEED_URLS`:
```bash
SEED_URLS=...,https://daa.uit.edu.vn/new-page
```

Then restart:
```bash
docker compose restart
```

### Docker Compose Configuration

The `docker-compose.yml` uses:
- **Host network mode** - Required for UIT internal network access
- **Volume mounts** - Persists data and logs
- **Environment variables** - Configuration from `.env`
- **Auto-restart** - Keeps crawler running

## 🐛 Troubleshooting

### Common Issues

**1. Docker not starting**
```bash
# Check if Docker Desktop is running
docker ps

# Start Docker Desktop (Windows)
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```

**2. SSL Certificate errors**
```
[SSL: CERTIFICATE_VERIFY_FAILED]
```
✅ Already fixed - SSL verification is disabled for internal UIT network

**3. Connection refused**
```
[Errno 111] Connection refused
```
- Check if you're on UIT network
- VPN might be required for internal URLs

**4. No data being crawled**
```bash
# Check logs
docker logs firecrawl-uit --tail 50

# Verify .env configuration
cat .env
```

**5. Container keeps restarting**
```bash
# Check logs for errors
docker logs firecrawl-uit

# Remove and recreate
docker compose down
docker compose up -d --build
```

### Debug Mode

Enable verbose logging:
```bash
# Edit firecrawl/main.py
# Change: logging.INFO to logging.DEBUG
```

## 📝 Notes

- **Internal Network**: Crawler uses `network_mode: host` to access UIT internal servers (10.204.2.x)
- **SSL Bypass**: SSL verification is disabled (`verify=False`) for self-signed certificates
- **Data Persistence**: All crawled data is stored in `./data` and persists across container restarts
- **Logs**: Available in `./logs/firecrawl.log` and via `docker logs`

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- Built for UIT (University of Information Technology)
- Based on local Firecrawl implementation
- Designed for educational documentation archival

---

**Made with ❤️ for UIT Community**
