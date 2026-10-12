import pytest

from research_agent import tools


def test_format_results():
    fake = [
        {"title": "T1", "href": "https://a.com", "body": "body one"},
        {"title": "T2", "href": "https://b.com", "body": "body two"},
    ]
    out = tools._format_results(fake)
    assert "T1" in out
    assert "https://a.com" in out


def test_format_results_includes_provenance_id():
    from research_agent.provenance import ProvenanceRegistry, set_current

    active = ProvenanceRegistry()
    active.register_search_results([{"title": "T1", "href": "https://a.com", "body": "body"}], "test")
    set_current(active)
    try:
        out = tools._format_results([{"title": "T1", "href": "https://a.com", "body": "body"}])
        assert "[SRC-001]" in out
    finally:
        set_current(None)


def test_web_search_uses_first_working_backend(monkeypatch):
    fake = [{"title": "Result", "href": "https://x.com", "body": "snippet"}]

    def bing_backend(query, max_results, recency="any"):
        return fake

    monkeypatch.setitem(tools._BACKENDS, "bing", bing_backend)
    monkeypatch.setenv("SEARCH_BACKEND", "bing")
    out = tools._web_search("python agents", max_results=5)
    assert "Result" in out
    assert "https://x.com" in out


def test_web_search_falls_back_on_failure(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    calls = {"n": 0}

    def fail_backend(query, max_results, recency="any"):
        calls["n"] += 1
        raise RuntimeError("network down")

    def ok_backend(query, max_results, recency="any"):
        calls["n"] += 1
        return [{"title": "OK", "href": "https://ok.com", "body": "works"}]

    monkeypatch.setitem(tools._BACKENDS, "bing", fail_backend)
    monkeypatch.setitem(tools._BACKENDS, "ddg", ok_backend)
    monkeypatch.setitem(tools._BACKENDS, "baidu", ok_backend)
    monkeypatch.setenv("SEARCH_BACKEND", "auto")
    out = tools._web_search("AI job market trends")
    assert "OK" in out
    assert calls["n"] == 2  # English query skips Baidu


def test_web_search_all_backends_fail(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    def fail_backend(query, max_results, recency="any"):
        raise RuntimeError("down")

    monkeypatch.setitem(tools._BACKENDS, "bing", fail_backend)
    monkeypatch.setitem(tools._BACKENDS, "ddg", fail_backend)
    monkeypatch.setitem(tools._BACKENDS, "baidu", fail_backend)
    monkeypatch.setenv("SEARCH_BACKEND", "auto")
    out = tools._web_search("anything")
    assert out.startswith("[search failed:")


def test_fetch_page_failure_returns_message(monkeypatch):
    def boom(url):
        raise RuntimeError("404")

    monkeypatch.setattr(tools, "_extract_main_text", boom)
    out = tools._fetch_page("https://example.com")
    assert "failed to fetch" in out


def test_active_backends_includes_tavily_with_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    assert "tavily" in tools._active_backends("ai")


def test_active_backends_no_tavily_without_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert "tavily" not in tools._active_backends("ai")


def test_tavily_search_builds_payload(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"results": []}})()

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr("requests.post", fake_post)
    tools._tavily_search("q", 4, recency="week")
    assert captured["json"]["api_key"] == "tvly-test"
    assert captured["json"]["time_range"] == "week"
    assert captured["json"]["include_raw_content"] == "text"
    assert captured["json"]["search_depth"] == "advanced"


def test_tavily_search_requires_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        tools._tavily_search("q", 3)


def test_research_sources_includes_content(monkeypatch):
    def ok_backend(query, max_results, recency="any"):
        return [{"title": "A", "href": "https://a.com", "body": "snip"}]

    monkeypatch.setitem(tools._BACKENDS, "bing", ok_backend)
    monkeypatch.setenv("SEARCH_BACKEND", "bing")
    monkeypatch.setattr(tools, "_extract_main_text", lambda url: "这是页面正文内容" * 10)
    out = tools._research_sources("q", max_results=1)
    assert "A" in out
    assert "正文摘录" in out
    assert "这是页面正文内容" in out


def test_search_skips_baidu_for_english(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    calls = []

    def bing_backend(query, max_results, recency="any"):
        calls.append("bing")
        return [{"title": "T", "href": "https://a.com", "body": "b"}]

    def baidu_backend(query, max_results, recency="any"):
        calls.append("baidu")
        return [{"title": "B", "href": "https://b.com", "body": ""}]

    monkeypatch.setitem(tools._BACKENDS, "bing", bing_backend)
    monkeypatch.setitem(tools._BACKENDS, "ddg", bing_backend)
    monkeypatch.setitem(tools._BACKENDS, "baidu", baidu_backend)
    monkeypatch.setenv("SEARCH_BACKEND", "auto")
    tools._web_search("English query about AI")
    assert "baidu" not in calls


def test_active_backends_cjk_prefers_baidu(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    order = tools._active_backends("人工智能岗位")
    assert "baidu" in order
    assert order.index("baidu") < order.index("bing")


def test_active_backends_english_skips_baidu(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    order = tools._active_backends("AI job market")
    assert "baidu" not in order
