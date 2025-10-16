import os
import re
import json
import time
import logging
import random
from collections import deque, defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin, urldefrag

import requests
import yaml
from bs4 import BeautifulSoup
from urllib import robotparser
import urllib3

# Disable SSL warnings for internal domains
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from utils.downloader import download_file, url_to_safe_path
from utils.parser import (
    extract_text_from_pdf,
    extract_text_from_docx,
    clean_html_to_text,
    find_download_links,
)
from utils.storage import (
    ensure_dirs,
    append_jsonl,
    rebuild_metadata_json,
)
from utils.ratelimit import sleep_for_bandwidth, jitter_delay

# ---------------------------
# Config & ENV
# ---------------------------

DEF_UA = os.environ.get("CRAWL_USER_AGENT", "firecrawl-uit-bot/1.0 (+https://uit.edu.vn)")
DEF_HEADERS = {"User-Agent": DEF_UA}

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/data")
LOG_PATH = os.environ.get("LOG_PATH", "/logs/firecrawl.log")
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config.yaml")

USE_FIRECRAWL = os.environ.get("USE_FIRECRAWL", "false").lower() == "true"
RESPECT_ROBOTS = os.environ.get("RESPECT_ROBOTS", "true").lower() == "true"

SCHEDULE_HOURS = float(os.environ.get("SCHEDULE_HOURS", "24"))
RUN_ONCE = os.environ.get("RUN_ONCE", "false").lower() == "true"

ACTIVE_WINDOW = os.environ.get("ACTIVE_WINDOW", "").strip()  # "HH:MM-HH:MM[,HH:MM-HH:MM]"
WINDOW_TZ = os.environ.get("WINDOW_TZ", "Asia/Ho_Chi_Minh")

# Folders
HTML_DIR = os.path.join(OUTPUT_DIR, "html")
PDF_DIR = os.path.join(OUTPUT_DIR, "pdf")
DOCS_DIR = os.path.join(OUTPUT_DIR, "docs")
TEXT_DIR = os.path.join(OUTPUT_DIR, "text")
META_JSONL = os.path.join(OUTPUT_DIR, "metadata.jsonl")
META_JSON = os.path.join(OUTPUT_DIR, "metadata.json")

# ---------------------------
# Logging
# ---------------------------

os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
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
# Windowed scheduling
# ---------------------------

def _parse_ranges(spec: str):
    ranges = []
    if not spec:
        return ranges
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            a, b = part.split("-")
            ah, am = [int(x) for x in a.split(":")]
            bh, bm = [int(x) for x in b.split(":")]
            ranges.append(((ah, am), (bh, bm)))
        except Exception:
            logger.warning("Bad ACTIVE_WINDOW part ignored: %s", part)
    return ranges

_ACTIVE_RANGES = _parse_ranges(ACTIVE_WINDOW)

def _now_local():
    try:
        if ZoneInfo and WINDOW_TZ:
            return datetime.now(ZoneInfo(WINDOW_TZ))
    except Exception:
        pass
    return datetime.now()

def _time_in_ranges(dt: datetime, ranges):
    if not ranges:
        return True  # no restriction
    tmins = dt.hour * 60 + dt.minute
    for (ah, am), (bh, bm) in ranges:
        a = ah * 60 + am
        b = bh * 60 + bm
        if a <= b:
            if a <= tmins <= b:
                return True
        else:
            # overnight window (e.g., 22:00-02:00)
            if tmins >= a or tmins <= b:
                return True
    return False

def _seconds_until_next_window(dt: datetime, ranges):
    # Find minimal seconds until we enter any window
    if not ranges:
        return 0
    tmins = dt.hour * 60 + dt.minute
    candidates = []
    for (ah, am), (bh, bm) in ranges:
        a = ah * 60 + am
        b = bh * 60 + bm
        if a <= b:
            if tmins <= a:
                delta = (a - tmins) * 60 - dt.second
            else:
                delta = ((24*60 - tmins) + a) * 60 - dt.second
        else:
            # overnight window starts at 'a' and goes past midnight
            if tmins <= a and tmins > b:
                delta = (a - tmins) * 60 - dt.second
            else:
                delta = 0  # we're already within overnight window
        if delta >= 0:
            candidates.append(delta)
    if not candidates:
        return 0
    return min(candidates)

# ---------------------------
# Robots.txt support
# ---------------------------

class RobotsCache:
    def __init__(self, user_agent: str):
        self.user_agent = user_agent
        self.cache = {}

    def get(self, url: str):
        domain = urlparse(url).netloc
        if domain in self.cache:
            return self.cache[domain]
        rp = robotparser.RobotFileParser()
        robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
        try:
            rp.set_url(robots_url)
            rp.read()
            crawl_delay = rp.crawl_delay(self.user_agent) or rp.crawl_delay("*")
            self.cache[domain] = (rp, crawl_delay if crawl_delay else 0.0)
            logger.info("Robots fetched for %s (crawl-delay=%s)", domain, self.cache[domain][1])
        except Exception as e:
            logger.warning("Robots fetch failed for %s: %s", domain, e)
            self.cache[domain] = (None, 0.0)
        return self.cache[domain]

