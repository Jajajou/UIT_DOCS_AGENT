# 🔥 UIT Documentation Crawler

> **Local web crawler** for UIT (University of Information Technology) documentation website with smart crawling features, SSL bypass for internal networks, and comprehensive data extraction.

[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📋 Project Structure

```
uit_firecrawl_new/
├── uit_crawler/           # Custom UIT crawler (standalone)
│   ├── main.py           # Main crawler script
│   ├── config.yaml       # Base configuration
│   ├── Dockerfile        # Docker image
│   └── utils/            # Utility modules
│       ├── downloader.py # File download handler
│       ├── parser.py     # Content parsing
│       ├── ratelimit.py  # Rate limiting
│       └── storage.py    # Data storage
├── firecrawl/            # Firecrawl submodule (reference only)
├── data/                 # Output directory (crawled data)
│   ├── html/            # Raw HTML pages
│   ├── pdf/             # Downloaded PDF files
│   ├── docs/            # Office documents
│   ├── text/            # Extracted text
│   ├── metadata.json    # Complete metadata
│   └── metadata.jsonl   # Line-delimited metadata
├── logs/                # Application logs
├── .env                 # Environment configuration
├── docker-compose.yml   # Docker orchestration
└── README.md            # This file
```

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
- 🌐 **Host network mode** - Access internal UIT servers

## 🚀 Quick Start

### Prerequisites
- Docker Desktop installed and running
- Git (for cloning the repository)
- Access to UIT internal network (for internal URLs)

### Installation

1. **Clone the repository with submodules**
```bash
git clone --recurse-submodules https://github.com/Jajajou/UIT_DOCS_AGENT.git
cd UIT_DOCS_AGENT
```

If you already cloned without submodules:
```bash
git submodule update --init --recursive
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

## 🔧 Architecture

### Custom Crawler vs Firecrawl Submodule

This project uses a **hybrid approach**:

- **`uit_crawler/`** - Custom standalone crawler specifically designed for UIT documentation
  - Optimized for UIT's website structure
  - SSL bypass for internal network
  - Custom rate limiting and backoff logic
  - Runs independently in Docker

- **`firecrawl/`** - Official Firecrawl submodule (reference only)
  - Contains the full Firecrawl stack (API, Redis, Postgres, Playwright)
  - Not used in the current implementation
  - Kept as reference for potential future integration

### Why This Approach?

1. **Simplicity** - Custom crawler is lightweight and focused
2. **Independence** - No external dependencies or services required
3. **Flexibility** - Easy to customize for UIT's specific needs
4. **Future-proof** - Firecrawl submodule available if needed

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

**3. Submodule not loaded**
```bash
# Initialize and update submodules
git submodule update --init --recursive
```

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

## 📝 Development

### Local Development (without Docker)

```bash
cd uit_crawler

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows

# Install dependencies
pip install requests beautifulsoup4 pyyaml pdfminer.six python-docx lxml

# Run crawler
python main.py
```

### Customizing the Crawler

Edit files in `uit_crawler/`:
- `main.py` - Core crawling logic
- `utils/parser.py` - HTML/PDF parsing
- `utils/downloader.py` - File download logic
- `utils/ratelimit.py` - Rate limiting behavior
- `config.yaml` - Default configuration

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- Built for UIT (University of Information Technology)
- Inspired by [Firecrawl](https://github.com/firecrawl/firecrawl)
- Designed for educational documentation archival

---

**Made with ❤️ for UIT Community**
