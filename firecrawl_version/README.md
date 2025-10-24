# UIT Crawler - Firecrawl Self-Hosted# 🔥 UIT Crawler - Firecrawl Self-Hosted Version



> Self-hosted web crawler using Firecrawl stack for UIT website data collection> This version uses **Firecrawl self-hosted** (runs locally) instead of cloud API.



## Architecture## 🆚 Comparison with Custom Crawler



```| Feature | Custom Crawler | Firecrawl Self-Hosted |

┌─────────────────────────────────────────────────────────┐|---------|---------------|----------------------|

│           Firecrawl Self-Hosted Stack                   │| **Complexity** | Simple (1 container) | Complex (5 containers) |

│                                                          │| **Dependencies** | requests, BeautifulSoup | Full Firecrawl stack |

│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐   │| **Cost** | Free | **Free** (no API key) |

│  │   Redis     │  │ PostgreSQL  │  │  Playwright  │   │| **Anti-bot** | Basic (SSL bypass) | Advanced (Playwright) |

│  │   (Queue)   │  │   (Data)    │  │  (Browser)   │   │| **JavaScript rendering** | No | **Yes** (Playwright) |

│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘   │| **Setup** | Quick (2 mins) | Longer (5-10 mins) |

│         │                 │                 │           │| **Resource usage** | 512MB RAM | **2-3GB RAM** |

│         └─────────────┬───┴─────────────────┘           │| **Best for** | Internal sites, low resource | Complex sites, have resources |

│                       ▼                                 │

│              ┌─────────────────┐                        │## 🏗️ Architecture

│              │  Firecrawl API  │                        │

│              │   (Node.js)     │                        │```

│              └────────┬────────┘                        │┌─────────────────────────────────────────────────────────┐

│                       │                                 ││           Firecrawl Self-Hosted Stack                   │

└───────────────────────┼─────────────────────────────────┘│                                                          │

                        │ HTTP (port 3002)│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐   │

                        ▼│  │   Redis     │  │ PostgreSQL  │  │  Playwright  │   │

              ┌─────────────────┐│  │   (Queue)   │  │   (Data)    │  │  (Browser)   │   │

              │  UIT Crawler    ││  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘   │

              │   (Python)      ││         │                 │                 │           │

              └─────────────────┘│         └─────────────┬───┴─────────────────┘           │

```│                       ▼                                 │

│              ┌─────────────────┐                        │

## Features│              │  Firecrawl API  │                        │

│              │   (Node.js)     │                        │

- **Parallel Crawling**: Concurrent processing of multiple seeds│              └────────┬────────┘                        │

- **Checkpoint System**: Auto-recovery from crashes│                       │                                 │

- **Health Check**: Wait for all services before crawling└───────────────────────┼─────────────────────────────────┘

- **Statistics**: Real-time metrics and performance tracking                        │ HTTP (port 3002)

- **Error Categorization**: Structured error logging                        ▼

- **Incremental Crawling**: Skip recently crawled content              ┌─────────────────┐

- **Content Categorization**: Smart folder organization              │  UIT Crawler    │

              │   (Python)      │

## Quick Start              │  Orchestrator   │

              └─────────────────┘

### Prerequisites                        │

                        ▼

- Docker with 4GB+ RAM                  ┌──────────┐

- 8GB+ total system RAM                  │   Data   │

- 10GB+ free disk space                  │ (Output) │

                  └──────────┘

### Setup```



1. Copy environment configuration:## 🚀 Quick Start

```bash

cp .env.example .env### 1. Prerequisites

```

- **Docker** with **4GB+ RAM** allocated

2. Edit `.env` if needed (defaults work):- **8GB+ total system RAM** recommended

```bash- **10GB+ free disk space**

SCHEDULE_HOURS=24

MAX_WORKERS=3### 2. Configure

```

Copy `.env.example` to `.env`:

3. Start services:```bash

```bashcp .env.example .env

docker compose up -d```

```

Edit `.env` (optional - defaults work fine):

First run takes 5-10 minutes to initialize all services.```bash

# No API key needed!

### Monitor ProgressSCHEDULE_HOURS=24

BULL_AUTH_KEY=CHANGEME

```bash```

# Check services

docker compose ps### 3. Run



# View crawler logs```bash

docker logs firecrawl-uit-crawler -fdocker compose up -d

```

# View API logs

docker logs firecrawl-api -f**First run takes 5-10 minutes** to:

```- Pull Firecrawl images (~2GB)

- Start 5 containers

## Configuration- Initialize PostgreSQL database

