"""Run the research pipeline over eval cases and produce a scored report.

Usage (from the project root):
    uv run python evals/run_evals.py --limit 3 --max-queries 2
    uv run python evals/run_evals.py --tags tech
    uv run python evals/run_evals.py --provider openai --max-queries 4
    uv run python evals/run_evals.py --limit 2 --judge --verify-sources
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

# Ensure Chinese output displays correctly even when piped or redirected.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - not available on some platforms  # noqa: BLE001, S110
    pass

# Make `src` importable when run as a plain script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from research_agent import evals as ev
from research_agent.formatting import report_to_markdown
from research_agent.judge import judge_report
from research_agent.runner import run_research, save_report

EVALS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVALS_DIR / "results"
console = Console()


async def run_one(
    case: dict,
    max_queries: int,
    provider: str,
    out_dir: Path,
    do_judge: bool,
    do_verify: bool,
) -> dict:
    question = case["question"]
    start = time.perf_counter()
    try:
        report = await run_research(
            question, max_queries=max_queries, provider=provider, verbose=False
        )
        elapsed = time.perf_counter() - start
        result = ev.score_case(question, report, elapsed, case.get("expected_keywords"))
        result["report_path"] = str(save_report(report, reports_dir=out_dir))

        if do_verify:
            result["source_check"] = ev.verify_sources(report)
        if do_judge:
            md = report_to_markdown(report, question)
            result["judge"] = await judge_report(question, md, provider)
        return result
    except Exception as exc:  # noqa: BLE001 - eval boundary: keep going on failure
        elapsed = time.perf_counter() - start
        return ev.error_case(question, elapsed, str(exc)[:300])


async def run_all(
    cases: list[dict],
    max_queries: int,
    provider: str,
    out_dir: Path,
    do_judge: bool,
    do_verify: bool,
) -> list[dict]:
    results: list[dict] = []
    for i, case in enumerate(cases, 1):
        console.print(
            f"[bold cyan][{i}/{len(cases)}][/] 评估中: {case['question']} "
            f"({case.get('tags', [])})"
        )
        result = await run_one(case, max_queries, provider, out_dir, do_judge, do_verify)
        mark = "[green]PASS[/green]" if result["passed"] else "[red]FAIL[/red]"
        extra = ""
        if result.get("judge") and "total" in result["judge"]:
            extra += f" judge={result['judge']['total']}"
        if result.get("source_check"):
            extra += f" 来源可达={result['source_check']['reachable']}/{result['source_check']['total']}"
        console.print(f"  -> {mark} 用时 {result['elapsed_s']}s{extra}")
        results.append(result)
    return results


def _result_table(results: list[dict]) -> Table:
    table = Table(title="逐用例评估结果")
    table.add_column("#", justify="right")
    table.add_column("问题")
    table.add_column("结果", justify="center")
    table.add_column("结构", justify="center")
    table.add_column("来源", justify="center")
    table.add_column("语言", justify="center")
    table.add_column("关键词", justify="center")
    table.add_column("耗时(s)", justify="right")
    for i, r in enumerate(results, 1):
        kw = (
            f"{r.get('keyword_hits', 0)}/{r.get('keyword_total', 0)}"
            if r.get("keyword_total", 0) > 0
            else "-"
        )
        table.add_row(
            str(i),
            r["question"][:24],
            "PASS" if r["passed"] else "FAIL",
            "OK" if r.get("structure_ok") else "X",
            "OK" if r.get("sources_ok") else "X",
            "OK" if r.get("language_ok") else "X",
            kw,
            str(r["elapsed_s"]),
        )
    return table


def _render_markdown(results: list[dict], summary: dict, meta: dict) -> str:
    lines = [
        "# Eval 报告",
        "",
        f"- 时间：{meta['time']}",
        f"- Provider：{meta['provider']}",
        f"- max_queries：{meta['max_queries']}",
        f"- LLM-as-judge：{'开启' if meta.get('judge') else '关闭'}",
        f"- 来源可访问性校验：{'开启' if meta.get('verify_sources') else '关闭'}",
        f"- 用例数：{summary['total']}",
        "",
        "## 总览",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
        f"| 通过数 / 总数 | {summary['passed']} / {summary['total']} |",
        f"| 通过率 | {summary['pass_rate']}% |",
        f"| 结构完整 | {summary['structure_ok']} / {summary['total']} |",
        f"| 来源有效 | {summary['sources_ok']} / {summary['total']} |",
        f"| 语言一致 | {summary['language_ok']} / {summary['total']} |",
        f"| 运行出错 | {summary['errors']} |",
        f"| 平均耗时 | {summary['avg_elapsed_s']}s |",
        (
            f"| 关键词命中率 | {summary['keyword_hit_rate']}% |"
            if summary["keyword_hit_rate"] is not None
            else "| 关键词命中率 | - |"
        ),
        "",
        "## 逐用例",
        "",
    ]
    for i, r in enumerate(results, 1):
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        lines.append(f"### {i}. {r['question']} — {status}（{r['elapsed_s']}s）")
        if "error" in r:
            lines.append(f"\n- 错误：{r['error']}")
            continue
        lines.append("- 结构检查：")
        for k, v in r["structure"].items():
            lines.append(f"  - {k}: {'OK' if v else 'X'}")
        lines.append(f"- 来源：{r['valid_sources']}/{r['total_sources']} 个有效 URL")
        if r.get("keywords_missing"):
            lines.append(f"- 关键词未命中：{', '.join(r['keywords_missing'])}")
        if r.get("source_check"):
            sc = r["source_check"]
            lines.append(f"- 来源可访问性：{sc['reachable']}/{sc['total']} 可达")
            for url, reason in sc["failed"]:
                lines.append(f"  - ❌ {url} （{reason}）")
        if r.get("judge"):
            j = r["judge"]
            if "error" in j:
                lines.append(f"- Judge 评分失败：{j['error']}")
            else:
                lines.append(
                    f"- Judge 评分：relevance {j['relevance']} / accuracy {j['accuracy']} / "
                    f"structure {j['structure']} / sources {j['sources']} / total {j['total']}"
                )
                if j.get("comments"):
                    lines.append(f"  - 评语：{j['comments']}")
        lines.append(f"- 报告文件：`{r.get('report_path', '')}`")
        lines.append("")
    lines += [
        "## 人工核验清单",
        "",
        "自动化只能检查结构与 URL 格式。请抽检 2-3 份报告，人工确认：",
        "1. 来源 URL 是否真实存在、可打开；",
        "2. 关键数字/结论是否与来源一致（防幻觉）；",
        "3. 报告语言与问题语言是否一致、是否易读。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_evals", description="运行研究流水线评估并生成评分报告"
    )
    parser.add_argument("--cases", default=str(EVALS_DIR / "cases.jsonl"))
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 个用例")
    parser.add_argument("--tags", nargs="*", default=[], help="按标签过滤，如 --tags tech")
    parser.add_argument("--max-queries", type=int, default=3, help="每个用例的并行查询数")
    parser.add_argument("--provider", choices=["openai", "local"], default=None, help="模型提供方")
    parser.add_argument(
        "--judge", action="store_true", help="用 LLM-as-judge 给每份报告打分（较慢）"
    )
    parser.add_argument(
        "--verify-sources", action="store_true", help="实际请求每个来源 URL 校验可访问性"
    )
    args = parser.parse_args(argv)

    cases = ev.load_cases(Path(args.cases))
    if args.tags:
        cases = [c for c in cases if set(args.tags) & set(c.get("tags", []))]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        console.print("[red]没有符合条件的用例。[/red]")
        return 1

    timestamp = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    results = asyncio.run(
        run_all(cases, args.max_queries, args.provider, out_dir, args.judge, args.verify_sources)
    )
    summary = ev.summarize(results)

    console.print()
    console.print(_result_table(results))
    console.print(
        f"\n[bold]通过率:[/] {summary['pass_rate']}%  "
        f"[bold]平均耗时:[/] {summary['avg_elapsed_s']}s  "
        f"[bold]运行出错:[/] {summary['errors']}"
    )

    meta = {
        "time": timestamp,
        "provider": args.provider or "auto",
        "max_queries": args.max_queries,
        "judge": args.judge,
        "verify_sources": args.verify_sources,
    }
    report_path = out_dir / "eval-report.md"
    report_path.write_text(_render_markdown(results, summary, meta), encoding="utf-8")
    console.print(f"\n[green]评估报告已保存:[/green] {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())