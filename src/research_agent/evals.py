"""Evaluation scoring for the research pipeline.

Pure functions so they can be unit-tested without calling any model.
A case passes excerpt quality checks only when structure, sources, language, and
validated quote coverage are sufficient. This is NOT a factual accuracy score.
Keyword checks are informational (they do not fail a case).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import ResearchReport
from .routing import evidence_coverage

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

_UA = "Mozilla/5.0 (compatible; deep-research-agent/0.1)"


def load_cases(path: Path) -> list[dict]:
    """Load eval cases from a JSONL file (lines starting with # are comments)."""
    cases: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    return cases


def _score_structure(report: ResearchReport) -> dict[str, bool]:
    return {
        "title": bool(report.title.strip()),
        "summary": bool(report.summary.strip()),
        "key_findings>=3": len(report.key_findings) >= 3,
        "sources>=1": len(report.sources) >= 1,
        "limitations": bool(report.limitations.strip()),
        "recommendations": bool(report.recommendations.strip()),
    }


def _score_sources(report: ResearchReport) -> dict[str, int]:
    valid = 0
    seen: set[str] = set()
    for source in report.sources:
        url = (source.url or "").strip()
        if url.startswith(("http://", "https://")) and "." in url and url not in seen:
            seen.add(url)
            valid += 1
    return {"valid_sources": valid, "total_sources": len(report.sources)}


def _score_language(report: ResearchReport, question: str) -> bool:
    """Chinese questions must produce Chinese reports (catch language drift)."""
    if not _CJK_RE.search(question):
        return True  # non-Chinese question: not checked
    text = " ".join([report.summary, " ".join(f.details for f in report.key_findings)])
    return bool(_CJK_RE.search(text))


def _score_evidence(report: ResearchReport) -> dict[str, float | int]:
    total = len(report.key_findings)
    backed = sum(any(e.support_level != "unverified" and e.evidence_quote.strip() and e.source_urls
                     for e in finding.evidence) for finding in report.key_findings)
    confirmed = sum(1 for finding in report.key_findings if finding.status == "confirmed")
    return {
        "evidence_backed": backed,
        "finding_total": total,
        "evidence_coverage": backed / total if total else 0.0,
        "confirmed_findings": confirmed,
    }


def _score_keywords(report: ResearchReport, keywords: list[str]) -> tuple[list[str], list[str]]:
    text = " ".join(
        [
            report.title,
            report.summary,
            " ".join(f.topic + " " + f.details for f in report.key_findings),
        ]
    ).lower()
    found = [k for k in keywords if k.lower() in text]
    missing = [k for k in keywords if k.lower() not in text]
    return found, missing


def verify_sources(report: ResearchReport, timeout: float = 8.0) -> dict:
    """Check which source URLs are actually reachable (HTTP status < 400).

    Returns {"reachable": int, "total": int, "failed": [(url, reason)]}.
    """
    import requests

    reachable: list[str] = []
    failed: list[tuple[str, str]] = []
    for source in report.sources:
        url = (source.url or "").strip()
        if not url.startswith(("http://", "https://")):
            failed.append((url, "invalid URL"))
            continue
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers={"User-Agent": _UA},
                stream=True,
            )
            if resp.status_code < 400:
                reachable.append(url)
            else:
                failed.append((url, f"HTTP {resp.status_code}"))
        except Exception as exc:  # noqa: BLE001 - report any failure reason
            failed.append((url, type(exc).__name__))
    return {"reachable": len(reachable), "total": len(report.sources), "failed": failed}


def score_case(
    question: str,
    report: ResearchReport,
    elapsed_s: float,
    expected_keywords: list[str] | None = None,
) -> dict:
    """Score a single finished research run against quality checks."""
    structure = _score_structure(report)
    sources = _score_sources(report)
    language_ok = _score_language(report, question)
    evidence = _score_evidence(report)
    found, missing = _score_keywords(report, expected_keywords or [])

    structure_ok = all(structure.values())
    sources_ok = sources["valid_sources"] >= 1
    quote_coverage = evidence_coverage(report)
    quotes_ok = report.verification_state in {"partial", "quoted"} and quote_coverage >= 0.5
    # We have no independent semantic verifier. Never count model-confirmed prose as verified.
    unreviewed_claims = any(f.status == "confirmed" for f in report.key_findings)
    passed = structure_ok and sources_ok and language_ok and quotes_ok and not unreviewed_claims
    abstained = report.verification_state == "insufficient" and all(
        f.status == "unknown" and not f.evidence for f in report.key_findings)


    return {
        "question": question,
        "elapsed_s": round(elapsed_s, 1),
        "passed": passed,
        "structure_ok": structure_ok,
        "quote_quality_ok": quotes_ok,
        "abstained": abstained,
        "factual_accuracy_verified": False,
        "sources_ok": sources_ok,
        "language_ok": language_ok,
        "evidence_coverage": round(float(evidence["evidence_coverage"]), 2),
        "evidence_backed": evidence["evidence_backed"],
        "confirmed_findings": evidence["confirmed_findings"],
        "keyword_hits": len(found),
        "keyword_total": len(found) + len(missing),
        "structure": structure,
        "valid_sources": sources["valid_sources"],
        "total_sources": sources["total_sources"],
        "keywords_found": found,
        "keywords_missing": missing,
    }


def error_case(question: str, elapsed_s: float, error: str) -> dict:
    """Build a failing result for a case that raised an exception."""
    return {
        "question": question,
        "elapsed_s": round(elapsed_s, 1),
        "passed": False,
        "structure_ok": False,
        "sources_ok": False,
        "language_ok": False,
        "keyword_hits": 0,
        "keyword_total": 0,
        "error": error,
    }


def summarize(results: list[dict]) -> dict:
    """Aggregate per-case results into an overall summary."""
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    structure_ok = sum(1 for r in results if r.get("structure_ok"))
    sources_ok = sum(1 for r in results if r.get("sources_ok"))
    language_ok = sum(1 for r in results if r.get("language_ok"))
    errors = sum(1 for r in results if "error" in r)
    elapsed = [r["elapsed_s"] for r in results]
    keyword_hits = sum(r.get("keyword_hits", 0) for r in results)
    keyword_total = sum(r.get("keyword_total", 0) for r in results)
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        "structure_ok": structure_ok,
        "quote_quality_ok": sum(bool(r.get("quote_quality_ok")) for r in results),
        "abstained": sum(bool(r.get("abstained")) for r in results),
        "factual_accuracy_verified": False,
        "sources_ok": sources_ok,
        "language_ok": language_ok,
        "errors": errors,
        "avg_elapsed_s": round(sum(elapsed) / len(elapsed), 1) if elapsed else 0.0,
        "keyword_hit_rate": round(keyword_hits / keyword_total * 100, 1) if keyword_total else None,
    }