- Wait for all services to be ready

### Environment Variables

### 4. Monitor

```bash

# SchedulingCheck services status:

SCHEDULE_HOURS=24          # Crawl interval (hours)```bash

RUN_ONCE=false            # Set true for one-time executiondocker compose ps

MAX_WORKERS=3             # Parallel workers```



# URL Configuration (optional, uses config.yaml by default)View logs:

SEED_URLS=url1,url2```bash

INCLUDE_PATTERNS=/path1,/path2# Firecrawl API logs

EXCLUDE_PATTERNS=/news,/blogdocker logs firecrawl-api -f

MAX_DEPTH=3

```# Crawler logs

docker logs firecrawl-uit-crawler -f

### config.yaml

# All logs

```yamldocker compose logs -f

seed_urls:```

  - https://daa.uit.edu.vn/qui-che-qui-dinh-qui-trinh

  - https://daa.uit.edu.vn/thongbaochinhquy### 5. Access Bull Queue UI

  # ... more URLs

Open browser: http://localhost:3002/admin/CHANGEME/queues

max_depth: 3

(Change `CHANGEME` to your `BULL_AUTH_KEY` value)

include_patterns:

  - /qui-dinh## � Resource Requirements

  - /thong-bao

### Firecrawl Self-Hosted:

exclude_patterns:- **RAM**: 2-3GB (5 containers)

  - /news- **CPU**: 2+ cores recommended

  - /blog- **Disk**: 10GB+ for Docker images

```- **Cost**: **$0** (runs locally)



## Output Structure### For UIT use case (~100 pages):

- **Custom crawler**: 512MB RAM, $0

```- **Firecrawl self-hosted**: 2-3GB RAM, $0

data/- **Firecrawl cloud API**: 512MB RAM, $20/month

├── content/

│   ├── daa/## 📊 Service Breakdown

│   │   ├── quy-dinh/

│   │   ├── quy-trinh/| Service | Purpose | RAM | Port |

│   │   ├── thong-bao/|---------|---------|-----|------|

│   │   └── huong-dan/| **api** | Main Firecrawl API | 512MB | 3002 |

│   └── khac/| **playwright-service** | Browser automation | 1GB | 3000 |

├── metadata.json         # All crawled pages metadata| **redis** | Job queue | 256MB | 6379 |

├── metadata.jsonl        # Line-delimited metadata| **postgres** | Database | 512MB | 5432 |

├── crawl_stats.json      # Performance statistics| **crawler** | UIT orchestrator | 256MB | - |

├── checkpoint.json       # Recovery checkpoint| **Total** | | **~2.5GB** | |

└── failed_urls.jsonl     # Failed URL log

```## ⚙️ Configuration



## Resource Requirements### Environment Variables



| Service | RAM | Purpose |```bash

|---------|-----|---------|# Required

| api | 512MB | Firecrawl API |FIRECRAWL_API_KEY=fc-xxx          # Get from firecrawl.dev

| playwright-service | 1GB | Browser automation |

| redis | 256MB | Job queue |# Optional

| postgres | 512MB | Database |SCHEDULE_HOURS=24                  # Crawl every 24 hours

| crawler | 256MB | Orchestrator |RUN_ONCE=false                     # Set true for one-time run

| **Total** | **~2.5GB** | |SEED_URLS=url1,url2,url3          # URLs to crawl

INCLUDE_PATTERNS=/path1,/path2     # Include only these paths

## TroubleshootingEXCLUDE_PATTERNS=/news,/blog       # Exclude these paths

MAX_DEPTH=3                        # Maximum crawl depth

### Services not starting```

```bash

# Check logs## 📁 Output Structure

docker logs firecrawl-api

```

# Restart servicesdata/

docker compose restart├── html/              # Raw HTML files

├── markdown/          # Converted markdown

# Ensure Docker has 4GB+ RAM allocated├── metadata.json      # All metadata

```└── metadata.jsonl     # Line-delimited metadata



### Connection refusedlogs/

- Wait 5-10 minutes for first startup└── firecrawl.log      # Application logs

- Check all services: `docker compose ps````

- Services must show "healthy" status

## ✅ Advantages

### Out of memory

- Increase Docker memory to 4GB+1. **Advanced features**:

- Reduce MAX_WORKERS to 2 or 1   - ✅ JavaScript rendering (Playwright)

- Close other applications   - ✅ Browser automation

   - ✅ Screenshot capture

## Development   - ✅ LLM-ready markdown

   - ✅ Professional UI (Bull Queue)

### Project Structure

2. **No cost**:

