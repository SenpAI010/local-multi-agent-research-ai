"""
Tools Module: Web operations
"""
import requests
import re
import socket
from urllib.parse import quote_plus, unquote, urlparse
from typing import Any, Dict, Optional
import ipaddress

class WebTools:
    """
    Tools für Web-Operationen.
    - web_search (DuckDuckGo)
    - web_fetch
    """

    def __init__(self, timeout_sec: int = 15):
        self.timeout_sec = timeout_sec

    def web_search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Sucht im Web (DuckDuckGo Lite)."""
        max_results = max(1, min(int(max_results), 10))
        q = query.strip()
        
        if not q:
            return {"ok": False, "error": "Empty query."}

        url = "https://lite.duckduckgo.com/lite/?q=" + quote_plus(q)
        
        try:
            r = requests.get(url, timeout=self.timeout_sec, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            html = r.text

            links = []
            for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S):
                href = m.group(1)
                title = re.sub(r"<.*?>", "", m.group(2)).strip()
                
                if not title:
                    continue
                
                if "duckduckgo.com/l/?" in href and "uddg=" in href:
                    m2 = re.search(r"uddg=([^&]+)", href)
                    if m2:
                        href = unquote(m2.group(1))
                
                if href.startswith("http"):
                    links.append({"title": title[:120], "url": href})
                
                if len(links) >= max_results:
                    break

            return {"ok": True, "query": q, "results": links}
        
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def web_fetch(self, url: str, max_chars: int = 12000) -> Dict[str, Any]:
        """Holt eine URL (localhost-safe)."""
        url = (url or "").strip()
        
        if not url:
            return {"ok": False, "error": "Empty url."}

        u = urlparse(url)
        
        if u.scheme not in {"http", "https"}:
            return {"ok": False, "error": "Only http/https allowed."}
        
        # Verhindere private Targets
        if self._is_private_target(u.hostname or ""):
            return {"ok": False, "error": "Blocked: private/local target."}

        if self._resolves_to_private(u.hostname or ""):
            return {"ok": False, "error": "Blocked: hostname resolves to private/local IP."}

        try:
            r = requests.get(url, timeout=self.timeout_sec, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            text = r.text
            return {"ok": True, "url": url, "content": text[:max_chars]}
        
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _is_private_target(self, host: str) -> bool:
        """Prüft, ob Host privat/lokal ist."""
        host = (host or "").strip().lower()
        
        if host in {"localhost"} or host.endswith(".local"):
            return True
        
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
        except ValueError:
            return False

    def _resolves_to_private(self, host: str) -> bool:
        """Resolve hostname and block private/local/link-local targets."""
        host = (host or "").strip()
        if not host:
            return True
        try:
            infos = socket.getaddrinfo(host, None)
        except Exception:
            return True

        for info in infos:
            ip_text = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_text)
            except ValueError:
                return True
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return True
        return False
