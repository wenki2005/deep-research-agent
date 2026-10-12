"""Offline audit probes. `reproduced: true` means a defect exists, NOT test success.

No network or LLM calls. Run with .venv/Scripts/python.exe evals/audit_20260908.py.
Not part of pytest: after fixes, reproduced should turn false.
"""

from __future__ import annotations

import json
from contextvars import Context
from pathlib import Path
from unittest.mock import patch

from research_agent import tools
from research_agent.evals import score_case
from research_agent.formatting import report_to_markdown
from research_agent.models import Finding, KeyFinding, ResearchReport, Source
from research_agent.provenance import ProvenanceRegistry, current, set_current, start_run
from research_agent.routing import apply_provenance_guard

RESULTS = []
URL = "https://example.com/article"
QUOTE = "The agency has not confirmed this event."


def record(case, reproduced, **observed):
    RESULTS.append({"case": case, "reproduced": bool(reproduced), "observed": observed})


def registry():
    reg = ProvenanceRegistry()
    reg.register_search_results([{"href": URL, "title": "Personal blog", "content": QUOTE}], "fixture")
    return reg


def report(evidence=None, summary="The event has been officially confirmed."):
    return ResearchReport(
        title="Synthetic audit only",
        summary=summary,
        key_findings=[
            KeyFinding(
                topic="Event",
                details="The agency confirmed this event.",
                status="confirmed",
                confidence="high",
                evidence=evidence or [],
            )
        ],
    )


