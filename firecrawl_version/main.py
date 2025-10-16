import os
import json
import logging
import time
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from urllib.parse import urljoin, urlparse
import hashlib

import yaml
from firecrawl import FirecrawlApp
import requests

# ---------------------------
# Configuration
# ---------------------------

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/data"))
LOG_PATH = Path(os.environ.get("LOG_PATH", "/logs/firecrawl.log"))
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config.yaml")

# Self-hosted Firecrawl endpoint (no API key needed)
FIRECRAWL_URL = os.environ.get("FIRECRAWL_URL", "http://api:3002")
SCHEDULE_HOURS = float(os.environ.get("SCHEDULE_HOURS", "24"))
RUN_ONCE = os.environ.get("RUN_ONCE", "false").lower() == "true"

# Output directories
HTML_DIR = OUTPUT_DIR / "html"
MARKDOWN_DIR = OUTPUT_DIR / "markdown"
PDF_DIR = OUTPUT_DIR / "pdf"
DOCX_DIR = OUTPUT_DIR / "docx"
META_JSONL = OUTPUT_DIR / "metadata.jsonl"
META_JSON = OUTPUT_DIR / "metadata.json"

# ---------------------------
# Logging
# ---------------------------

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("firecrawl-uit")

# ---------------------------
# Helper Functions
# ---------------------------

