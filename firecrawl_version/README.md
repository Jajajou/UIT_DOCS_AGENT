# 🔥 UIT Crawler - Firecrawl Self-Hosted Version

> This version uses **Firecrawl self-hosted** (runs locally) instead of cloud API.

## 🆚 Comparison with Custom Crawler

| Feature | Custom Crawler | Firecrawl Self-Hosted |
|---------|---------------|----------------------|
| **Complexity** | Simple (1 container) | Complex (5 containers) |
| **Dependencies** | requests, BeautifulSoup | Full Firecrawl stack |
| **Cost** | Free | **Free** (no API key) |
| **Anti-bot** | Basic (SSL bypass) | Advanced (Playwright) |
| **JavaScript rendering** | No | **Yes** (Playwright) |
| **Setup** | Quick (2 mins) | Longer (5-10 mins) |
| **Resource usage** | 512MB RAM | **2-3GB RAM** |
| **Best for** | Internal sites, low resource | Complex sites, have resources |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│           Firecrawl Self-Hosted Stack                   │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐   │
│  │   Redis     │  │ PostgreSQL  │  │  Playwright  │   │
│  │   (Queue)   │  │   (Data)    │  │  (Browser)   │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘   │
│         │                 │                 │           │
│         └─────────────┬───┴─────────────────┘           │
│                       ▼                                 │
│              ┌─────────────────┐                        │
│              │  Firecrawl API  │                        │
│              │   (Node.js)     │                        │
│              └────────┬────────┘                        │
│                       │                                 │
└───────────────────────┼─────────────────────────────────┘
                        │ HTTP (port 3002)
                        ▼
              ┌─────────────────┐
              │  UIT Crawler    │
              │   (Python)      │
              │  Orchestrator   │
              └─────────────────┘
                        │
                        ▼
                  ┌──────────┐
                  │   Data   │
                  │ (Output) │
                  └──────────┘
```

## 🚀 Quick Start

### 1. Prerequisites

- **Docker** with **4GB+ RAM** allocated
- **8GB+ total system RAM** recommended
- **10GB+ free disk space**

### 2. Configure

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` (optional - defaults work fine):
```bash
# No API key needed!
SCHEDULE_HOURS=24
BULL_AUTH_KEY=CHANGEME
```

### 3. Run

```bash
docker compose up -d
```

**First run takes 5-10 minutes** to:
- Pull Firecrawl images (~2GB)
- Start 5 containers
- Initialize PostgreSQL database
- Wait for all services to be ready

### 4. Monitor

Check services status:
```bash
docker compose ps
```

View logs:
```bash
# Firecrawl API logs
docker logs firecrawl-api -f

# Crawler logs
docker logs firecrawl-uit-crawler -f

# All logs
docker compose logs -f
```

### 5. Access Bull Queue UI

Open browser: http://localhost:3002/admin/CHANGEME/queues

(Change `CHANGEME` to your `BULL_AUTH_KEY` value)

## � Resource Requirements

### Firecrawl Self-Hosted:
- **RAM**: 2-3GB (5 containers)
- **CPU**: 2+ cores recommended
- **Disk**: 10GB+ for Docker images
- **Cost**: **$0** (runs locally)

### For UIT use case (~100 pages):
- **Custom crawler**: 512MB RAM, $0
- **Firecrawl self-hosted**: 2-3GB RAM, $0
- **Firecrawl cloud API**: 512MB RAM, $20/month

## 📊 Service Breakdown

| Service | Purpose | RAM | Port |
|---------|---------|-----|------|
| **api** | Main Firecrawl API | 512MB | 3002 |
| **playwright-service** | Browser automation | 1GB | 3000 |
| **redis** | Job queue | 256MB | 6379 |
| **postgres** | Database | 512MB | 5432 |
| **crawler** | UIT orchestrator | 256MB | - |
| **Total** | | **~2.5GB** | |

## ⚙️ Configuration

### Environment Variables

```bash
# Required
FIRECRAWL_API_KEY=fc-xxx          # Get from firecrawl.dev

# Optional
SCHEDULE_HOURS=24                  # Crawl every 24 hours
RUN_ONCE=false                     # Set true for one-time run
SEED_URLS=url1,url2,url3          # URLs to crawl
INCLUDE_PATTERNS=/path1,/path2     # Include only these paths
EXCLUDE_PATTERNS=/news,/blog       # Exclude these paths
MAX_DEPTH=3                        # Maximum crawl depth
```

## 📁 Output Structure

```
data/
├── html/              # Raw HTML files
├── markdown/          # Converted markdown
├── metadata.json      # All metadata
└── metadata.jsonl     # Line-delimited metadata

logs/
└── firecrawl.log      # Application logs
```

## ✅ Advantages

1. **Advanced features**:
   - ✅ JavaScript rendering (Playwright)
   - ✅ Browser automation
   - ✅ Screenshot capture
   - ✅ LLM-ready markdown
   - ✅ Professional UI (Bull Queue)

2. **No cost**:
   - ✅ Free forever (no API key)
   - ✅ All features unlocked
   - ✅ No rate limits

3. **Full control**:
   - ✅ Runs on your infrastructure
   - ✅ No external dependencies
   - ✅ Data stays local

## ❌ Disadvantages

1. **Resource intensive**:
   - ❌ Requires 2-3GB RAM
   - ❌ 5 containers to manage
   - ❌ Slower startup (5-10 mins)

2. **Complex setup**:
   - ❌ More moving parts
   - ❌ Harder to debug
   - ❌ Need Docker expertise

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
