"""Command-line interface: research "<question>"."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from agents.exceptions import InputGuardrailTripwireTriggered
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

from .config import PROVIDERS
from .formatting import report_to_markdown
from .routing import RESEARCH_MODES
from .runner import run_research, save_report

# Ensure Chinese output displays correctly even when piped or redirected.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - not available on some platforms  # noqa: BLE001, S110
    pass

console = Console()


async def _ask_questions(questions: list[str]) -> dict[str, str]:
    """Interactive clarifying-questions flow (human-in-the-loop)."""
    answers: dict[str, str] = {}
    console.print("\n[bold yellow]📋 为了研究得更准确，请先回答几个问题（直接回车可跳过）:[/]")
    for q in questions:
        ans = Prompt.ask(q, default="")
        if ans.strip():
            answers[q] = ans.strip()
    return answers


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research",
        description="Multi-agent deep research assistant (多智能体深度研究助手)",
    )
    parser.add_argument("question", nargs="*", help="研究问题（留空则交互式输入）")
    parser.add_argument(
        "--max-queries",
        type=int,
        default=4,
        help="并行搜索查询数量上限（默认 4）",
    )
    parser.add_argument(
        "--research-mode",
        choices=RESEARCH_MODES,
        default=None,
        help="研究模式（默认按问题自动判断：hot_topic/academic/policy/technical/industry）",
    )
    parser.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=None,
        help="模型提供方（默认自动选择：有 OPENAI_API_KEY 用 openai，否则用 local）",
    )
    parser.add_argument(
        "--no-clarify",
        action="store_true",
        help="跳过追问澄清（问题模糊时也不询问，直接研究）",
    )
    parser.add_argument(
        "--use-memory",
        action="store_true",
        help="启用向量记忆（检索历史报告辅助研究，并存入新报告）",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="同时导出 PDF 报告",
    )
    parser.add_argument("--no-save", action="store_true", help="只在终端显示，不保存报告文件")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    question = " ".join(args.question).strip()
    if not question:
        question = console.input("[bold cyan]请输入研究问题: [/]").strip()
    if not question:
        console.print("[red]未输入研究问题。[/red]")
        return 1

    # 交互式终端才追问澄清；管道/非交互环境跳过。
    ask_questions = None
    if not args.no_clarify and sys.stdin.isatty():
        ask_questions = _ask_questions

    try:
        report = asyncio.run(
            run_research(
                question,
                max_queries=args.max_queries,
                provider=args.provider,
                verbose=True,
                ask_questions=ask_questions,
                use_memory=args.use_memory,
                research_mode=args.research_mode,
            )
        )
    except InputGuardrailTripwireTriggered as exc:
        reason = getattr(exc.guardrail_result.output.output_info, "reason", "输入未通过检查")
        console.print(f"[red]输入被护栏拦截 / Guardrail blocked:[/red] {reason}")
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        console.print(f"[red]运行失败 / Run failed:[/red] {exc}")
        return 1

    console.print()
    console.print(Markdown(report_to_markdown(report, question)))

    if not args.no_save:
        path = save_report(report)
        console.print(f"\n[green]报告已保存 / Report saved to:[/green] {path}")
        if args.pdf:
            try:
                from .export import report_to_pdf

                pdf = report_to_pdf(report)
                console.print(f"[green]PDF 已导出:[/green] {pdf}")
            except Exception as exc:  # noqa: BLE001 - PDF export must not fail the run
                console.print(f"[yellow]PDF 导出失败:[/yellow] {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