ROBOTS = RobotsCache(DEF_UA)

def allowed_by_robots(target_url: str):
    if not RESPECT_ROBOTS:
        return True
    rp, _ = ROBOTS.get(target_url)
    if rp is None:
        return True
    try:
        return rp.can_fetch(DEF_UA, target_url)
    except Exception:
        return True

def robots_crawl_delay_for(url: str) -> float:
    if not RESPECT_ROBOTS:
        return 0.0
    _, delay = ROBOTS.get(url)
    try:
        return float(delay or 0.0)
    except Exception:
        return 0.0

# ---------------------------
# Helpers
# ---------------------------

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    def env_list(name, default):
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return [x.strip() for x in raw.split(",") if x.strip()]

    cfg["seed_urls"] = env_list("SEED_URLS", cfg.get("seed_urls", []))
    cfg["include_patterns"] = env_list("INCLUDE_PATTERNS", cfg.get("include_patterns", []))
    cfg["exclude_patterns"] = env_list("EXCLUDE_PATTERNS", cfg.get("exclude_patterns", []))

    cfg["max_depth"] = int(os.environ.get("MAX_DEPTH", cfg.get("max_depth", 3)))
    cfg["concurrency"] = int(os.environ.get("CONCURRENCY", cfg.get("concurrency", 2)))
    cfg["rate_limit"] = float(os.environ.get("RATE_LIMIT", cfg.get("rate_limit", 1)))
    cfg["download_files"] = os.environ.get("DOWNLOAD_FILES", str(cfg.get("download_files", True))).lower() == "true"

    cfg["output_dir"] = os.environ.get("OUTPUT_DIR", cfg.get("output_dir", OUTPUT_DIR))
    return cfg

def normalize(u: str):
    u, _ = urldefrag(u)
    return u

def should_visit(target_url: str, include_patterns, exclude_patterns, seed_domain: str):
    try:
        pu = urlparse(target_url)
        if not pu.scheme.startswith("http"):
            return False
        if pu.netloc != seed_domain:
            return False
        path = pu.path or "/"
        if include_patterns and not any(p in path for p in include_patterns):
            return False
        if any(p in path for p in (exclude_patterns or [])):
            return False
        if not allowed_by_robots(target_url):
            logger.info("[ROBOTS] Disallow -> %s", target_url)
            return False
        return True
    except Exception:
        return False

def save_html(url: str, html: str):
    fname = url_to_safe_path(url, suffix=",") + ".html"
    fpath = os.path.join(HTML_DIR, fname)
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(html)
    return fpath

def process_html_page(url: str, html: str, source_domain: str, cfg: dict):
    saved_html_path = save_html(url, html)
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "").strip()
    text_content = clean_html_to_text(soup)

    page_meta = {
        "title": title,
        "url": url,
        "type": "html",
        "content": text_content,
        "download_path": saved_html_path or "",
        "date": "",
        "source": source_domain,
    }
    append_jsonl(META_JSONL, page_meta)

    if cfg.get("download_files", True):
        links = find_download_links(html)
        for link in links:
            try:
                file_url = urljoin(url, link)
                if RESPECT_ROBOTS and not allowed_by_robots(file_url):
                    logger.info("[ROBOTS] Disallow file -> %s", file_url)
                    continue
                saved_path = download_file(file_url, PDF_DIR, DOCS_DIR)
                ftype = saved_path.split(".")[-1].lower()

                extracted_text = ""
                ct_path = os.path.join(TEXT_DIR, url_to_safe_path(file_url) + ".txt")
                os.makedirs(os.path.dirname(ct_path), exist_ok=True)

                if ftype == "pdf":
                    try:
                        extracted_text = extract_text_from_pdf(saved_path)
                    except Exception as e:
                        logger.warning(f"PDF text extraction failed: {e}")
                elif ftype in ("docx",):
                    try:
                        extracted_text = extract_text_from_docx(saved_path)
                    except Exception as e:
                        logger.warning(f"DOCX text extraction failed: {e}")
                elif ftype in ("txt",):
                    try:
                        with open(saved_path, "r", encoding="utf-8", errors="ignore") as f:
                            extracted_text = f.read()
                    except Exception:
                        pass

                if extracted_text:
                    with open(ct_path, "w", encoding="utf-8") as f:
                        f.write(extracted_text)

                doc_meta = {
                    "title": os.path.basename(saved_path),
                    "url": file_url,
                    "type": ftype,
                    "content": extracted_text[:200000],
                    "download_path": saved_path,
                    "date": "",
                    "source": source_domain,
                }
                append_jsonl(META_JSONL, doc_meta)
                logger.info(f"Saved file: {saved_path}")
            except Exception as e:
                logger.warning(f"Failed file: {link} — {e}")

# ---------------------------
# Local BFS with polite pacing & backoff
# ---------------------------