def load_config() -> Dict[str, Any]:
    """Load configuration from YAML and environment variables."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    
    def env_list(name: str, default: List[str]) -> List[str]:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return [x.strip() for x in raw.split(",") if x.strip()]
    
    cfg["seed_urls"] = env_list("SEED_URLS", cfg.get("seed_urls", []))
    cfg["include_patterns"] = env_list("INCLUDE_PATTERNS", cfg.get("include_patterns", []))
    cfg["exclude_patterns"] = env_list("EXCLUDE_PATTERNS", cfg.get("exclude_patterns", []))
    cfg["max_depth"] = int(os.environ.get("MAX_DEPTH", cfg.get("max_depth", 3)))
    
    return cfg

def ensure_dirs():
    """Create output directories."""
    for directory in [OUTPUT_DIR, HTML_DIR, MARKDOWN_DIR, PDF_DIR, DOCX_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

def append_jsonl(obj: Dict[str, Any]):
    """Append object to JSONL file."""
    with open(META_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def rebuild_metadata_json():
    """Rebuild metadata.json from JSONL."""
    items = []
    if META_JSONL.exists():
        with open(META_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception as e:
                    logger.warning(f"Failed to parse JSON line: {e}")
    
    with open(META_JSON, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

def find_download_links(html: str, base_url: str) -> List[str]:
    """Extract PDF/DOCX download links from HTML."""
    if not html:
        return []
    
    links = []
    # Find links to PDF, DOCX, DOC, XLS, XLSX
    patterns = [
        r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
        r'href=["\']([^"\']*\.docx?[^"\']*)["\']',
        r'href=["\']([^"\']*\.xlsx?[^"\']*)["\']',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        for match in matches:
            # Convert relative URL to absolute
            full_url = urljoin(base_url, match)
            if full_url not in links:
                links.append(full_url)
    
    return links

def download_file(url: str, output_dir: Path) -> bool:
    """Download a file from URL."""
    try:
        # Generate safe filename using hash
        parsed = urlparse(url)
        filename = parsed.path.split('/')[-1]
        if not filename or len(filename) > 200:
            # Use hash if filename too long
            url_hash = hashlib.sha1(url.encode()).hexdigest()[:8]
            ext = url.split('.')[-1].lower() if '.' in url else 'bin'
            filename = f"{url_hash}.{ext}"
        
        output_path = output_dir / filename
        
        # Skip if already exists
        if output_path.exists():
            logger.debug(f"File already exists: {filename}")
            return True
        
        # Download with streaming
        response = requests.get(url, stream=True, timeout=30, verify=False)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(f"Downloaded: {filename} ({size_mb:.2f} MB)")
        
        # Save metadata
        metadata = {
            "title": filename,
            "url": url,
            "type": "file",
            "file_path": str(output_path),
            "size_mb": round(size_mb, 2),
            "date": datetime.now().isoformat(),
        }
        append_jsonl(metadata)
        
        return True
    
    except Exception as e:
        logger.warning(f"Failed to download {url}: {e}")
        return False

def save_content(url: str, data: Dict[str, Any]):
    """Save crawled content to files."""
    # Generate safe filename
    safe_name = url.replace("https://", "").replace("http://", "")
    safe_name = safe_name.replace("/", "_").replace(":", "_")[:200]
    
    # Save HTML if available
    if data.get("html"):
        html_file = HTML_DIR / f"{safe_name}.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(data["html"])
        logger.info(f"Saved HTML: {html_file.name}")
        
        # Find and download PDF/DOCX links
        download_links = find_download_links(data["html"], url)
        for link in download_links:
            if link.lower().endswith('.pdf'):
                download_file(link, PDF_DIR)
            elif link.lower().endswith(('.doc', '.docx')):
                download_file(link, DOCX_DIR)
    
    # Save Markdown if available
    if data.get("markdown"):
        md_file = MARKDOWN_DIR / f"{safe_name}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(data["markdown"])
        logger.info(f"Saved Markdown: {md_file.name}")
    
    # Save metadata
    metadata = {
        "title": data.get("metadata", {}).get("title", ""),
        "url": url,
        "type": "html",
        "content": data.get("markdown", data.get("text", ""))[:10000],
        "source_url": data.get("metadata", {}).get("sourceURL", url),
        "status_code": data.get("metadata", {}).get("statusCode", 200),
        "date": datetime.now().isoformat(),
    }
    append_jsonl(metadata)

# ---------------------------
# Firecrawl Crawler
# ---------------------------

def crawl_with_firecrawl(app: FirecrawlApp, seed_urls: List[str], cfg: Dict[str, Any]):
    """
    Crawl websites using Firecrawl API.
    
    Args:
        app: FirecrawlApp instance
        seed_urls: List of URLs to crawl
        cfg: Configuration dictionary
    """
    for seed_url in seed_urls:
        try:
            logger.info(f"Starting crawl for: {seed_url}")
            
            # Prepare crawl parameters
            crawl_params = {
                "limit": 500,  # Max pages to crawl (increased from 100)
                "maxDepth": cfg.get("max_depth", 3),  # Follow links up to 3 levels
                "scrapeOptions": {
                    "formats": ["markdown", "html"],
                    "waitFor": 1000,  # Wait 1 second after page load
                }
            }
            
            # Add include/exclude patterns if specified
            if cfg.get("include_patterns"):
                crawl_params["includePaths"] = cfg["include_patterns"]
            if cfg.get("exclude_patterns"):
                crawl_params["excludePaths"] = cfg["exclude_patterns"]
            
            # Start crawl (async)
            crawl_result = app.crawl_url(seed_url, params=crawl_params, poll_interval=5)
            
            if crawl_result.get("success"):
                data = crawl_result.get("data", [])
                logger.info(f"Crawled {len(data)} pages from {seed_url}")
                
                # Process each page
                for page in data:
                    try:
                        save_content(page.get("metadata", {}).get("sourceURL", seed_url), page)
                    except Exception as e:
                        logger.error(f"Failed to save page: {e}")
            else:
                logger.error(f"Crawl failed for {seed_url}: {crawl_result.get('error')}")
        
        except Exception as e:
            logger.error(f"Error crawling {seed_url}: {e}")
        
        # Rate limiting between seeds
        time.sleep(2)

def scrape_with_firecrawl(app: FirecrawlApp, urls: List[str]):
    """
    Scrape individual URLs using Firecrawl API.
    
    Args:
        app: FirecrawlApp instance
        urls: List of URLs to scrape
    """
    for url in urls:
        try:
            logger.info(f"Scraping: {url}")
            
            # Scrape single page
            scrape_result = app.scrape_url(url, params={
                "formats": ["markdown", "html"],
            })
            
            if scrape_result.get("success"):
                save_content(url, scrape_result)
            else:
                logger.error(f"Scrape failed for {url}")
        
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
        
        time.sleep(1)

# ---------------------------
# Main Crawl Job
# ---------------------------

def crawl_once():
    """Run one crawl cycle."""
    cfg = load_config()
    ensure_dirs()
    
    try:
        # Initialize Firecrawl (self-hosted, no API key needed)
        app = FirecrawlApp(api_url=FIRECRAWL_URL)
        logger.info(f"Connected to Firecrawl at {FIRECRAWL_URL}")
        
        seed_urls = cfg.get("seed_urls", [])
        if not seed_urls:
            logger.warning("No seed URLs configured")
            return
        
        # Crawl websites
        crawl_with_firecrawl(app, seed_urls, cfg)
        
        # Rebuild metadata JSON
        rebuild_metadata_json()
        logger.info(f"Rebuilt {META_JSON}")
    
    except Exception as e:
        logger.error(f"Crawl failed: {e}")

# ---------------------------
# Main Entry Point
# ---------------------------

if __name__ == "__main__":
    logger.info("=== UIT crawler (Firecrawl Self-Hosted) started ===")
    logger.info(f"Firecrawl endpoint: {FIRECRAWL_URL}")
    
    # Wait for Firecrawl services to be ready
    logger.info("Waiting for Firecrawl services to start...")
    time.sleep(10)
    
    # Run initial crawl
    crawl_once()
    
    if RUN_ONCE:
        logger.info("Run-once complete. Exiting.")
    else:
        # Scheduled runs
        hours = max(SCHEDULE_HOURS, 1)
        while True:
            logger.info(f"=== Next crawl in {hours} hours ===")
            try:
                time.sleep(hours * 3600)
                crawl_once()
            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                break
            except Exception as e:
                logger.error(f"Scheduled crawl failed: {e}")
    
    logger.info("=== UIT crawler stopped ===")
