from research_agent.models import Finding, KeyFinding, ResearchReport, Source
from research_agent.provenance import (
    ProvenanceRegistry,
    current,
    is_search_result_url,
    normalize_url,
    set_current,
    start_run,
)
from research_agent.routing import apply_provenance_guard


def test_normalize_url_removes_fragment():
    assert normalize_url("https://EXAMPLE.com/a#section") == "https://example.com/a"


def test_search_result_pages_are_not_citable():
    assert is_search_result_url("https://www.baidu.com/s?wd=topic")
    assert is_search_result_url("https://www.sogou.com/web?query=topic")
    assert is_search_result_url("https://www.bing.com/search?q=topic")
    assert not is_search_result_url("https://example.com/article")


def test_start_run_is_available_as_current_registry():
    registry = start_run()
    assert current() is registry
    set_current(None)


def test_provenance_guard_removes_invented_source_and_evidence():
    registry = ProvenanceRegistry()
    registry.register_search_results(
        [{"title": "Observed", "href": "https://example.com/real", "body": "snippet", "content": "quoted fact"}],
        "test",
    )
    report = ResearchReport(
        title="t",
        summary="s",
        key_findings=[
            KeyFinding(
                topic="real",
                details="d",
                status="confirmed",
                confidence="high",
                evidence=[
                    Finding(
                        content="fact",
                        status="confirmed",
                        confidence="high",
                        source_urls=["https://example.com/real"],
                        evidence_quote="quoted fact",
                    )
                ],
            ),
            KeyFinding(
                topic="fake",
                details="d",
                status="confirmed",
                confidence="high",
                evidence=[
                    Finding(
                        content="fake",
                        status="confirmed",
                        confidence="high",
                        source_urls=["https://mps.gov.cn/fabricated"],
                        evidence_quote="invented official statement",
                    )
                ],
            ),
        ],
        sources=[
            Source(title="real", url="https://example.com/real"),
            Source(title="fake", url="https://mps.gov.cn/fabricated", source_type="government"),
        ],
    )
    guarded = apply_provenance_guard(report, registry)
    assert [source.url for source in guarded.sources] == ["https://example.com/real"]
    assert len(guarded.key_findings[0].evidence) == 1
    assert guarded.key_findings[1].evidence == []
    assert guarded.key_findings[1].status == "unknown"
    assert guarded.evidence_coverage == 0.5


def test_provenance_guard_falls_back_to_observed_sources():
    registry = ProvenanceRegistry()
    registry.register_search_results(
        [{"title": "Observed", "href": "https://example.com/real", "body": "snippet"}],
        "test",
    )
    report = ResearchReport(title="t", summary="s", key_findings=[])
    guarded = apply_provenance_guard(report, registry)
    assert [source.url for source in guarded.sources] == ["https://example.com/real"]


def test_registry_assigns_ids_and_resolves_them():
    registry = ProvenanceRegistry()
    registry.register_search_results(
        [{"title": "Observed", "href": "https://example.com/real", "body": "snippet"}],
        "test",
    )
    assert registry.source_ref("https://example.com/real") == "SRC-001"
    assert registry.get("SRC-001").url == "https://example.com/real"


def test_provenance_guard_maps_source_ids_to_real_urls():
    registry = ProvenanceRegistry()
    registry.register_search_results(
        [{"title": "Observed", "href": "https://example.com/real", "content": "quoted fact"}],
        "test",
    )
    report = ResearchReport(
        title="t",
        summary="s",
        key_findings=[
            KeyFinding(
                topic="real",
                details="d",
                evidence=[
                    Finding(
                        content="fact",
                        source_urls=["SRC-001"],
                        evidence_quote="quoted fact",
                    )
                ],
            )
        ],
        sources=[Source(title="real", url="SRC-001")],
    )
    guarded = apply_provenance_guard(report, registry)
    assert guarded.sources[0].url == "https://example.com/real"
    assert guarded.key_findings[0].evidence[0].source_urls == ["https://example.com/real"]


def test_provenance_guard_warns_when_no_real_sources_exist():
    report = ResearchReport(
        title="t",
        summary="模型生成的摘要",
        key_findings=[KeyFinding(topic="claim", details="模型生成的结论", status="confirmed")],
    )
    guarded = apply_provenance_guard(report, ProvenanceRegistry())
    assert "没有登记到任何真实搜索" in guarded.summary
    assert guarded.key_findings[0].status == "unknown"


def test_provenance_guard_marks_unquoted_confirmed_claim_as_low_confidence():
    registry = ProvenanceRegistry()
    registry.register_search_results(
        [{"title": "Observed", "href": "https://example.com/real", "content": "actual page text"}],
        "test",
    )
    report = ResearchReport(
        title="t",
        summary="s",
        key_findings=[
            KeyFinding(
                topic="claim",
                details="d",
                status="confirmed",
                confidence="high",
                evidence=[
                    Finding(
                        content="claim",
                        status="confirmed",
                        confidence="high",
                        source_urls=["https://example.com/real"],
                        evidence_quote="not in the page",
                    )
                ],
            )
        ],
    )
    guarded = apply_provenance_guard(report, registry)
    assert guarded.key_findings[0].evidence == []
    assert guarded.key_findings[0].status == "unknown"
    assert "模型草稿已移除" in guarded.key_findings[0].details
    assert "不能把报告中的具体日期" in guarded.summary
