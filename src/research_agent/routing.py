"""Research-mode routing and deterministic source-quality heuristics."""

from __future__ import annotations

from urllib.parse import urlparse

from .models import Finding, ResearchReport, Source
from .provenance import ProvenanceRegistry, SourceRecord, is_search_result_url

_HOT_MARKERS = ("新闻", "热点", "失踪", "拐卖", "绑架", "遇害", "最新消息", "舆情", "传闻")
_ACADEMIC_MARKERS = ("论文", "学术", "研究进展", "文献", "综述", "paper", "benchmark")
_POLICY_MARKERS = ("政策", "法规", "监管", "政府", "通知", "规划", "条例")
_TECH_MARKERS = ("代码", "框架", "模型", "api", "github", "技术", "架构", "开源")
_INDUSTRY_MARKERS = ("市场", "行业", "竞争", "公司", "岗位", "就业", "商业")
RESEARCH_MODES = ("standard", "hot_topic", "academic", "industry", "policy", "technical")


def infer_mode(question: str) -> str:
    """Select a research mode without spending an LLM call."""
    q = question.lower()
    if any(marker in q for marker in _HOT_MARKERS):
        return "hot_topic"
    if any(marker in q for marker in _ACADEMIC_MARKERS):
        return "academic"
    if any(marker in q for marker in _POLICY_MARKERS):
        return "policy"
    if any(marker in q for marker in _TECH_MARKERS):
        return "technical"
    if any(marker in q for marker in _INDUSTRY_MARKERS):
        return "industry"
    return "standard"


def mode_instruction(mode: str) -> str:
    """Return mode-specific research constraints for the agents."""
    instructions = {
        "hot_topic": (
            "这是热点事件核验模式：必须建立时间线，区分已确认事实、媒体报道未独立证实、"
            "社交媒体传闻和存在争议的信息；至少寻找两个相互独立的来源，禁止把单一传闻写成事实。"
        ),
        "academic": "这是学术模式：优先论文、大学、研究机构和原始实验报告，记录发表年份和研究限制。",
        "policy": "这是政策模式：优先政府、监管机构和官方文件，记录文件名称、发布日期和适用范围。",
        "technical": "这是技术模式：优先官方文档、GitHub 仓库、论文和可复现实验，记录版本和发布日期。",
        "industry": "这是行业模式：优先公司公告、监管文件、行业报告和招聘/统计数据，区分估算与官方统计。",
        "standard": "这是标准研究模式：覆盖背景、最新进展、数据、争议和下一步建议。",
    }
    return "\n\n研究模式约束：" + instructions.get(mode, instructions["standard"])


def _domain_type(url: str) -> str:
    host = urlparse(url).hostname or ""
    if host.endswith((".gov.cn", ".gov")):
        return "government"
    if host.endswith((".edu", ".edu.cn", ".ac.uk")) or host == "arxiv.org":
        return "academic"
    domains = {"media": ("reuters.com", "bbc.com", "bbc.co.uk", "thepaper.cn", "news.cn"),
               "social": ("weibo.com", "x.com", "twitter.com", "zhihu.com", "threads.com")}
    for kind, suffixes in domains.items():
        if any(host == d or host.endswith("." + d) for d in suffixes):
            return kind
    return "unknown"


def score_source_quality(source: Source) -> int:
    """Domain heuristic only. Never accept model-declared authority."""
    if is_search_result_url(source.url):
        return 0
    return {"government": 95, "academic": 85, "media": 70, "social": 30}.get(
        _domain_type(source.url), 45)


def source_from_record(record: SourceRecord) -> Source:
    source = Source(title=record.title or (urlparse(record.url).hostname or "来源"), url=record.url,
                    relevance="本次工具观察到的来源；不代表内容已证实",
                    source_type=_domain_type(record.url), published_at=record.published_at)
    source.quality_score = score_source_quality(source)
    return source


def enrich_source_quality(report: ResearchReport) -> ResearchReport:
    for source in report.sources:
        source.quality_score = score_source_quality(source)
    return report