def main():
    reg = registry()
    bad_link = "https://example.invalid/invented-official-statement"
    result = apply_provenance_guard(report(summary=f"Official confirmation: {bad_link}"), reg)
    record(
        "A01_unverified_prose_survives",
        bad_link in report_to_markdown(result),
        fake_link_visible=bad_link in report_to_markdown(result),
        unsupported_details_visible="The agency confirmed this event." in result.key_findings[0].details,
        coverage=result.evidence_coverage,
    )

    evidence = Finding(
        content="The agency confirmed this event.",
        source_urls=[URL],
        evidence_quote=QUOTE,
        status="confirmed",
        confidence="high",
    )
    result = apply_provenance_guard(report([evidence]), reg)
    record(
        "A02_contradictory_quote_accepted",
        result.key_findings[0].status == "confirmed",
        status=result.key_findings[0].status,
        coverage=result.evidence_coverage,
    )

    candidate = report()
    candidate.sources = [
        Source(
            title="Official agency announcement", url=URL, source_type="official", published_at="2099-01-01"
        )
    ]
    result = apply_provenance_guard(candidate, reg)
    record(
        "A03_model_metadata_trusted",
        result.sources[0].quality_score == 90,
        source=result.sources[0].model_dump(),
    )

    second = "https://example.org/unrelated"
    reg.register_search_results([{"href": second, "content": "Unrelated weather report."}], "fixture")
    evidence = Finding(content="claim", source_urls=[URL, second], evidence_quote=QUOTE)
    result = apply_provenance_guard(report([evidence]), reg)
    record(
        "A04_only_first_source_quote_checked",
        second in result.key_findings[0].evidence[0].source_urls,
        retained_urls=result.key_findings[0].evidence[0].source_urls,
    )

    reg = ProvenanceRegistry()
    search_page = "https://www.baidu.com/s?wd=example"
    reg.register_search_results([{"href": search_page}], "fixture")
    before = len(reg.records)
    reg.mark_fetched(search_page, "Search engine results text")
    result = apply_provenance_guard(report(), reg)
    record(
        "A05_fetch_reintroduces_search_page",
        any(s.url == search_page for s in result.sources),
        records_after_search=before,
        records_after_fetch=len(reg.records),
        rendered_sources=[s.url for s in result.sources],
    )

    reg = start_run()
    with (
        patch.object(tools, "get_tavily_api_key", return_value="fixture-key"),
        patch.object(tools, "_tavily_search", return_value=[{"href": URL, "title": "News", "body": QUOTE}]),
    ):
        output = tools._news_search("fixture")
    record(
        "A06_news_not_registered",
        URL in output and not reg.contains(URL),
        returned_url=URL in output,
        registered=len(reg.records),
    )
    set_current(None)

    with (
        patch.object(tools, "get_tavily_api_key", return_value="fixture-key"),
        patch.object(tools, "_tavily_search", return_value=[]),
        patch.object(tools, "_search_raw", return_value=([], "empty")),
    ):
        error = ""
        try:
            tools._news_search("fixture")
        except UnboundLocalError as exc:
            error = type(exc).__name__
    record("A07_empty_news_crash", error == "UnboundLocalError", error=error)

    calls = []

    def poor(*args):
        calls.append("poor")
        return [{"href": search_page, "title": "Search page", "body": "No article"}]

    def good(*args):
        calls.append("good")
        return [{"href": URL, "title": "Article", "body": QUOTE}]

    reg = start_run()
    with (
        patch.object(tools, "_active_backends", return_value=["poor", "good"]),
        patch.dict(tools._BACKENDS, {"poor": poor, "good": good}),
    ):
        tools._search_raw("fixture")
    record(
        "A08_invalid_results_stop_fallback",
        calls == ["poor"] and not reg.records,
        backends_called=calls,
        registered=len(reg.records),
    )
    set_current(None)

    reg = start_run()
    foreign = Context().run(current)
    record(
        "A09_empty_context_inherits_global_registry",
        foreign is reg,
        unrelated_empty_context_sees_active_run=foreign is reg,
    )
    set_current(None)

    candidate = report(summary="Synthetic report")
    candidate.key_findings *= 3
    candidate.sources = [Source(title="Observed", url=URL)]
    candidate.limitations = "No verification"
    candidate.recommendations = "Check sources"
    result = apply_provenance_guard(candidate, registry())
    score = score_case("Audit report", result, 0)
    record(
        "A10_zero_evidence_passes_eval",
        score["passed"] and score["evidence_coverage"] == 0,
        passed=score["passed"],
        evidence_coverage=score["evidence_coverage"],
    )

    class Response:
        text = ""

        def raise_for_status(self):
            pass

    try:
        with patch.object(tools.requests, "get", return_value=Response()) as request:
            tools._bing_search("fixture", 2, recency="week")
            week = request.call_args.kwargs.copy()
            tools._bing_search("fixture", 2, recency="any")
            any_time = request.call_args.kwargs.copy()
        record("A11_bing_recency_ignored", week == any_time, same_request_parameters=week == any_time)
    except ValueError:
        record("A11_bing_recency_ignored", False, unsupported_filter_explicitly_rejected=True)

    reg = registry()
    first = apply_provenance_guard(report(), reg)
    original = first.summary
    second_result = apply_provenance_guard(first, reg)
    record(
        "A12_guard_not_idempotent",
        original != second_result.summary,
        initial_summary_length=len(original),
        twice_summary_length=len(second_result.summary),
    )

    with (
        patch.object(tools, "get_tavily_api_key", return_value="fixture-key"),
        patch.object(tools.requests, "post") as request,
    ):
        request.return_value.json.return_value = {"results": []}
        tools._tavily_search("fixture", 2, recency="year")
        payload = request.call_args.kwargs["json"]
    record(
        "A13_year_recency_silently_ignored",
        "time_range" not in payload and "days" not in payload,
        time_range=payload.get("time_range"),
        days=payload.get("days"),
    )

    path = Path(__file__).resolve().parents[1] / "docs" / "audit-2026-09-08-after.json"
    path.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(RESULTS, ensure_ascii=True, indent=2))
    print(f"Reproduced: {sum(r['reproduced'] for r in RESULTS)}/{len(RESULTS)}")


if __name__ == "__main__":
    main()
