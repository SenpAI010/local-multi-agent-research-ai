"""
Tools Module: Web operations
"""
import requests
import re
import socket
from urllib.parse import quote_plus, unquote, urljoin, urlparse
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
            fetched = self._safe_get_text(url, max_chars=200_000)
            if not fetched.get("ok"):
                return fetched
            html = str(fetched.get("content", ""))

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

        fetched = self._safe_get_text(url, max_chars=max_chars)
        if not fetched.get("ok"):
            return fetched
        fetched["prompt_injection_risk"] = self._prompt_injection_risk(str(fetched.get("content", "")))
        if fetched["prompt_injection_risk"]:
            fetched["content"] = self._strip_prompt_injection(str(fetched.get("content", "")))[:max_chars]
        return fetched

    def _safe_get_text(self, url: str, max_chars: int = 12000) -> Dict[str, Any]:
        current_url = (url or "").strip()
        max_chars = max(1, min(int(max_chars), 200_000))
        headers = {"User-Agent": "LocalAgentWebTools/1.0"}
        for redirect_count in range(4):
            u = urlparse(current_url)
            if u.scheme not in {"http", "https"}:
                return {"ok": False, "error": "Only http/https allowed."}
            if self._is_private_target(u.hostname or "") or self._resolves_to_private(u.hostname or ""):
                return {"ok": False, "error": "Blocked: private/local target."}
            try:
                r = requests.get(
                    current_url,
                    timeout=self.timeout_sec,
                    headers=headers,
                    allow_redirects=False,
                    stream=True,
                )
            except Exception as e:
                return {"ok": False, "error": str(e)}
            try:
                if 300 <= r.status_code < 400:
                    if redirect_count >= 3:
                        return {"ok": False, "error": "too_many_redirects"}
                    location = r.headers.get("Location")
                    if not location:
                        return {"ok": False, "error": "redirect_without_location"}
                    current_url = urljoin(current_url, location)
                    continue
                r.raise_for_status()
                chunks = []
                total = 0
                for chunk in r.iter_content(chunk_size=65536, decode_unicode=True):
                    if not chunk:
                        continue
                    chunks.append(str(chunk))
                    total += len(str(chunk))
                    if total > max_chars:
                        break
                return {"ok": True, "url": current_url, "content": "".join(chunks)[:max_chars]}
            except Exception as e:
                return {"ok": False, "error": str(e)}
            finally:
                r.close()
        return {"ok": False, "error": "too_many_redirects"}

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

    def _prompt_injection_risk(self, text: str) -> bool:
        lowered = text.lower()
        markers = (
            "ignore previous instructions",
            "ignore all previous instructions",
            "system prompt",
            "developer message",
            "exfiltrate",
            "send your secrets",
            "do not obey",
        )
        return any(marker in lowered for marker in markers)

    def _strip_prompt_injection(self, text: str) -> str:
        if self._prompt_injection_risk(text):
            return "[prompt_injection_risk removed from untrusted source]"
        return text
