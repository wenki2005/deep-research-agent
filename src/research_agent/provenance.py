"""Task-local, thread-safe provenance. Observed text is not a truth certificate."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import wraps
from threading import RLock
from urllib.parse import urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    try:
        parts = urlsplit((url or "").strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            return ""
        _ = parts.port
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))
    except (ValueError, TypeError):
        return ""


def is_search_result_url(url: str) -> bool:
    value = normalize_url(url)
    if not value:
        return True
    parts = urlsplit(value)
    host, path = parts.hostname or "", parts.path.rstrip("/").lower() or "/"
    rules = {
        "baidu.com": {"/", "/s", "/link", "/sf/vsearch"},
        "bing.com": {"/", "/search", "/ck/a", "/news/search"},
        "sogou.com": {"/", "/web", "/link"},
        "google.com": {"/", "/search", "/url"},
        "google.com.hk": {"/", "/search", "/url"},
        "google.co.uk": {"/", "/search", "/url"},
        "duckduckgo.com": {"/", "/html", "/lite", "/l"},
    }
    return any((host == domain or host.endswith("." + domain)) and path in paths
               for domain, paths in rules.items())


def observed_date(value: str | None) -> str | None:
    """Keep only valid, non-future ISO dates received from a tool."""
    try:
        parsed = date.fromisoformat((value or "")[:10])
        return parsed.isoformat() if parsed <= datetime.now(timezone.utc).date() else None
    except (TypeError, ValueError):
        return None


@dataclass
class SourceRecord:
    url: str
    title: str = ""
    snippet: str = ""
    content: str = ""
    backend: str = ""
    fetched: bool = False
    source_id: str = ""
    published_at: str | None = None


@dataclass
class ProvenanceRegistry:
    records: dict[str, SourceRecord] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def _ensure(self, url: str) -> SourceRecord:
        if url not in self.records:
            self.records[url] = SourceRecord(url=url, source_id=f"SRC-{len(self.records) + 1:03d}")
        return self.records[url]

    def register_search_results(self, results: list[dict], backend: str) -> None:
        with self._lock:
            for item in results:
                url = normalize_url(item.get("href") or item.get("url") or "")
                if is_search_result_url(url):
                    continue
                record = self._ensure(url)
                record.title = record.title or (item.get("title") or "").strip()
                record.snippet = record.snippet or (item.get("body") or item.get("content") or "").strip()
                raw = (item.get("raw_content") or "").strip()
                record.content = raw or record.content or (item.get("content") or "").strip()
                record.fetched = record.fetched or bool(raw)
                record.backend = record.backend or backend
                record.published_at = record.published_at or observed_date(item.get("published_at"))

    def mark_fetched(self, url: str, content: str) -> None:
        key = normalize_url(url)
        if is_search_result_url(key) or not content or not content.strip():
            return
        with self._lock:
            record = self._ensure(key)
            record.content = content
            record.fetched = True

    def contains(self, url: str) -> bool:
        return self.get(url) is not None

    def get(self, reference: str) -> SourceRecord | None:
        value = (reference or "").strip()
        with self._lock:
            if value.upper().startswith("SRC-"):
                return next((r for r in self.records.values() if r.source_id == value.upper()), None)
            return self.records.get(normalize_url(value))

    def source_ref(self, url: str) -> str:
        record = self.get(url)
        return record.source_id if record else ""

    def citation_packet(self, limit: int = 20) -> str:
        with self._lock:
            records = list(self.records.values())[:limit]
        blocks = []
        for record in records:
            kind = "网页正文" if record.fetched else "搜索摘录（未读取全文）"
            excerpt = " ".join((record.content or record.snippet).split())[:1800]
            blocks.append(f"[{record.source_id}] {record.title or record.url}\nURL: {record.url}"
                          f"\n类型: {kind}\n摘录: {excerpt or '(无可引用文本)'}")
        return "\n\n".join(blocks) or "[本次运行没有可引用来源]"

    def urls(self) -> set[str]:
        with self._lock:
            return set(self.records)


_CURRENT: ContextVar[ProvenanceRegistry | None] = ContextVar("research_provenance", default=None)


def start_run() -> ProvenanceRegistry:
    registry = ProvenanceRegistry()
    _CURRENT.set(registry)
    return registry


def current() -> ProvenanceRegistry | None:
    return _CURRENT.get()


def set_current(registry: ProvenanceRegistry | None) -> None:
    _CURRENT.set(registry)


@contextmanager
def use_registry(registry: ProvenanceRegistry):
    token = _CURRENT.set(registry)
    try:
        yield registry
    finally:
        _CURRENT.reset(token)


def isolated_run(function):
    """One registry per call; reset on normal completion, error, and cancellation."""
    @wraps(function)
    async def wrapped(*args, **kwargs):
        with use_registry(ProvenanceRegistry()):
            return await function(*args, **kwargs)
    return wrapped