def evidence_coverage(report: ResearchReport) -> float:
    """Quote coverage, not factual accuracy; only computed after provenance validation."""
    if not report.key_findings:
        return 0.0
    return sum(any(e.support_level != "unverified" and e.evidence_quote.strip() and e.source_urls
                   for e in f.evidence) for f in report.key_findings) / len(report.key_findings)


def _matching_level(quote: str, record: SourceRecord) -> str:
    if not quote:
        return "unverified"
    if quote in " ".join(record.content.split()):
        return "page_quote" if record.fetched else "snippet_quote"
    if quote in " ".join(record.snippet.split()):
        return "snippet_quote"
    return "unverified"


def apply_provenance_guard(report: ResearchReport, registry: ProvenanceRegistry) -> ResearchReport:
    """Project a model draft into an attributed-excerpt report, idempotently.

    There is no semantic fact verifier here: model prose is never certified by
    a substring match. Only matched quotations and observed metadata survive.
    """
    requested = [s.url for s in report.sources]
    used = []
    for index, key_finding in enumerate(report.key_findings, 1):
        evidence_list = []
        seen = set()
        for evidence in key_finding.evidence:
            quote = " ".join(evidence.evidence_quote.split())
            urls, levels = [], []
            for ref in evidence.source_urls:
                record = registry.get(ref)
                if record is None or is_search_result_url(record.url):
                    continue
                level = _matching_level(quote, record)
                if level != "unverified" and record.url not in urls:
                    urls.append(record.url)
                    levels.append(level)
            signature = (quote, tuple(urls))
            if not urls or signature in seen:
                continue
            seen.add(signature)
            used.extend(urls)
            # Replace the claim with the actual quote. Matching a quote does not
            # establish that the original claim, or even the source, is true.
            evidence_list.append(Finding(content=quote, evidence_quote=quote, source_urls=urls,
                                         status="reported_not_verified", confidence="low",
                                         support_level="page_quote" if all(x == "page_quote" for x in levels)
                                         else "snippet_quote"))
        key_finding.evidence = evidence_list
        key_finding.topic = f"资料核验 {index}"
        key_finding.confidence = "low"
        key_finding.status = "reported_not_verified" if evidence_list else "unknown"
        key_finding.details = (
            "以下仅为来源原文摘录，未独立证实，也不代表原模型结论成立。"
            if evidence_list else "本条未获得可匹配的原文证据，不能确认；无依据的模型草稿已移除。"
        )

    # Rebuild ALL metadata from tools, and include every actually cited source.
    records, seen_urls = [], set()
    for ref in used + requested + list(registry.urls()):
        record = registry.get(ref)
        if record and not is_search_result_url(record.url) and record.url not in seen_urls:
            seen_urls.add(record.url)
            records.append(record)
    # Stable order also makes repeated validation reproducible.
    records.sort(key=lambda r: r.source_id)
    report.sources = [source_from_record(r) for r in records]
    report.question = ""
    report.title = "研究资料核验报告"
    report.evidence_coverage = evidence_coverage(report)
    report.verification_state = ("insufficient" if report.evidence_coverage == 0 else
                                 "quoted" if report.evidence_coverage == 1 else "partial")
    report.verification_summary = build_verification_summary(report, registry)
    report.summary = report.verification_summary
    if not records:
        report.summary = "本次没有登记到任何真实搜索或网页抓取的可引用来源。" + report.summary
    report.limitations = "引文匹配只检查文本是否出现；来源独立性、语义支持及事实真伪尚未核实。"
    report.recommendations = "请打开对应来源查看上下文及发布日期；证据不足时补搜原始报道或官方材料。"
    return report


def build_verification_summary(report: ResearchReport, registry: ProvenanceRegistry) -> str:
    total = len(report.key_findings)
    backed = sum(bool(f.evidence) for f in report.key_findings)
    return (f"本次登记 {len(registry.records)} 个来源，{total} 项资料中 {backed} 项有匹配摘录。"
            f"引文匹配覆盖率 {report.evidence_coverage:.0%}，不等于事实准确率。"
            "不能把报告中的具体日期、数字或事件结论视为已确认事实；请依据下列来源继续核验。")
