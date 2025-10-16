import os, time, random

_BPS = int(os.environ.get("BANDWIDTH_BPS", "0") or "0")
_JITTER_MAX = float(os.environ.get("JITTER_MAX", "0.5") or "0")

class _TokenBucket:
    def __init__(self, rate_bytes_per_sec: int):
        self.rate = max(int(rate_bytes_per_sec), 0)
        self.tokens = float(self.rate)
        self.last = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last
        self.last = now
        self.tokens = min(self.rate, self.tokens + elapsed * self.rate)

    def consume(self, nbytes: int):
        if self.rate <= 0:
            return  # unlimited
        self._refill()
        need = float(nbytes)
        while self.tokens < need:
            # sleep until enough tokens refilled
            to_sleep = (need - self.tokens) / self.rate
            time.sleep(min(max(to_sleep, 0.0), 2.0))  # nap in small chunks
            self._refill()
        self.tokens -= need

_BUCKET = _TokenBucket(_BPS)

def sleep_for_bandwidth(nbytes: int):
    """Block to keep average throughput under BANDWIDTH_BPS."""
    try:
        _BUCKET.consume(int(nbytes))
    except Exception:
        pass

def jitter_delay(base_seconds: float) -> float:
    j = random.uniform(0.0, max(float(os.environ.get("JITTER_MAX", _JITTER_MAX)), 0.0))
    return max(base_seconds, 0.0) + j