def local_bfs_crawl(seed_url: str, cfg: dict):
    seed_url = normalize(seed_url)
    seed_domain = urlparse(seed_url).netloc
    include_patterns = cfg.get("include_patterns", [])
    exclude_patterns = cfg.get("exclude_patterns", [])
    max_depth = cfg.get("max_depth", 3)
    base_delay = float(cfg.get("rate_limit", 1))

    q = deque()
    q.append((seed_url, 0))
    seen = set([seed_url])

    per_host_backoff = defaultdict(float)  # seconds
    per_host_delay = defaultdict(float)    # include robots crawl-delay if present

    while q:
        # Respect active window before each fetch
        now = _now_local()
        if not _time_in_ranges(now, _ACTIVE_RANGES):
            sleep_s = max(_seconds_until_next_window(now, _ACTIVE_RANGES), 60)
            logger.info("[WINDOW] Outside ACTIVE_WINDOW, sleeping %ss", sleep_s)
            try:
                time.sleep(sleep_s)
            except KeyboardInterrupt:
                return

        url, d = q.popleft()
        host = urlparse(url).netloc

        # Compute effective delay: base + robots + backoff + jitter
        robots_delay = robots_crawl_delay_for(url)
        eff_delay = max(base_delay, robots_delay, per_host_delay[host], per_host_backoff[host])
        eff_delay = jitter_delay(eff_delay)
        if eff_delay > 0:
            time.sleep(eff_delay)

        try:
            logger.info(f"[LOCAL] Fetch ({d}/{max_depth}): {url}")
            r = requests.get(url, headers=DEF_HEADERS, timeout=30, verify=False)
            status = r.status_code

            # Backoff handling for 429/503-ish
            if status in (429, 503):
                retry_after = r.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    per_host_backoff[host] = max(per_host_backoff[host], float(retry_after))
                else:
                    per_host_backoff[host] = min(max(5.0, per_host_backoff[host] * 2 or 5.0), 120.0)
                logger.warning("[BACKOFF] %s -> backoff=%ss", status, per_host_backoff[host])
                # re-enqueue and continue
                q.appendleft((url, d))
                continue
            else:
                # success or other: decay backoff
                per_host_backoff[host] = max(per_host_backoff[host] * 0.5 - 1.0, 0.0)

            ctype = (r.headers.get("Content-Type") or "").lower()
            content = r.content or b""
            # Account bandwidth for HTML bodies
            sleep_for_bandwidth(len(content))

            if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
                logger.info(f"[LOCAL] Skip non-HTML: {url} ({ctype})")
                continue

            html = content.decode(r.apparent_encoding or "utf-8", errors="ignore")
            process_html_page(url, html, seed_domain, cfg)

            if d < max_depth:
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    nxt = urljoin(url, a["href"].strip())
                    nxt = normalize(nxt)
                    if nxt in seen:
                        continue
                    if should_visit(nxt, include_patterns, exclude_patterns, seed_domain):
                        seen.add(nxt)
                        q.append((nxt, d + 1))
        except Exception as e:
            logger.warning(f"[LOCAL] Failed {url}: {e}")
        # loop continues

# ---------------------------
# Main crawl job
# ---------------------------

def crawl_once():
    cfg = load_config()
    ensure_dirs([OUTPUT_DIR, HTML_DIR, PDF_DIR, DOCS_DIR, TEXT_DIR])

    if USE_FIRECRAWL:
        logger.error("USE_FIRECRAWL=true is not supported in this local-advanced build.")
        return
    else:
        for seed in cfg.get("seed_urls", []):
            try:
                local_bfs_crawl(seed, cfg)
            except Exception as e:
                logger.error(f"Local crawl error for seed {seed}: {e}")

    try:
        rebuild_metadata_json(META_JSONL, META_JSON)
        logger.info(f"Rebuilt {META_JSON}")
    except Exception as e:
        logger.warning(f"Failed to rebuild metadata.json: {e}")

if __name__ == "__main__":
    logger.info("=== UIT crawler (local, robots-aware) started ===")
    crawl_once()

    if RUN_ONCE:
        logger.info("Run-once complete. Exiting.")
    else:
        hours = max(SCHEDULE_HOURS, 1)
        while True:
            # Sleep until next run start, but honor ACTIVE_WINDOW: start at the next window open if set
            if _ACTIVE_RANGES:
                now = _now_local()
                if not _time_in_ranges(now, _ACTIVE_RANGES):
                    wait = max(_seconds_until_next_window(now, _ACTIVE_RANGES), 60)
                    logger.info("[WINDOW] Waiting %ss for next ACTIVE_WINDOW to start...", wait)
                    try:
                        time.sleep(wait)
                    except KeyboardInterrupt:
                        break
            logger.info("=== Scheduled run ===")
            try:
                crawl_once()
            except Exception as e:
                logger.error(f"Scheduled crawl failed: {e}")
            try:
                time.sleep(hours * 3600)
            except KeyboardInterrupt:
                break

    logger.info("=== UIT crawler stopped ===")
