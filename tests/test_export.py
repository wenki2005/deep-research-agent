from pathlib import Path

import pytest

from research_agent.export import find_cjk_font, report_to_pdf
from research_agent.models import KeyFinding, ResearchReport, Source


def _report():
    return ResearchReport(
        title="AI 医疗诊断测试报告",
        summary="这是一份用于测试 PDF 导出的中文摘要。",
        key_findings=[KeyFinding(topic="发现一", details="详细内容 12345")],
        sources=[Source(title="来源A", url="https://example.com/a")],
        limitations="局限说明",
        recommendations="建议说明",
    )


@pytest.mark.skipif(find_cjk_font() is None, reason="no CJK font on this machine")
def test_report_to_pdf(tmp_path):
    pdf = report_to_pdf(_report(), out_dir=Path(tmp_path))
    assert pdf.exists()
    assert pdf.suffix == ".pdf"
    assert pdf.stat().st_size > 0
    head = pdf.read_bytes()[:5]
    assert head == b"%PDF-"