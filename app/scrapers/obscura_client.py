"""Lightweight Python wrapper around Obscura — the Rust headless browser.
Provides two modes:
  - One-shot: obscura fetch <url> --dump text --stealth
  - CDP: obscura serve --port <port> (for Puppeteer/Playwright)
"""
import subprocess
import tempfile
import os
import shutil
import json
import time
import platform
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ObscuraResult:
    url: str
    text: str
    html: str | None = None
    links: list[str] | None = None
    elapsed_ms: float = 0

class ObscuraClient:
    """Minimal Python wrapper that calls the obscura binary via subprocess.
    Falls back to obscura-node (npm) if the binary isn't installed."""

    def __init__(self, binary_path: str | None = None):
        self.bin = binary_path or self._find_binary()
        self._available = self._check_available()

    def _find_binary(self) -> str:
        return shutil.which("obscura") or "obscura"

    def _check_available(self) -> bool:
        try:
            result = subprocess.run([self.bin, "--version"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @property
    def available(self) -> bool:
        return self._available

    def fetch(self, url: str, *, stealth: bool = True, dump: str = "text",
              timeout: int = 30, wait: int = 3, selector: str | None = None) -> ObscuraResult:
        if not self._available:
            return self._node_fallback(url, stealth, dump, timeout)

        start = time.time()
        args = [self.bin, "fetch", url, "--dump", dump, "--timeout", str(timeout), "--wait", str(wait)]
        if stealth:
            args.append("--stealth")
        if selector:
            args += ["--selector", selector]

        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 10)
        elapsed = (time.time() - start) * 1000

        if result.returncode != 0:
            raise RuntimeError(f"Obscura fetch failed: {result.stderr}")

        stdout = result.stdout.strip()
        html = stdout if dump == "html" else None
        text = stdout if dump != "html" else stdout
        return ObscuraResult(url=url, html=html, text=text, elapsed_ms=elapsed)

    def fetch_html(self, url: str, stealth: bool = True, timeout: int = 30) -> ObscuraResult:
        return self.fetch(url, stealth=stealth, dump="html", timeout=timeout)

    def fetch_links(self, url: str, stealth: bool = True, timeout: int = 30) -> list[str]:
        res = self.fetch(url, stealth=stealth, dump="links", timeout=timeout)
        return [l.strip() for l in res.text.split("\n") if l.strip()]

    def serve(self, port: int = 9222, stealth: bool = True) -> subprocess.Popen:
        """Start a persistent CDP server. Returns the process handle.
        Use with Puppeteer/Playwright via CDP WebSocket: ws://127.0.0.1:{port}"""
        args = [self.bin, "serve", "--port", str(port)]
        if stealth:
            args.append("--stealth")
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _node_fallback(self, url: str, stealth: bool, dump: str, timeout: int) -> ObscuraResult:
        """Fall back to obscura-node (npm wrapper) if the binary isn't installed."""
        try:
            result = subprocess.run(
                ["npx", "obscura-node", "fetch", url, "--dump", dump] +
                (["--stealth"] if stealth else []),
                capture_output=True, text=True, timeout=timeout + 10
            )
            return ObscuraResult(url=url, text=result.stdout.strip())
        except Exception as e:
            raise RuntimeError(
                "Obscura binary not found. Install it:\n"
                "  npm install -g obscura-node\n"
                "Or download the binary from https://github.com/h4ckf0r0day/obscura/releases"
            ) from e


# Singleton
obscura = ObscuraClient()
