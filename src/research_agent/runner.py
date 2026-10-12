"""Orchestration layer: (clarify) -> (memory recall) -> plan -> research -> write -> save."""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from agents import RunConfig, Runner, set_tracing_disabled
from rich.console import Console

from .agents import build_agents
from .clarify import likely_vague, refine_with_answers, run_clarification
from .config import (
    PROVIDER_LOCAL,
    PROVIDER_OPENAI,
    get_local_base_url,
    get_local_model,
    get_openai_base_url,
    get_openai_model,
    get_provider,
)
from .formatting import notes_to_context, report_to_markdown
from .memory import MemoryStore
from .models import ResearchNotes, ResearchReport
from .provenance import current, isolated_run
from .routing import apply_provenance_guard, enrich_source_quality, infer_mode
from .tools import _research_sources

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

AskQuestions = Callable[[list[str]], Awaitable[dict[str, str]]]

RETRY_PROMPT = """你上一次针对下面的查询没有找到任何数据（web_search 没有返回结果，或来源为空）。

请重新开始研究：换一种措辞、换同义词、或切换语言（中文<->English）重新搜索，
至少尝试 2-3 个不同的查询；对最相关的来源用 fetch_page 阅读正文。
最后返回完整的 ResearchNotes：findings 至少 1 条、sources 至少 1 个。
不要放弃，也不要编造。

原查询：{query}"""

EVIDENCE_RETRY_PROMPT = """这份研究报告的证据链不完整。请基于研究笔记重新撰写报告：
每一条核心发现都必须复制至少一条研究笔记中的 evidence_quote，并在 evidence
中填写对应 source_urls；明确区分 confirmed、reported_not_verified、rumor、disputed、unknown。
不能创造笔记中没有的数字、机构确认或来源。

研究问题和笔记如下：
{context}"""


def build_model(provider: str) -> object | None:
    """Return a Model for the given provider, or None to use the SDK default."""
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    if provider == PROVIDER_LOCAL:
        client = AsyncOpenAI(base_url=get_local_base_url(), api_key="ollama")
        return OpenAIChatCompletionsModel(model=get_local_model(), openai_client=client)

    if provider == PROVIDER_OPENAI:
        base_url = get_openai_base_url()
        if base_url:
            model = get_openai_model()
            if not model:
                raise RuntimeError(
                    "OPENAI_MODEL must be set when using a custom OPENAI_BASE_URL."
                )
            client = AsyncOpenAI(base_url=base_url, api_key=os.getenv("OPENAI_API_KEY"))
            return OpenAIChatCompletionsModel(model=model, openai_client=client)

    return None


def _run_config(model: object | None) -> RunConfig:
    if model is None:
        return RunConfig()
    return RunConfig(model=model)  # type: ignore[arg-type]


def notes_are_empty(notes: ResearchNotes | None) -> bool:
    """True when a researcher produced neither findings nor sources."""
    return notes is None or (not notes.findings and not notes.sources)


async def _research_one(
    researcher, query: str, run_config: RunConfig, max_turns: int
) -> ResearchNotes:
    """Run one researcher; if it came back empty, retry once with explicit guidance."""
    # Deterministic preflight: local models sometimes skip tool calls and invent
    # a polished report. Search and extract first so every run has real
    # provenance even when the model ignores the tools.
    preflight = await asyncio.to_thread(_research_sources, query, 4, 1800)
    researcher_input = (
        f"原始研究查询：{query}\n\n"
        "编排器已经执行了强制搜索和正文提取。以下是本次运行的真实预检资料，"
        "只能引用其中出现的 URL 和原文，不得创造来源：\n"
        f"{preflight}\n\n"
        "请基于这些资料继续研究；如资料不足，标记为 reported_not_verified 或 unknown。"
        "source_urls 必须填写预检资料中显示的 SRC-xxx 编号，evidence_quote 必须复制原文摘录。"
    )
    result = await Runner.run(researcher, researcher_input, run_config=run_config, max_turns=max_turns)
    notes = result.final_output
    if notes_are_empty(notes):
        console.print(f"  [retry] 搜索结果为空，重试查询: {query}")
        retry = await Runner.run(
            researcher,
            RETRY_PROMPT.format(query=query) + f"\n\n强制预检资料：\n{preflight}",
            run_config=run_config,
            max_turns=max_turns,
        )
        notes = retry.final_output
    return notes


def _recall_history(question: str, verbose: bool) -> tuple[str, MemoryStore | None]:
    """Retrieve relevant past reports from vector memory; never raises."""
    try:
        store = MemoryStore()
        hits = store.search(question, k=3)
        if not hits:
            return "", store
        history = "\n\n已知历史研究（仅供参考，注意时效性）：\n" + "\n\n".join(
            h["document"][:800] for h in hits
        )
        if verbose:
            console.print(f"[cyan]🧠 记忆命中 {len(hits)} 条历史研究[/]")
        return history, store
    except Exception as exc:  # noqa: BLE001 - memory must never block research
        if verbose:
            console.print(f"[yellow]⚠ 记忆检索失败（已忽略）: {exc}[/]")
        return "", None


