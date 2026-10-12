"""Regressions for the 2026-09-08 audit, plus SDK and pipeline boundaries."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from contextvars import Context
from types import SimpleNamespace

import pytest
from agents.tool_context import ToolContext

from research_agent import runner, tools
from research_agent.evals import score_case
from research_agent.formatting import report_to_markdown
from research_agent.models import Finding, KeyFinding, ResearchNotes, ResearchPlan, ResearchReport, Source
from research_agent.provenance import (
    ProvenanceRegistry,
    current,
    isolated_run,
    normalize_url,
    observed_date,
    set_current,
    use_registry,
)
from research_agent.routing import apply_provenance_guard

URL = "https://example.com/report"
QUOTE = "The agency has not confirmed this event."
FAKE = "https://example.invalid/fake"


def make_registry():
    reg = ProvenanceRegistry()
    reg.register_search_results([{"href": URL, "title": "Personal blog", "content": QUOTE}], "fixture")
    return reg


def make_report(urls=None, quote=QUOTE):
    return ResearchReport(
        title=f"Official confirmation {FAKE}", summary=f"Confirmed {FAKE}",
        recommendations=f"Use {FAKE}", limitations=f"All verified {FAKE}",
        key_findings=[KeyFinding(topic="confirmed", details=f"Event confirmed {FAKE}",
                                status="confirmed", confidence="high", evidence=[
                                    Finding(content="The event is confirmed", evidence_quote=quote,
                                            source_urls=urls or [URL], status="confirmed", confidence="high")
                                ])],
        sources=[Source(title="Official confirmation", url=URL, source_type="official", published_at="2099-01-01")],
    )


def test_all_draft_prose_removed_and_contradictory_claim_not_certified():
    result = apply_provenance_guard(make_report(), make_registry())
    markdown = report_to_markdown(result)
    assert FAKE not in result.model_dump_json()
    assert "Event confirmed" not in markdown
    assert QUOTE in markdown
    assert result.key_findings[0].status == "reported_not_verified"
    assert result.key_findings[0].evidence[0].content == QUOTE
    assert result.key_findings[0].evidence[0].support_level == "snippet_quote"
    assert result.evidence_coverage == 1.0  # quote coverage, expressly NOT truth


def test_metadata_not_taken_from_model():
    result = apply_provenance_guard(make_report(), make_registry())
    source = result.sources[0]
    assert source.title == "Personal blog"
    assert source.source_type == "unknown"
    assert source.published_at is None
    assert source.quality_score == 45


def test_every_url_must_match_and_missing_sources_list_is_completed():
    reg = make_registry()
    unrelated = "https://example.org/unrelated"
    reg.register_search_results([{"href": unrelated, "content": "Unrelated weather"}], "fixture")
    candidate = make_report([unrelated, URL])  # match is second, not first
    candidate.sources = []
    result = apply_provenance_guard(candidate, reg)
    assert result.key_findings[0].evidence[0].source_urls == [URL]
    assert URL in [s.url for s in result.sources]


@pytest.mark.parametrize("url", [
    "https://www.baidu.com/s?wd=x", "https://cn.bing.com/search?q=x",
    "https://www.sogou.com/web?query=x", "https://www.baidu.com/link?url=x",
    "https://www.bing.com/ck/a?u=x", "https://www.google.com.hk/search?q=x",
])
def test_search_pages_rejected_by_both_registry_entries(url):
    reg = ProvenanceRegistry()
    reg.register_search_results([{"href": url, "content": QUOTE}], "fixture")
    reg.mark_fetched(url, QUOTE)
    assert not reg.records
    assert not apply_provenance_guard(make_report([url]), reg).sources


def test_guard_is_idempotent():
    reg = make_registry()
    first = apply_provenance_guard(make_report(), reg).model_dump()
    second = apply_provenance_guard(ResearchReport(**first), reg).model_dump()
    assert first == second


def test_unmatched_quote_removed_and_zero_coverage_fails_evaluation():
    report = make_report(quote="Fabricated quotation")
    report.key_findings = [f.model_copy(deep=True) for f in report.key_findings * 3]
    result = apply_provenance_guard(report, make_registry())
    assert result.evidence_coverage == 0
    assert result.verification_state == "insufficient"
    assert "Fabricated quotation" not in result.model_dump_json()
    scores = score_case("topic", result, 0)
    assert scores["passed"] is False
    assert scores["abstained"] is True
    assert scores["structure_ok"] is True


def test_news_sources_registered(monkeypatch):
    reg = ProvenanceRegistry()
    monkeypatch.setattr(tools, "get_tavily_api_key", lambda: "fixture")
    monkeypatch.setattr(tools, "_tavily_search", lambda *a, **k: [{"href": URL, "content": QUOTE}])
    with use_registry(reg):
        output = tools._news_search("topic")
    assert reg.contains(URL)
    assert "SRC-001" in output


@pytest.mark.parametrize("key", [None, "fixture"])
def test_empty_news_returns_failure_not_unbound_error(monkeypatch, key):
    monkeypatch.setattr(tools, "get_tavily_api_key", lambda: key)
    monkeypatch.setattr(tools, "_tavily_search", lambda *a, **k: [])
    monkeypatch.setattr(tools, "_search_raw", lambda *a, **k: ([], "empty"))
    assert "news search failed" in tools._news_search("topic")


def test_no_key_news_uses_fallback(monkeypatch):
    monkeypatch.setattr(tools, "get_tavily_api_key", lambda: None)
    monkeypatch.setattr(tools, "_search_raw", lambda *a, **k: ([{"href": URL, "title": "Found"}], ""))
    assert "Found" in tools._news_search("topic")


def test_filtered_empty_backend_continues(monkeypatch):
    calls = []

    def bad(*args):
        calls.append("bad")
        return [{"href": "https://www.baidu.com/s?wd=x"}]

    def good(*args):
        calls.append("good")
        return [{"href": URL, "content": QUOTE}]

    monkeypatch.setattr(tools, "_active_backends", lambda *a: ["bad", "good"])
    monkeypatch.setitem(tools._BACKENDS, "bad", bad)
    monkeypatch.setitem(tools._BACKENDS, "good", good)
    with use_registry(ProvenanceRegistry()) as reg:
        results, error = tools._search_raw("topic")
        assert reg.contains(URL)
    assert calls == ["bad", "good"]
    assert len(results) == 1 and not error


def test_tavily_recency_and_raw_text_contract(monkeypatch):
    captured = {}

    def post(url, json, timeout):
        captured.update(json)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"results": [
            {"url": URL, "content": "Snippet", "raw_content": QUOTE, "published_date": "2026-01-02"}]})

    monkeypatch.setattr(tools, "get_tavily_api_key", lambda: "fixture")
    monkeypatch.setattr(tools.requests, "post", post)
    results = tools._tavily_search("topic", 2, recency="year")
    assert captured["time_range"] == "year"
    assert captured["include_raw_content"] == "text"
    reg = ProvenanceRegistry()
    reg.register_search_results(results, "tavily")
    assert reg.get(URL).fetched is True
    assert reg.get(URL).content == QUOTE
    assert reg.get(URL).published_at == "2026-01-02"


@pytest.mark.parametrize("backend", [tools._bing_search, tools._baidu_search])
def test_unsupported_recency_explicitly_rejected(backend):
    with pytest.raises(ValueError, match="cannot enforce recency"):
        backend("topic", 2, "week")


def test_ddg_receives_time_filter(monkeypatch):
    captured = {}

    class FakeDDG:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def text(self, query, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(tools, "DDGS", FakeDDG)
    tools._ddg_search("topic", 3, "year")
    assert captured["timelimit"] == "y"
    with pytest.raises(ValueError):
        tools._web_search("topic", recency="century")


def test_fresh_context_does_not_inherit_global_registry():
    with use_registry(make_registry()):
        assert Context().run(current) is None


def test_unique_ids_under_threaded_registration():
    reg = ProvenanceRegistry()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: reg.register_search_results([{"href": f"https://example.com/{i}"}], "test"),
                      range(100)))
    assert len({r.source_id for r in reg.records.values()}) == 100


async def test_context_restored_after_error_and_cancel():
    @isolated_run
    async def broken():
        assert current() is not None
        raise RuntimeError("fixture")

    @isolated_run
    async def cancelled():
        raise asyncio.CancelledError

    parent = make_registry()
    with use_registry(parent):
        with pytest.raises(RuntimeError):
            await broken()
        assert current() is parent
        with pytest.raises(asyncio.CancelledError):
            await cancelled()
        assert current() is parent


async def test_sdk_bound_tools_keep_independent_run_registries(monkeypatch):
    monkeypatch.setattr(tools, "_active_backends", lambda *a: ["fixture"])
    monkeypatch.setitem(tools._BACKENDS, "fixture", lambda query, *a: [
        {"href": f"https://example.com/{query}", "content": QUOTE}])
    regs = [ProvenanceRegistry(), ProvenanceRegistry()]
    bound = [tools.bound_tools(reg)[0] for reg in regs]
    set_current(None)

    async def invoke(index):
        args = json.dumps({"query": str(index), "max_results": 2, "recency": "any"})
        ctx = ToolContext(context=None, tool_name="web_search", tool_call_id=str(index), tool_arguments=args)
        return await bound[index].on_invoke_tool(ctx, args)

    outputs = await asyncio.gather(invoke(0), invoke(1))
    assert all("SRC-001" in output for output in outputs)
    assert regs[0].urls() == {"https://example.com/0"}
    assert regs[1].urls() == {"https://example.com/1"}
    assert current() is None


@pytest.mark.parametrize("repair_failure", [False, True])
async def test_pipeline_retains_better_first_report_and_cleans_context(monkeypatch, repair_failure):
    searches = []
    writes = []

    def search(query, *args):
        searches.append(query)
        current().register_search_results([{"href": URL, "content": QUOTE}], "fixture")
        return current().citation_packet()

    async def run(agent, text, **kwargs):
        if agent.name == "Planner":
            return SimpleNamespace(final_output=ResearchPlan(angle="test", queries=["planned query"]))
        if agent.name == "Researcher":
            return SimpleNamespace(final_output=ResearchNotes(query="planned query"))
        writes.append(text)
        if len(writes) == 2:
            if repair_failure:
                raise RuntimeError("repair unavailable")
            return SimpleNamespace(final_output=ResearchReport(title="worse", summary="draft", key_findings=[]))
        result = make_report()
        result.key_findings.extend([KeyFinding(topic="unsupported", details="fake") for _ in range(2)])
        return SimpleNamespace(final_output=result)

    monkeypatch.setattr(runner, "_research_sources", search)
    monkeypatch.setattr(runner, "build_model", lambda *a: None)
    monkeypatch.setattr(runner.Runner, "run", run)
    set_current(None)
    result = await runner.run_research("original question", provider="local", verbose=False, max_queries=1)
    assert len(writes) == 2
    assert searches == ["planned query", "original question"]
    assert result.evidence_coverage == pytest.approx(1 / 3)
    assert len(result.key_findings) == 3
    assert QUOTE in report_to_markdown(result)
    assert current() is None


def test_invalid_url_and_date_do_not_crash():
    assert normalize_url("https://[invalid") == ""
    assert normalize_url("https://user:password@example.com") == ""
    assert observed_date("2099-01-01") is None
    assert observed_date("not a date") is None


def test_render_external_title_as_literal():
    reg = make_registry()
    reg.get(URL).title = f"[Fake link]({FAKE}) <img src=x>"
    result = apply_provenance_guard(make_report(), reg)
    markdown = report_to_markdown(result)
    assert FAKE not in markdown
    assert "<img" not in markdown

def test_raw_text_upgrade_replaces_snippet_without_falsely_certifying_it():
    reg = make_registry()
    reg.register_search_results([{"href": URL, "raw_content": "Different page body"}], "tavily")
    result = apply_provenance_guard(make_report(), reg)
    # Original quote exists only in the search snippet, not the fetched page body.
    assert result.key_findings[0].evidence[0].support_level == "snippet_quote"
    assert reg.get(URL).content == "Different page body"


def test_save_report_retains_question_and_avoids_collisions(tmp_path):
    result = apply_provenance_guard(make_report(), make_registry())
    result.question = "原始研究问题"
    first = runner.save_report(result, tmp_path)
    second = runner.save_report(result, tmp_path)
    assert first != second
    assert "原始研究问题" in first.read_text(encoding="utf-8")