```   - ✅ Free forever (no API key)

.   - ✅ All features unlocked

├── main.py              # Main crawler logic   - ✅ No rate limits

├── config.yaml          # Crawl configuration

├── docker-compose.yml   # Service orchestration3. **Full control**:

├── Dockerfile          # Crawler container   - ✅ Runs on your infrastructure

├── .env.example        # Environment template   - ✅ No external dependencies

└── README.md           # Documentation   - ✅ Data stays local

```

## ❌ Disadvantages

### Key Components

1. **Resource intensive**:

- **CrawlStats**: Performance metrics tracking   - ❌ Requires 2-3GB RAM

- **Checkpoint System**: Crash recovery   - ❌ 5 containers to manage

- **Health Check**: Service readiness verification   - ❌ Slower startup (5-10 mins)

- **Parallel Execution**: ThreadPoolExecutor-based crawling

- **Content Categorization**: Smart folder organization2. **Complex setup**:

   - ❌ More moving parts

## License   - ❌ Harder to debug

   - ❌ Need Docker expertise

MIT

3. **Overkill for UIT**:
   - ❌ UIT website is simple
   - ❌ Custom crawler is faster
   - ❌ More maintenance needed

## 🎯 When to Use This Version

✅ **Use Firecrawl Self-Hosted when**:
- Target website has heavy anti-bot
- Need JavaScript rendering
- Have 2-3GB RAM available
- Want professional features (Bull Queue UI)
- Don't want to pay for cloud API

❌ **Use Custom Crawler when**:
- Internal/simple websites (like UIT) ⭐
- Want minimal resource usage (512MB)
- Want simple single-container setup
- Don't need JavaScript rendering
- Prefer lightweight solution

## 🔄 Migration from Custom Crawler

If you want to switch from custom crawler to Firecrawl self-hosted:

```bash
# 1. Stop custom crawler
docker compose -f ../docker-compose.yml down

# 2. Go to firecrawl_version directory
cd firecrawl_version

# 3. Copy .env (no API key needed!)
cp .env.example .env

# 4. Start Firecrawl stack (first time takes 5-10 mins)
docker compose up -d

# 5. Wait for services to be ready
docker compose ps

# 6. Monitor
docker logs firecrawl-uit-crawler -f
```

## 📚 API Documentation

- [Firecrawl API Docs](https://docs.firecrawl.dev)
- [Python SDK](https://docs.firecrawl.dev/sdks/python)
- [Pricing](https://firecrawl.dev/pricing)

## 🆘 Troubleshooting

### Error: Services not starting
```
ERROR: Container firecrawl-api exited with code 1
```
**Solution**: 
- Check Docker has enough RAM (need 4GB+)
- Wait 5-10 minutes for first startup
- Check logs: `docker logs firecrawl-api`

### Error: Connection refused
```
Connection refused to http://api:3002
```
**Solution**: 
- Services still starting, wait longer
- Check all services running: `docker compose ps`
- Restart: `docker compose restart`

### Error: Out of memory
```
OOMKilled or container keeps restarting
```
**Solution**: 
- Increase Docker memory limit to 4GB+
- Close other applications
- Use custom crawler instead (only 512MB)

### Bull Queue UI not accessible
**Solution**: 
- Check if API is running: `docker compose ps`
- Access: http://localhost:3002/admin/CHANGEME/queues
- Change `CHANGEME` to your `BULL_AUTH_KEY`

## 🎓 Learning Resources

- [Firecrawl Self-Hosting Guide](../firecrawl/SELF_HOST.md)
- [Firecrawl Documentation](https://docs.firecrawl.dev)
- [Python SDK Examples](https://github.com/firecrawl/firecrawl-py)
- [Comparison with Custom Crawler](../WHY_CUSTOM_CRAWLER.md)

## 🏆 Recommendation

**For UIT use case**: **Use custom crawler** (uit_crawler/) ⭐
- ✅ Free
- ✅ Simple (1 container)
- ✅ Fast (512MB RAM)
- ✅ Sufficient features
- ✅ No external dependencies

**For complex websites with JS**: **Use Firecrawl self-hosted** (this version)
- ✅ Free (no API key)
- ✅ Advanced anti-bot
- ✅ JavaScript rendering
- ✅ Full control
- ❌ Heavy (2-3GB RAM)
- ❌ Complex (5 containers)

**For convenience**: **Use Firecrawl cloud API**
- ✅ Minimal resources
- ✅ Managed service
- ❌ Costs $20+/month

---

**Made with 🔥 by Firecrawl**
