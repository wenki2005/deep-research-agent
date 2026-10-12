"""Export a ResearchReport to a CJK-safe PDF using a local Windows font."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from xml.sax.saxutils import escape as _esc

from .models import ResearchReport

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
]


def find_cjk_font() -> str | None:
    """Locate a CJK-capable TrueType font on Windows."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def report_to_pdf(
    report: ResearchReport, out_dir: Path | None = None, font_path: str | None = None
) -> Path:
    """Render a report to PDF via reportlab; returns the output path."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font_path = font_path or find_cjk_font()
    if not font_path:
        raise RuntimeError("未找到中文字体（需要 simhei/msyh 等 Windows 字体）")
    try:
        pdfmetrics.registerFont(TTFont("CJK", font_path))
    except Exception as exc:
        raise RuntimeError(f"字体加载失败: {font_path}: {exc}") from exc

    out_dir = out_dir or (PROJECT_ROOT / "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", report.title.lower()).strip("-")[:60] or "report"
    timestamp = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{timestamp}-{slug}.pdf"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CJKTitle", parent=styles["Title"], fontName="CJK", fontSize=18, leading=24)
    h2 = ParagraphStyle("CJKH2", parent=styles["Heading2"], fontName="CJK", fontSize=13, leading=18, spaceBefore=10)
    body = ParagraphStyle("CJKBody", parent=styles["BodyText"], fontName="CJK", fontSize=10.5, leading=16)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    story = [Paragraph(_esc(report.title), title_style), Spacer(1, 4 * mm)]
    story.append(Paragraph("<b>摘要 / Summary</b>", h2))
    story.append(Paragraph(_esc(report.summary), body))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>核心发现 / Key findings</b>", h2))
    for f in report.key_findings:
        story.append(Paragraph(f"<b>{_esc(f.topic)} [{_esc(f.status)}/{_esc(f.confidence)}]</b>", body))
        story.append(Paragraph(_esc(f.details), body))
        for evidence in f.evidence:
            quote = evidence.evidence_quote or evidence.content
            story.append(Paragraph(f"Evidence: {_esc(quote)}", body))
            for url in evidence.source_urls:
                story.append(Paragraph(f"Source: {_esc(url)}", body))
        story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("<b>参考来源 / Sources</b>", h2))
    for s in report.sources:
        story.append(Paragraph(f"&bull; {_esc(s.title)} — {_esc(s.url)}", body))
    if report.limitations:
        story.append(Paragraph("<b>局限 / Limitations</b>", h2))
        story.append(Paragraph(_esc(report.limitations), body))
    if report.recommendations:
        story.append(Paragraph("<b>建议 / Recommendations</b>", h2))
        story.append(Paragraph(_esc(report.recommendations), body))
    story.append(Paragraph("<b>核验状态 / Verification</b>", h2))
    story.append(Paragraph(f"引文匹配覆盖率（非事实准确率）: {report.evidence_coverage:.0%}", body))
    if report.verification_summary:
        story.append(Paragraph(_esc(report.verification_summary), body))

    doc.build(story)
    return path
