"""Safe read-only web access for research literature retrieval."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_ALLOWLIST = [
    "arxiv.org",
    "export.arxiv.org",
    "claymath.org",
    "www.claymath.org",
    "wikipedia.org",
    "en.wikipedia.org",
    "mathworld.wolfram.com",
    "zbmath.org",
    "doi.org",
    "api.crossref.org",
    "crossref.org",
    "semanticscholar.org",
    "api.semanticscholar.org",
]

PROMPT_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "system prompt",
    "developer message",
    "run this command",
    "execute this code",
    "exfiltrate",
]


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_") or "web_item"


class WebResearchProxy:
    """Restricted research-only web proxy.

    The proxy performs only GET/HEAD requests, never uses cookies, blocks private
    network targets, and stores all fetched artifacts as untrusted research input.
    """

    def __init__(self, project_dir: Path, enabled: bool = False, max_bytes: int = 25 * 1024 * 1024):
        self.project_dir = Path(project_dir)
        self.enabled = enabled
        self.max_bytes = max_bytes
        self.cache_dir = self.project_dir / "web_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.project_dir / "web_config.json"
        self.audit_path = self.project_dir / "web_audit.jsonl"

    def config(self) -> Dict[str, Any]:
        data = self._load_json(self.config_path, {})
        if "allowlist" in data:
            allowlist = data.get("allowlist")
            if not isinstance(allowlist, list):
                allowlist = DEFAULT_ALLOWLIST
        else:
            allowlist = DEFAULT_ALLOWLIST
        return {
            "enabled": bool(data.get("enabled", self.enabled)),
            "allowlist": sorted(set(str(d).lower().strip() for d in allowlist if str(d).strip())),
            "max_bytes": int(data.get("max_bytes", self.max_bytes)),
        }

    def set_enabled(self, enabled: bool) -> None:
        cfg = self.config()
        cfg["enabled"] = bool(enabled)
        self._atomic_json(self.config_path, cfg)
        self.enabled = bool(enabled)

    def allowlist(self) -> List[str]:
        return self.config()["allowlist"]

    def add_domain(self, domain: str) -> str:
        domain = self._normalize_domain(domain)
        self._validate_domain_for_allowlist(domain)
        cfg = self.config()
        domains = set(cfg["allowlist"])
        domains.add(domain)
        cfg["allowlist"] = sorted(domains)
        self._atomic_json(self.config_path, cfg)
        return domain

    def remove_domain(self, domain: str) -> str:
        domain = self._normalize_domain(domain)
        cfg = self.config()
        cfg["allowlist"] = [d for d in cfg["allowlist"] if d != domain]
        self._atomic_json(self.config_path, cfg)
        return domain

    def audit_tail(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        lines = self.audit_path.read_text(encoding="utf-8", errors="replace").splitlines()
        events = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except Exception:
                pass
        return events

    def search_literature(self, query: str, purpose: str = "research_literature") -> List[Dict[str, Any]]:
        try:
            if not self.config()["enabled"]:
                self._audit("search", "", purpose, "blocked", "web_disabled")
                return []
            query = self._minimal_query(query)
            sources: List[Dict[str, Any]] = []
            sources.extend(self._search_arxiv(query, purpose))
            sources.extend(self._search_crossref(query, purpose))
            sources.extend(self._search_wikipedia(query, purpose))
            return sources
        except Exception as exc:
            self._audit("search", "", purpose, "blocked", f"search_failed:{exc}", query=str(query)[:300])
            return []

    def fetch_text(self, url: str, purpose: str = "research_fetch") -> Dict[str, Any]:
        return self._request(url, purpose=purpose, method="GET", binary=False)

    def download_quarantined(self, url: str, purpose: str = "research_download") -> Dict[str, Any]:
        return self._request(url, purpose=purpose, method="GET", binary=True)

    def head(self, url: str, purpose: str = "research_head") -> Dict[str, Any]:
        return self._request(url, purpose=purpose, method="HEAD", binary=False)

    def _search_arxiv(self, query: str, purpose: str) -> List[Dict[str, Any]]:
        encoded = urllib.parse.urlencode({"search_query": f"all:{query}", "start": "0", "max_results": "5"})
        url = f"https://export.arxiv.org/api/query?{encoded}"
        result = self.fetch_text(url, purpose=purpose)
        if not result.get("allowed"):
            return []
        text = result.get("text", "")
        entries = []
        for raw in re.findall(r"<entry>(.*?)</entry>", text, flags=re.S):
            title = self._xml_text(raw, "title")
            summary = self._xml_text(raw, "summary")
            year = self._xml_text(raw, "published")[:4]
            authors = ", ".join(re.findall(r"<name>(.*?)</name>", raw, flags=re.S))
            link_match = re.search(r"<id>(.*?)</id>", raw, flags=re.S)
            if title:
                entries.append(self._source(
                    title=title,
                    authors=authors,
                    year=year or "unknown",
                    url=link_match.group(1).strip() if link_match else url,
                    summary=summary[:800],
                    relevance="arXiv search result; source text is untrusted until reviewed.",
                    trust_level="survey",
                    retrieval_mode="web_arxiv",
                ))
        return entries

    def _search_crossref(self, query: str, purpose: str) -> List[Dict[str, Any]]:
        encoded = urllib.parse.urlencode({"query.title": query, "rows": "3"})
        url = f"https://api.crossref.org/works?{encoded}"
        result = self.fetch_text(url, purpose=purpose)
        if not result.get("allowed"):
            return []
        try:
            data = json.loads(result.get("text", "{}"))
        except Exception:
            return []
        entries = []
        for item in data.get("message", {}).get("items", [])[:3]:
            title = " ".join(item.get("title") or [])[:300]
            if not title:
                continue
            authors = ", ".join(
                " ".join(part for part in [a.get("given", ""), a.get("family", "")] if part).strip()
                for a in item.get("author", [])[:6]
            )
            year_parts = item.get("published-print", item.get("published-online", {})).get("date-parts", [[]])
            year = str(year_parts[0][0]) if year_parts and year_parts[0] else "unknown"
            doi = item.get("DOI", "")
            entries.append(self._source(
                title=title,
                authors=authors,
                year=year,
                url=f"https://doi.org/{doi}" if doi else item.get("URL", ""),
                summary=(item.get("abstract") or "")[:800],
                relevance="Crossref metadata; bibliographic grounding only.",
                trust_level="trusted_reference",
                retrieval_mode="web_crossref",
            ))
        return entries

    def _search_wikipedia(self, query: str, purpose: str) -> List[Dict[str, Any]]:
        encoded = urllib.parse.urlencode({
            "action": "opensearch",
            "search": query,
            "limit": "3",
            "namespace": "0",
            "format": "json",
        })
        url = f"https://en.wikipedia.org/w/api.php?{encoded}"
        result = self.fetch_text(url, purpose=purpose)
        if not result.get("allowed"):
            return []
        try:
            data = json.loads(result.get("text", "[]"))
        except Exception:
            return []
        titles = data[1] if len(data) > 1 else []
        summaries = data[2] if len(data) > 2 else []
        urls = data[3] if len(data) > 3 else []
        entries = []
        for idx, title in enumerate(titles[:3]):
            entries.append(self._source(
                title=str(title),
                authors="Wikipedia contributors",
                year=str(datetime.now().year),
                url=str(urls[idx]) if idx < len(urls) else "",
                summary=str(summaries[idx])[:500] if idx < len(summaries) else "",
                relevance="Reference overview; not primary proof source.",
                trust_level="trusted_reference",
                retrieval_mode="web_wikipedia",
            ))
        return entries

    def _request(self, url: str, purpose: str, method: str = "GET", binary: bool = False) -> Dict[str, Any]:
        method = method.upper()
        if method not in {"GET", "HEAD"}:
            self._audit(method, url, purpose, "blocked", "method_not_allowed")
            return {"allowed": False, "reason": "method_not_allowed"}
        try:
            parsed = self._validate_url(url)
            self._validate_domain(parsed.hostname or "")
            self._validate_resolved_ips(parsed.hostname or "")
        except Exception as exc:
            self._audit(method, url, purpose, "blocked", str(exc))
            return {"allowed": False, "reason": str(exc)}

        current_url = url
        opener = urllib.request.build_opener(NoRedirectHandler)
        try:
            for redirect_count in range(4):
                request = urllib.request.Request(
                    current_url,
                    method=method,
                    headers={
                        "User-Agent": "LocalResearchAgent/1.0 read-only literature retrieval",
                        "Accept": "text/plain,text/xml,application/xml,application/json,application/pdf,text/html;q=0.5",
                    },
                )
                try:
                    response = opener.open(request, timeout=12)
                except urllib.error.HTTPError as exc:
                    if exc.code in {301, 302, 303, 307, 308}:
                        if redirect_count >= 3:
                            raise ValueError("too_many_redirects") from exc
                        location = exc.headers.get("Location")
                        if not location:
                            raise ValueError("redirect_without_location") from exc
                        current_url = urllib.parse.urljoin(current_url, location)
                        parsed = self._validate_url(current_url)
                        self._validate_domain(parsed.hostname or "")
                        self._validate_resolved_ips(parsed.hostname or "")
                        continue
                    raise
                with response:
                    final_url = response.geturl()
                    final_parsed = self._validate_url(final_url)
                    self._validate_domain(final_parsed.hostname or "")
                    self._validate_resolved_ips(final_parsed.hostname or "")
                    content_type = response.headers.get("Content-Type", "")
                    if method == "HEAD":
                        self._audit(method, final_url, purpose, "allowed", "head_ok", content_type=content_type)
                        return {"allowed": True, "content_type": content_type, "headers": dict(response.headers), "final_url": final_url}
                    data = self._read_limited(response, self.config()["max_bytes"])
                    parsed = final_parsed
                    url = final_url
                    break
            else:
                raise ValueError("too_many_redirects")
        except Exception as exc:
            self._audit(method, url, purpose, "blocked", f"request_failed:{exc}")
            return {"allowed": False, "reason": f"request_failed:{exc}"}

        digest = hashlib.sha256(data).hexdigest()
        prompt_risk = self._prompt_injection_risk(data)
        if binary or self._looks_binary(content_type):
            suffix = self._suffix_for_content(url, content_type)
            cache_path = self.cache_dir / f"{int(time.time())}_{slugify(parsed.netloc)}_{digest[:12]}{suffix}"
            cache_path.write_bytes(data)
            self._audit(method, url, purpose, "allowed", "download_quarantined", sha256=digest, path=str(cache_path), content_type=content_type, prompt_injection_risk=prompt_risk)
            return {"allowed": True, "sha256": digest, "path": str(cache_path), "content_type": content_type, "prompt_injection_risk": prompt_risk}

        text = data.decode("utf-8", errors="replace")
        text = self._html_to_text(text) if "html" in content_type.lower() else text
        if prompt_risk:
            text = self._strip_prompt_injection(text)[:4000]
        cache_path = self.cache_dir / f"{int(time.time())}_{slugify(parsed.netloc)}_{digest[:12]}.txt"
        cache_path.write_text(text, encoding="utf-8")
        self._audit(method, url, purpose, "allowed", "text_cached", sha256=digest, path=str(cache_path), content_type=content_type, prompt_injection_risk=prompt_risk)
        return {"allowed": True, "text": text, "sha256": digest, "path": str(cache_path), "content_type": content_type, "prompt_injection_risk": prompt_risk, "final_url": url}

    def _validate_url(self, url: str) -> urllib.parse.ParseResult:
        if re.match(r"^[a-zA-Z]:\\", url) or url.startswith("\\\\"):
            raise ValueError("windows_path_blocked")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("scheme_blocked")
        if not parsed.hostname:
            raise ValueError("missing_hostname")
        return parsed

    def _validate_domain(self, hostname: str) -> None:
        host = hostname.lower().strip(".")
        allowlist = self.allowlist()
        if not any(host == d or host.endswith("." + d) for d in allowlist):
            raise ValueError(f"domain_not_allowed:{host}")

    def _validate_resolved_ips(self, hostname: str) -> None:
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise ValueError(f"private_or_internal_ip_blocked:{ip}")

    def _read_limited(self, response, max_bytes: int) -> bytes:
        chunks = []
        total = 0
        while True:
            chunk = response.read(min(65536, max_bytes - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("download_too_large")
        return b"".join(chunks)

    def _source(self, title: str, authors: str, year: str, url: str, summary: str, relevance: str, trust_level: str, retrieval_mode: str) -> Dict[str, Any]:
        return {
            "title": re.sub(r"\s+", " ", title).strip(),
            "authors": re.sub(r"\s+", " ", authors).strip(),
            "year": str(year or "unknown"),
            "url": url,
            "bibtex_key": f"{retrieval_mode}_{slugify(title)[:36]}",
            "summary": re.sub(r"\s+", " ", self._strip_prompt_injection(summary)).strip()[:800],
            "relevance": relevance,
            "used_for_approach_id": "A001",
            "retrieval_mode": retrieval_mode,
            "trust_level": trust_level,
            "untrusted_source": True,
        }

    def _minimal_query(self, query: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 äöüÄÖÜß:;,.+-_/")
        cleaned = "".join(ch if ch in allowed else " " for ch in str(query))
        cleaned = " ".join(cleaned.split())
        return cleaned[:300]

    def _normalize_domain(self, domain: str) -> str:
        domain = domain.strip().lower()
        if "://" in domain:
            domain = urllib.parse.urlparse(domain).hostname or ""
        domain = domain.strip(".")
        if not domain:
            raise ValueError("empty_domain")
        return domain

    def _validate_domain_for_allowlist(self, domain: str) -> None:
        try:
            ip = ipaddress.ip_address(domain)
        except ValueError:
            return
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
            raise ValueError("cannot_allow_private_or_internal_domain")

    def _prompt_injection_risk(self, data: bytes) -> bool:
        sample = data[:200000].decode("utf-8", errors="ignore").lower()
        return any(pattern in sample for pattern in PROMPT_INJECTION_PATTERNS)

    def _strip_prompt_injection(self, text: str) -> str:
        lowered = text.lower()
        if any(pattern in lowered for pattern in PROMPT_INJECTION_PATTERNS):
            return "[prompt_injection_risk removed from untrusted source]"
        return text

    def _html_to_text(self, text: str) -> str:
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _looks_binary(self, content_type: str) -> bool:
        ctype = content_type.lower()
        return "pdf" in ctype or "octet-stream" in ctype

    def _suffix_for_content(self, url: str, content_type: str) -> str:
        path_suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if path_suffix in {".pdf", ".bib", ".txt"}:
            return path_suffix
        if "pdf" in content_type.lower():
            return ".pdf"
        return ".bin"

    def _xml_text(self, text: str, tag: str) -> str:
        match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, flags=re.S)
        if not match:
            return ""
        return (
            match.group(1)
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
        )

    def _audit(self, method: str, url: str, purpose: str, decision: str, reason: str, **extra: Any) -> None:
        parsed = urllib.parse.urlparse(url) if url else None
        event = {
            "ts": now_iso(),
            "method": method,
            "url": url,
            "domain": parsed.hostname if parsed else "",
            "purpose": purpose,
            "decision": decision,
            "reason": reason,
            **extra,
        }
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _atomic_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(data, indent=2, ensure_ascii=False))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, path)
        finally:
            Path(tmp_name).unlink(missing_ok=True)
