"""LLM-as-judge: score a research report with a judge model.

The judge prompt asks the model to rate the report on four 1-5 dimensions and
to return JSON only. `_extract_json` is kept separate for unit testing.
"""

from __future__ import annotations

import json
import re

JUDGE_SYSTEM = """你是一位严谨的研究报告评审专家。请按以下 4 个维度对报告打分（1-5 整数），并给出总评：
- relevance: 内容是否紧扣研究问题
- accuracy: 是否有具体事实/数据支撑、表述是否谨慎（是否可能编造）
- structure: 结构是否清晰完整（摘要/发现/来源/局限/建议）
- sources: 引用来源是否与内容相关、数量是否合理

只输出 JSON（不要输出任何其他内容）：
{"relevance": 3, "accuracy": 3, "structure": 4, "sources": 3, "total": 3.2, "comments": "一句话总评"}"""


def _extract_json(text: str | None) -> dict | None:
    """Extract the first JSON object from a model reply (tolerates code fences)."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(t[start : end + 1])
    except json.JSONDecodeError:
        return None


async def judge_report(
    question: str,
    report_md: str,
    provider: str | None = None,
    max_turns: int = 6,
) -> dict:
    """Run a judge agent over a rendered report; return score dict or error info."""
    from agents import Agent, RunConfig, Runner

    from .config import get_provider
    from .runner import build_model

    provider = (provider or get_provider()).lower()
    agent = Agent(name="Judge", instructions=JUDGE_SYSTEM)
    model = build_model(provider)
    run_config = RunConfig(model=model) if model is not None else RunConfig()

    user_input = f"研究问题：{question}\n\n研究报告：\n{report_md}"
    result = await Runner.run(agent, user_input, run_config=run_config, max_turns=max_turns)
    data = _extract_json(result.final_output)
    if data is None:
        return {"error": "judge output was not valid JSON", "raw": str(result.final_output)[:200]}

    def _score(key: str) -> int:
        try:
            return int(data.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    return {
        "relevance": _score("relevance"),
        "accuracy": _score("accuracy"),
        "structure": _score("structure"),
        "sources": _score("sources"),
        "total": round(float(data.get("total", 0) or 0), 2),
        "comments": str(data.get("comments", ""))[:200],
    }