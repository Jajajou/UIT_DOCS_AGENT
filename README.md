# 🔥 UIT Documentation Crawler

> **Local web crawler** for UIT (University of Information Technology) documentation website with smart crawling features, SSL bypass for internal networks, and comprehensive data extraction.

[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📋 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Output Data](#-output-data)
- [Advanced Configuration](#-advanced-configuration)
- [Troubleshooting](#-troubleshooting)

## ✨ Features

### Core Capabilities
- 🌐 **Local-only crawler** - No external API dependencies
- 🔒 **SSL verification bypass** - Works with internal UIT network (self-signed certificates)
- 🤖 **robots.txt compliance** - Respects crawl-delay and disallow rules (configurable)
- 📊 **Multiple data formats** - HTML, PDF, DOCX, text extraction
- 🔄 **Smart scheduling** - Automatic recurring crawls every 24 hours
- 🚦 **Rate limiting** - Configurable request delays and bandwidth throttling
- 📝 **Comprehensive logging** - Track all crawling activities

### Advanced Features
- ⏰ **Time windows** - Run only during specified hours (e.g., off-peak times)
- 🔀 **Jittered pacing** - Random delays to appear more human-like
- 🔁 **Backoff on errors** - Automatic retry with exponential backoff on 429/503
- 🎯 **Pattern matching** - Include/exclude URL patterns for targeted crawling
- 📏 **Depth control** - Limit crawling depth (default: 3 levels)
- 🌐 **Host network mode** - Access internal UIT servers (10.204.2.x)

## 🚀 Quick Start

### Prerequisites
- Docker Desktop installed and running
- Git (for cloning the repository)
- Access to UIT internal network (for internal URLs)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/Jajajou/UIT_DOCS_AGENT.git
cd UIT_DOCS_AGENT
git checkout firecrawl
```

2. **Review/Edit configuration** (optional)
```bash
# Edit .env file to customize URLs and settings
notepad .env  # Windows
nano .env     # Linux/Mac
```

3. **Start crawling**
```bash
# Build and run in background
docker compose up -d --build

# Or run once and exit
docker compose run --rm app
```

4. **Monitor progress**
```bash
# View logs
docker logs firecrawl-uit -f

# Check data
ls data/html    # HTML files
ls data/pdf     # PDF files
ls data/text    # Extracted text
```

## 📁 Project Structure

```
firecrawl-uit-local-advanced/
├── .env                    # Environment configuration
├── .gitignore             # Git ignore rules
├── docker-compose.yml     # Docker compose configuration
├── README.md              # This file
├── data/                  # Output directory (crawled data)
│   ├── html/             # Raw HTML pages
│   ├── pdf/              # Downloaded PDF files
│   ├── docs/             # Office documents (DOCX, XLS, etc.)
│   ├── text/             # Extracted text from files
│   ├── metadata.json     # Complete metadata (JSON)
│   └── metadata.jsonl    # Line-delimited metadata
├── firecrawl/            # Crawler application
│   ├── main.py           # Main crawler script
│   ├── config.yaml       # Base configuration
│   ├── Dockerfile        # Docker image definition
│   └── utils/            # Utility modules
│       ├── downloader.py # File download handler
│       ├── parser.py     # Content parsing
│       ├── ratelimit.py  # Rate limiting
│       └── storage.py    # Data storage
└── logs/                 # Application logs
    └── firecrawl.log     # Main log file
```

## ⚙️ Configuration

### Environment Variables (.env)

The crawler is configured via the `.env` file. Key settings:

#### Crawl Targets
```bash
# Multiple URLs separated by commas
SEED_URLS=https://daa.uit.edu.vn/qui-che-qui-dinh-qui-trinh,https://daa.uit.edu.vn/thongbaochinhquy,...

# URL patterns to include
INCLUDE_PATTERNS=/qui-che,/quy-dinh,/ctdt-khoa,/cqui,/tu-xa

# URL patterns to exclude
EXCLUDE_PATTERNS=/tin-tuc,/news,/blog
```

#### Crawl Behavior
```bash
MAX_DEPTH=3              # How deep to follow links (0-10)
CONCURRENCY=2            # Parallel requests (1-5 recommended)
RATE_LIMIT=1             # Delay between requests in seconds
RESPECT_ROBOTS=false     # robots.txt compliance (false for internal sites)
```

#### Scheduling
```bash
SCHEDULE_HOURS=24        # Hours between crawl runs
RUN_ONCE=false          # Set to true for one-time crawl
ACTIVE_WINDOW=          # Time ranges: "01:00-05:00,12:00-13:00"
WINDOW_TZ=Asia/Ho_Chi_Minh
```

#### Performance
```bash
BANDWIDTH_BPS=0          # Bandwidth limit (0 = unlimited)
JITTER_MAX=0.5          # Random delay variance (seconds)
```

### Current Crawl Targets

The crawler is configured to crawl:

**📚 Training Programs (Chương trình đào tạo)**
- Regular programs: 2012-2025 (13 years)
- Distance learning: 2008, 2013, 2018-2024 (8 years)

**📋 Regulations & Guidelines**
- University regulations
- Training guidelines
- Announcements (regular & distance learning)
- Administrative procedures

See `.env` file for complete list of URLs.

## 🎯 Usage

### Basic Commands

**Start crawler (background)**
```bash
docker compose up -d
```

**View real-time logs**
```bash
docker logs firecrawl-uit -f
```

**Stop crawler**
```bash
docker compose down
```

**Restart crawler**
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