@isolated_run
async def run_research(
    question: str,
    max_queries: int = 4,
    provider: str | None = None,
    verbose: bool = True,
    on_stage: Callable[[str], None] | None = None,
    ask_questions: AskQuestions | None = None,
    use_memory: bool = False,
    research_mode: str | None = None,
) -> ResearchReport:
    """Run the full multi-agent research pipeline and return the final report.

    on_stage: optional callback invoked with "clarifying" / "planning" /
        "researching" / "writing" so UI layers can surface progress.
    ask_questions: optional async callback for human-in-the-loop clarification.
    use_memory: recall relevant past reports (RAG) and store the new one.
    """
    provider = (provider or get_provider()).lower()

    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to .env (see .env.example) or run with --provider local."
        )

    set_tracing_disabled(provider != "openai")

    model = build_model(provider)
    run_config = _run_config(model)
    provenance = current()
    assert provenance is not None

    # Stage 0: optional clarifying questions (human-in-the-loop).
    if ask_questions is not None and likely_vague(question):
        if on_stage:
            on_stage("clarifying")
        if verbose:
            console.print("[bold cyan]📋 检查问题是否需要澄清 ...[/]")
        plan = await run_clarification(question, run_config)
        if plan.needs_clarification and plan.questions:
            if verbose:
                console.print("[bold yellow]需要先确认几个问题:[/]")
                for q in plan.questions:
                    console.print(f"   ? {q}")
            answers = await ask_questions(plan.questions)
            question = refine_with_answers(question, answers)

    mode = research_mode or infer_mode(question)
    agents = build_agents(question, mode, provenance)

    # Stage 1: recall relevant history from vector memory (RAG).
    history, store = ("", None)
    if use_memory:
        history, store = _recall_history(question, verbose)

    if on_stage:
        on_stage("planning")
    if verbose:
        console.print(f"[bold blue]🧭 规划中 / Planning:[/] {question}")

    planner_input = question + history
    plan_result = await Runner.run(
        agents.planner, planner_input, run_config=run_config, max_turns=15
    )
    plan = plan_result.final_output
    queries = (plan.queries or [question])[: max(1, max_queries)]

    if on_stage:
        on_stage("researching")
    if verbose:
        console.print(f"[bold yellow]🔎 研究中 / Researching:[/] {len(queries)} 个并行查询")
        for q in queries:
            console.print(f"   • {q}")

    tasks = [_research_one(agents.researcher, q, run_config, 15) for q in queries]
    notes: list[ResearchNotes] = await asyncio.gather(*tasks)

    if on_stage:
        on_stage("writing")
    if verbose:
        console.print("[bold magenta]✍️  撰写中 / Writing:[/] 汇总为最终报告 ...")

    context = notes_to_context(question, notes, provenance)
    writer_result = await Runner.run(
        agents.writer, context, run_config=run_config, max_turns=15
    )
    report = writer_result.final_output
    report.research_mode = mode
    report = enrich_source_quality(report)
    report = apply_provenance_guard(report, provenance)

    # Bounded repair: obtain fresh material, then keep the better guarded candidate.
    if report.evidence_coverage < 0.5:
        if verbose:
            console.print("[yellow]引文不足，补搜原问题并尝试一次重写 ...[/]")
        extra = await asyncio.to_thread(_research_sources, question, 4, 4000)
        if provenance.records:
            try:
                context = notes_to_context(question, notes, provenance) + "\n补充检索：\n" + extra
                repair = await Runner.run(
                    agents.writer, EVIDENCE_RETRY_PROMPT.format(context=context),
                    run_config=run_config, max_turns=15,
                )
                candidate = apply_provenance_guard(repair.final_output, provenance)
                candidate.research_mode = mode
                if report_quality(candidate) > report_quality(report):
                    report = candidate
            except Exception:  # noqa: BLE001 - retain the first guarded report on repair failure
                if verbose:
                    console.print("[yellow]补写未完成，保留首次核验结果。[/]")
        report = apply_provenance_guard(report, provenance)

    report.question = question

    # Stage 6: persist the new report into vector memory for future runs.
    if store is not None and report.verification_state == "quoted":
        try:
            store.add_report(report)
            if verbose:
                console.print("[green]🧠 新报告已存入记忆库[/]")
        except Exception as exc:  # noqa: BLE001 - memory must never break the run
            if verbose:
                console.print(f"[yellow]⚠ 报告写入记忆失败（已忽略）: {exc}[/]")

    return report


def report_quality(report: ResearchReport) -> tuple[float, int]:
    return report.evidence_coverage, sum(
        e.support_level == "page_quote" for f in report.key_findings for e in f.evidence)


def save_report(report: ResearchReport, reports_dir: Path | None = None) -> Path:
    """Persist the report as a timestamped Markdown file; returns its path."""
    reports_dir = reports_dir or (PROJECT_ROOT / "reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", (report.question or report.title).lower()).strip("-")[:60]
    slug = slug or "report"
    timestamp = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    path = reports_dir / f"{timestamp}-{slug}-{uuid.uuid4().hex[:8]}.md"
    path.write_text(report_to_markdown(report), encoding="utf-8")
    return path
