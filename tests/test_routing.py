from research_agent.models import Finding, KeyFinding, ResearchReport, Source
from research_agent.routing import evidence_coverage, infer_mode, mode_instruction, score_source_quality


def test_infer_modes():
    assert infer_mode("网红失踪事件最新进展") == "hot_topic"
    assert infer_mode("人工智能监管政策") == "policy"
    assert infer_mode("开源模型技术架构") == "technical"
    assert infer_mode("AI就业市场") == "industry"


def test_mode_instruction_mentions_hot_topic_protocol():
    assert "时间线" in mode_instruction("hot_topic")


def test_source_quality_ranks_government():
    gov = Source(title="gov", url="https://example.gov.cn/report", source_type="unknown")
    social = Source(title="social", url="https://example.com/post", source_type="social")
    assert score_source_quality(gov) > score_source_quality(social)


def test_evidence_coverage():
    evidence = Finding(
        content="confirmed",
        status="confirmed",
        confidence="high",
        source_urls=["https://example.com"],
        evidence_quote="quoted text",
        support_level="snippet_quote",
    )
    report = ResearchReport(
        title="t",
        summary="s",
        key_findings=[KeyFinding(topic="t", details="d", evidence=[evidence])],
    )
    assert evidence_coverage(report) == 1.0
