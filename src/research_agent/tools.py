"""Custom function tools that give the Researcher agents live web access.

Search strategy (order via SEARCH_BACKEND / auto):
1. Tavily API - if TAVILY_API_KEY is set (free tier at https://tavily.com).
   Returns high-quality results WITH page content, supports recency (days) and
   a news topic - this is the reliable path used by gpt-researcher etc.
2. Bing scraping - works well in most regions, incl. CN (fallback).
3. DuckDuckGo - fallback.
4. Baidu - last resort, only for Chinese queries.

Extra tools:
- `research_sources`: search THEN read the top pages' full text (real content).
- `news_search`: recent news (Tavily topic=news, or Bing News fallback).
- `web_search(..., recency=day|week|month)`: time-filtered results (API backends).
"""

from __future__ import annotations

import os
import re
from html import unescape

import requests
from agents import function_tool

from .config import get_tavily_api_key
from .provenance import ProvenanceRegistry, current, is_search_result_url, normalize_url, use_registry

try:  # pragma: no cover - depends on installed version
    from ddgs import DDGS
except ImportError:  # pragma: no cover
    from duckduckgo_search import DDGS

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_RECENCY_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


def _validate_recency(recency: str) -> None:
    if recency not in {"any", *_RECENCY_DAYS}:
        raise ValueError("recency must be any/day/week/month/year")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _strip_tags(text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


# ---------------------------------------------------------------- backends


def _tavily_search(query: str, max_results: int, recency: str = "any", topic: str = "general") -> list[dict]:
    """Tavily API (requires TAVILY_API_KEY). Returns results with page content."""
    _validate_recency(recency)
    key = get_tavily_api_key()
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    payload: dict = {
        "api_key": key,
        "query": query,
        "max_results": min(20, max(1, max_results)),
        "topic": topic,
        "include_raw_content": "text",
    }
    if topic == "general":
        payload["search_depth"] = "advanced"
    if recency in _RECENCY_DAYS:
        payload["time_range"] = recency
    elif topic == "news":
        payload["time_range"] = "week"
    resp = requests.post("https://api.tavily.com/search", json=payload, timeout=30)
    resp.raise_for_status()
    results: list[dict] = []
    for item in resp.json().get("results", []):
        content = (item.get("content") or "").strip()
        results.append(
            {
                "title": (item.get("title") or "").strip(),
                "href": (item.get("url") or "").strip(),
                "body": content[:400],
                "content": content[:1800],
                "raw_content": (item.get("raw_content") or "")[:12000],
                "published_at": item.get("published_date"),
            }
        )
        if len(results) >= max_results:
            break
    return results


def _bing_search(query: str, max_results: int, recency: str = "any") -> list[dict]:
    _validate_recency(recency)
    if recency != "any":
        raise ValueError("This scraping backend cannot enforce recency; use Tavily or DDG")
    params = {"q": query, "count": str(max_results), "setlang": "zh-hans", "mkt": "zh-CN"}
    resp = requests.get(
        "https://www.bing.com/search",
        params=params,
        headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        timeout=20,
    )
    resp.raise_for_status()
    results: list[dict] = []
    for match in re.finditer(r'<li class="b_algo".*?</li>', resp.text, re.DOTALL):
        block = match.group(0)
        title_match = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not title_match:
            continue
        url = title_match.group(1)
        if not url.startswith("http"):
            continue
        title = _strip_tags(title_match.group(2))
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
        snippet = _strip_tags(snippet_match.group(1)) if snippet_match else ""
        results.append({"title": title, "href": url, "body": snippet})
        if len(results) >= max_results:
            break
    return results


def _ddg_search(query: str, max_results: int, recency: str = "any") -> list[dict]:
    _validate_recency(recency)
    timelimit = {"day": "d", "week": "w", "month": "m", "year": "y"}.get(recency)
    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=max_results, timelimit=timelimit))
    return [
        {
            "title": (item.get("title") or ""),
            "href": (item.get("href") or item.get("url") or ""),
            "body": (item.get("body") or ""),
        }
        for item in raw
    ]


def _resolve_redirect(url: str, timeout: float = 6.0) -> str:
    """Follow baidu.com/link redirects to the real page URL (best effort)."""
    if "baidu.com/link" not in url:
        return url
    try:
        resp = requests.get(
            url, allow_redirects=True, stream=True, headers={"User-Agent": _UA}, timeout=timeout
        )
        final = resp.url
        resp.close()
        if final.startswith("http") and "baidu.com/link" not in final:
            return final
    except Exception:  # noqa: BLE001, S110 - keep the original link on any failure
        pass
    return url


