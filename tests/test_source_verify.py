from research_agent import evals
from research_agent.models import ResearchReport, Source


def _report_with(urls):
    return ResearchReport(
        title="t",
        summary="s",
        key_findings=[],
        sources=[Source(title=f"s{i}", url=u) for i, u in enumerate(urls)],
        limitations="",
        recommendations="",
    )


def test_verify_sources_counts_reachable(monkeypatch):
    class FakeResp:
        status_code = 200

    def fake_get(url, **kwargs):
        return FakeResp()

    monkeypatch.setattr("requests.get", fake_get)
    report = _report_with(["https://a.com/1", "https://b.com/2"])
    check = evals.verify_sources(report, timeout=1)
    assert check["reachable"] == 2
    assert check["total"] == 2
    assert check["failed"] == []


def test_verify_sources_marks_http_errors(monkeypatch):
    class FakeResp:
        status_code = 404

    def fake_get(url, **kwargs):
        return FakeResp()

    monkeypatch.setattr("requests.get", fake_get)
    report = _report_with(["https://a.com/1"])
    check = evals.verify_sources(report, timeout=1)
    assert check["reachable"] == 0
    assert check["failed"] == [("https://a.com/1", "HTTP 404")]


def test_verify_sources_handles_exceptions(monkeypatch):
    def fake_get(url, **kwargs):
        raise TimeoutError("slow")

    monkeypatch.setattr("requests.get", fake_get)
    report = _report_with(["https://a.com/1"])
    check = evals.verify_sources(report, timeout=1)
    assert check["reachable"] == 0
    assert check["failed"][0][1] == "TimeoutError"


def test_verify_sources_invalid_url():
    report = _report_with(["not-a-url"])
    check = evals.verify_sources(report, timeout=1)
    assert check["reachable"] == 0
    assert check["failed"][0][1] == "invalid URL"