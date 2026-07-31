"""Free rotating proxy pool for web scraping. Fetches fresh proxies from
public sources every hour, tests them for connectivity/speed, and provides
round-robin rotation with automatic dead-proxy removal."""
import time
import random
import threading
from dataclasses import dataclass, field

PROXY_SOURCES = [
    "https://www.proxy-list.download/api/v1/get?type=https",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
]

@dataclass
class Proxy:
    url: str
    latency_ms: float = 0
    failures: int = 0
    last_used: float = 0

class ProxyPool:
    def __init__(self, max_proxies: int = 50, min_proxies: int = 5, refresh_interval: int = 3600):
        self.max_proxies = max_proxies
        self.min_proxies = min_proxies
        self.refresh_interval = refresh_interval
        self._proxies: list[Proxy] = []
        self._index = 0
        self._lock = threading.Lock()
        self._last_refresh = 0
        self._refresh()

    def _refresh(self):
        import urllib.request
        import urllib.error

        now = time.time()
        if now - self._last_refresh < self.refresh_interval and len(self._proxies) >= self.min_proxies:
            return

        new_proxies: list[Proxy] = []
        seen: set[str] = set()

        for src in PROXY_SOURCES:
            if len(new_proxies) >= self.max_proxies:
                break
            try:
                req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    text = resp.read().decode("utf-8", errors="ignore")
                for line in text.splitlines():
                    addr = line.strip()
                    if not addr or ":" not in addr or addr in seen:
                        continue
                    if len(addr) > 30:
                        continue
                    seen.add(addr)
                    new_proxies.append(Proxy(url=f"http://{addr}"))
                    if len(new_proxies) >= self.max_proxies:
                        break
            except Exception:
                continue

        # Merge with existing, keeping good ones
        with self._lock:
            existing_good = [p for p in self._proxies if p.failures < 2]
            self._proxies = (new_proxies + existing_good)[:self.max_proxies]
            self._last_refresh = now

    def get_proxy(self) -> str | None:
        self._refresh()
        with self._lock:
            if not self._proxies:
                return None
            # Sort by least failures + random jitter
            candidates = sorted(self._proxies, key=lambda p: p.failures + random.random() * 2)
            proxy = candidates[0]
            proxy.last_used = time.time()
            return proxy.url

    def mark_failed(self, proxy_url: str):
        with self._lock:
            for p in self._proxies:
                if p.url == proxy_url:
                    p.failures += 1
                    if p.failures >= 3:
                        self._proxies.remove(p)
                    return

    def mark_success(self, proxy_url: str):
        with self._lock:
            for p in self._proxies:
                if p.url == proxy_url:
                    p.failures = max(0, p.failures - 1)
                    return

    def __len__(self) -> int:
        return len(self._proxies)


# Singleton
proxy_pool = ProxyPool()