def _baidu_search(query: str, max_results: int, recency: str = "any") -> list[dict]:
    _validate_recency(recency)
    if recency != "any":
        raise ValueError("This scraping backend cannot enforce recency; use Tavily or DDG")
    resp = requests.get(
        "https://www.baidu.com/s",
        params={"wd": query, "rn": str(max_results)},
        headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"},
        timeout=20,
    )
    resp.raise_for_status()
    results: list[dict] = []
    for match in re.finditer(
        r'<h3[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?</h3>', resp.text, re.DOTALL
    ):
        url = match.group(1).replace("&amp;", "&")
        if "/sf/vsearch" in url:  # skip video-only blocks
            continue
        title = _strip_tags(match.group(2))
        block = resp.text[match.start() : match.start() + 4000]
        snip_match = re.search(r'<div class="c-abstract[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
        if not snip_match:
            snip_match = re.search(r'<span class="content-right_8Zs40">(.*?)</span>', block, re.DOTALL)
        snippet = _strip_tags(snip_match.group(1)) if snip_match else ""
        results.append({"title": title, "href": _resolve_redirect(url), "body": snippet})
        if len(results) >= max_results:
            break
    return results


_BACKENDS = {
    "tavily": _tavily_search,
    "bing": _bing_search,
    "ddg": _ddg_search,
    "baidu": _baidu_search,
}


def _active_backends(query: str = "") -> list[str]:
    """Backend order. For Chinese queries Baidu ranks before Bing (it covers CN hot
    topics far better); English queries skip Baidu entirely."""
    mode = os.getenv("SEARCH_BACKEND", "auto").strip().lower()
    if mode in _BACKENDS:
        return [mode]
    has_tavily = bool(get_tavily_api_key())
    if _has_cjk(query):
        return ["tavily", "baidu", "bing", "ddg"] if has_tavily else ["baidu", "bing", "ddg"]
    return ["tavily", "bing", "ddg"] if has_tavily else ["bing", "ddg"]


# ---------------------------------------------------------------- shared logic


def _clean_results(results: list[dict], max_results: int) -> list[dict]:
    cleaned, seen = [], set()
    for item in results:
        url = normalize_url(item.get("href") or item.get("url") or "")
        if is_search_result_url(url) or url in seen:
            continue
        seen.add(url)
        cleaned.append({**item, "href": url})
        if len(cleaned) >= max_results:
            break
    return cleaned


def _search_raw(
    query: str, max_results: int = 6, recency: str = "any", read_content: bool = False,
    max_chars: int = 1800,
) -> tuple[list[dict], str]:
    """Stop only after URL cleaning yields usable results, not on raw nonempty data."""
    _validate_recency(recency)
    max_results = min(20, max(1, max_results))
    max_chars = min(12000, max(100, max_chars))
    last_error = "no available backend"
    for backend in _active_backends(query):
        if backend == "baidu" and not _has_cjk(query):
            continue
        try:
            results = _clean_results(_BACKENDS[backend](query, max_results, recency), max_results)
        except Exception as exc:  # noqa: BLE001 - bounded backend fallback
            last_error = f"{backend}: {type(exc).__name__} (time filter or provider unavailable)"
            continue
        if not results:
            last_error = f"{backend}: no citable results after filtering"
            continue
        registry = current()
        if registry is not None:
            registry.register_search_results(results, backend)
        if read_content:
            for item in results:
                if item.get("raw_content"):
                    item["content"] = item["raw_content"][:max_chars]
                    continue
                try:
                    text = _extract_main_text(item["href"])[:max_chars]
                    if text:
                        item["content"] = text
                        item["raw_content"] = text
                        if registry is not None:
                            registry.mark_fetched(item["href"], text)
                except Exception:  # noqa: BLE001 - retain search snippet on page failure
                    item["fetch_status"] = "unavailable"
        return results, ""
    return [], last_error


def _format_results(results: list[dict], with_content: bool = False) -> str:
    """Turn raw search results into a compact, model-friendly text block."""
    if not results:
        return "[no results found]"
    lines: list[str] = []
    for i, item in enumerate(results, 1):
        title = (item.get("title") or "(no title)").strip()
        url = item.get("href") or item.get("url") or ""
        registry = current()
        source_ref = registry.source_ref(url) if registry is not None else ""
        body = (item.get("body") or "").strip().replace("\n", " ")[:400]
        citation = f" [{source_ref}]" if source_ref else ""
        lines.append(f"{i}. {title}{citation}\n   URL: {url}\n   摘要: {body}")
        if with_content and item.get("content"):
            label = "正文摘录" if item.get("raw_content") else "搜索摘录（非全文）"
            lines.append(f"   {label}: {item['content'][:1800]}")
    return "\n\n".join(lines)


def _web_search(query: str, max_results: int = 6, recency: str = "any") -> str:
    results, last_error = _search_raw(query, max_results, recency)
    if not results:
        return f"[search failed: all backends ({', '.join(_active_backends())}) failed; last error: {last_error}]"
    return _format_results(results)


@function_tool
def web_search(query: str, max_results: int = 6, recency: str = "any") -> str:
    """Search the web and return a compact list of results (title, url, snippet).

    Args:
        query: the search query.
        max_results: how many results to return (default 6).
        recency: optional time filter - "day" | "week" | "month" | "year" | "any".

    Use recency to find fresh data (e.g. recency="month" for the last month).
    """
    return _web_search(query, max_results, recency)


def _research_sources(query: str, max_results: int = 4, max_chars: int = 1800) -> str:
    """Search, then read the top pages and return titles + extracted text."""
    results, last_error = _search_raw(query, max_results, "any", read_content=True, max_chars=max_chars)
    if not results:
        return (
            f"[search failed: all backends ({', '.join(_active_backends())}) failed; last error: {last_error}]"
        )
    return _format_results(results, with_content=True)


@function_tool
def research_sources(query: str, max_results: int = 4, max_chars: int = 1800) -> str:
    """Search the web, then READ the top pages and return their extracted text.

    Prefer this over web_search when you need actual content/facts: each result
    includes a content excerpt (up to max_chars chars) from the page itself.
    """
    return _research_sources(query, max_results, max_chars)


def _news_search(query: str, max_results: int = 5) -> str:
    last_error = "empty news results"
    if get_tavily_api_key():
        for topic in ("news", "general"):
            try:
                results = _clean_results(_tavily_search(query, max_results, recency="week", topic=topic),
                                         max_results)
                if results:
                    registry = current()
                    if registry is not None:
                        registry.register_search_results(results, f"tavily:{topic}")
                    return _format_results(results, with_content=True)
            except Exception as exc:  # noqa: BLE001 - try the alternate topic
                last_error = type(exc).__name__
    results, fallback_error = _search_raw(query, max_results, "week")
    if results:
        return _format_results(results)
    return f"[news search failed: {fallback_error or last_error}]"


@function_tool
def news_search(query: str, max_results: int = 5) -> str:
    """Search recent news (last ~7 days) for a topic.

    Requires TAVILY_API_KEY for best results; otherwise falls back to web search.
    Use this when you need the latest developments/events rather than evergreen
    articles.
    """
    return _news_search(query, max_results)


# ---------------------------------------------------------------- page fetch


def _extract_main_text(url: str) -> str:
    """Download a page and extract its main article text (isolated for testing)."""
    import trafilatura

    if is_search_result_url(url):
        raise ValueError("Search pages and unresolved search redirects are not articles")
    resp = requests.get(
        url,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0 (compatible; deep-research-agent/0.1)"},
    )
    resp.raise_for_status()
    if is_search_result_url(resp.url):
        raise ValueError("Redirect ended on a search page")
    text = trafilatura.extract(resp.content, include_comments=False)
    if not text:
        return ""
    return text[:6000]


def _fetch_page(url: str) -> str:
    try:
        text = _extract_main_text(url)
    except Exception as exc:  # noqa: BLE001 - report any failure back to the model
        return f"[failed to fetch {url}: {exc}]"
    if not text:
        return "[could not extract readable content from this page]"
    registry = current()
    if registry is not None:
        registry.mark_fetched(url, text)
    return text


@function_tool
def fetch_page(url: str) -> str:
    """Fetch a URL and return its main readable text content (up to ~6000 chars).

    Use this tool to read the full article behind a promising search result.
    """
    return _fetch_page(url)


def bound_tools(registry: ProvenanceRegistry):
    """Create per-run tools; closures work even when the SDK invokes a fresh context."""
    import asyncio

    @function_tool(name_override="web_search")
    async def search(query: str, max_results: int = 6, recency: str = "any") -> str:
        """Search articles. recency: any/day/week/month/year."""
        with use_registry(registry):
            return await asyncio.to_thread(_web_search, query, max_results, recency)

    @function_tool(name_override="research_sources")
    async def research(query: str, max_results: int = 4, max_chars: int = 1800) -> str:
        """Search and read article text; query should retain the event's actual dates."""
        with use_registry(registry):
            return await asyncio.to_thread(_research_sources, query, max_results, max_chars)

    @function_tool(name_override="news_search")
    async def news(query: str, max_results: int = 5) -> str:
        """Search recent news, register all returned sources, and retry other backends if empty."""
        with use_registry(registry):
            return await asyncio.to_thread(_news_search, query, max_results)

    @function_tool(name_override="fetch_page")
    async def fetch(url: str) -> str:
        """Read article text. Search result pages and unresolved redirects are rejected."""
        with use_registry(registry):
            return await asyncio.to_thread(_fetch_page, url)

    return [search, research, news, fetch]
