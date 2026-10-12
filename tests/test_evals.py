from research_agent import evals
from research_agent.models import Finding, KeyFinding, ResearchReport, Source
from research_agent.provenance import ProvenanceRegistry
from research_agent.routing import apply_provenance_guard


def _make_report(
    *,
    sources=True,
    findings=3,
    title="T",
    summary="S",
    limitations="L",
    recommendations="R",
) -> ResearchReport:
    src = (
        [Source(title="s1", url="https://example.com/article")]
        if sources
        else []
    )
    return ResearchReport(
        title=title,
        summary=summary,
        key_findings=[KeyFinding(topic=f"t{i}", details="d" * 5) for i in range(findings)],
        sources=src,
        limitations=limitations,
        recommendations=recommendations,
    )


def _good_report():
    report = _make_report()
    registry = ProvenanceRegistry()
    registry.register_search_results([{"href": "https://example.com/article", "content": "Observed excerpt"}],
                                     "fixture")
    for finding in report.key_findings:
        finding.evidence = [Finding(content="Observed excerpt", evidence_quote="Observed excerpt",
                                    source_urls=["https://example.com/article"])]
    return apply_provenance_guard(report, registry)


def test_score_case_passes_good_report():
    report = _good_report()
    result = evals.score_case("q", report, 10.0)
    assert result["passed"] is True
    assert result["structure_ok"] is True
    assert result["sources_ok"] is True
    assert result["elapsed_s"] == 10.0
    assert result["evidence_coverage"] == 1.0
    assert result["factual_accuracy_verified"] is False


def test_score_case_fails_without_sources():
    report = _make_report(sources=False)
    result = evals.score_case("q", report, 5.0)
    assert result["passed"] is False
    assert result["sources_ok"] is False
    assert result["structure_ok"] is False


def test_score_case_fails_too_few_findings():
    report = _make_report(findings=1)
    result = evals.score_case("q", report, 5.0)
    assert result["passed"] is False
    assert result["structure"]["key_findings>=3"] is False


def test_score_case_filters_invalid_urls():
    report = _make_report()
    report.sources = [
        Source(title="bad", url="not-a-url"),
        Source(title="ok", url="https://example.com/a"),
        Source(title="dup", url="https://example.com/a"),
    ]
    result = evals.score_case("q", report, 5.0)
    assert result["valid_sources"] == 1
    assert result["total_sources"] == 3


def test_keywords_found_and_missing():
    report = _make_report(summary="强化学习是一种机器学习方法")
    result = evals.score_case("q", report, 5.0, expected_keywords=["强化学习", "不存在词"])
    assert result["keyword_hits"] == 1
    assert result["keyword_total"] == 2
    assert result["keywords_found"] == ["强化学习"]
    assert result["keywords_missing"] == ["不存在词"]


def test_language_check_flags_english_report_for_chinese_question():
    report = _make_report(summary="This is an English summary")
    result = evals.score_case("中文问题", report, 5.0)
    assert result["language_ok"] is False
    assert result["passed"] is False


def test_language_check_passes_chinese_report():
    report = _make_report(summary="这是一个中文摘要")
    result = evals.score_case("中文问题", report, 5.0)
    assert result["language_ok"] is True


def test_language_check_skips_english_question():
    report = _make_report(summary="English summary")
    result = evals.score_case("What is RL?", report, 5.0)
    assert result["language_ok"] is True


def test_error_case_never_passes():
    result = evals.error_case("q", 3.0, "boom")
    assert result["passed"] is False
    assert result["error"] == "boom"


def test_summarize():
    good = evals.score_case("a", _good_report(), 10.0)
    bad = evals.error_case("b", 2.0, "x")
    summary = evals.summarize([good, bad])
    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["pass_rate"] == 50.0
    assert summary["errors"] == 1
    assert summary["avg_elapsed_s"] == 6.0
    assert summary["language_ok"] == 1


def test_load_cases_skips_comments():
    from pathlib import Path

    p = Path("C:/tmp/eval_cases_test.jsonl")
    p.write_text("# comment\n{\"question\": \"q\"}\n\n", encoding="utf-8")
    cases = evals.load_cases(p)
    assert len(cases) == 1
    assert cases[0]["question"] == "q"
    p.unlink()
