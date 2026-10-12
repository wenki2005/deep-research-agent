from research_agent.models import KeyFinding, ResearchNotes, ResearchPlan, ResearchReport, Source


def test_research_plan_roundtrip():
    plan = ResearchPlan(angle="覆盖综述与最新进展", queries=["a", "b"])
    data = plan.model_dump()
    assert data["queries"] == ["a", "b"]
    assert "综述" in data["angle"]


def test_research_notes_defaults():
    notes = ResearchNotes(query="q")
    assert notes.findings == []
    assert notes.sources == []


def test_research_report_required_fields():
    report = ResearchReport(
        title="t",
        summary="s",
        key_findings=[KeyFinding(topic="x", details="y")],
        sources=[Source(title="s1", url="https://example.com")],
    )
    assert report.sources[0].url == "https://example.com"
    assert report.limitations == ""
    assert report.recommendations == ""


def test_research_report_normalizes_percentage_coverage():
    report = ResearchReport(
        title="t",
        summary="s",
        key_findings=[],
        evidence_coverage=100,
    )
    assert report.evidence_coverage == 1.0
