"""Streamlit web UI for the Deep Research Agent.

Run:  uv run --extra web streamlit run app.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from research_agent.clarify import likely_vague, run_clarification
from research_agent.config import PROVIDERS
from research_agent.formatting import report_to_markdown
from research_agent.routing import RESEARCH_MODES
from research_agent.runner import (
    _run_config,
    build_model,
    run_research,
    save_report,
)

STAGE_LABELS = {
    "clarifying": "📋 检查是否需要澄清 ...",
    "planning": "🧭 规划研究策略 ...",
    "researching": "🔎 并行联网调研中 ...",
    "writing": "✍️ 撰写最终报告 ...",
}

st.set_page_config(page_title="Deep Research Agent", page_icon="🧠", layout="wide")
st.title("🧠 Deep Research Agent · 多智能体深度研究助手")
st.caption("Clarify → Planner → Researcher×N（并行）→ Writer ｜ 支持本地 Ollama / OpenAI 云端 / 任意 OpenAI 兼容端点")


def _effective_provider(choice: str) -> str | None:
    return choice if choice != "auto" else None


def _run_async(coro):
    return asyncio.run(coro)


with st.sidebar:
    st.header("⚙️ 配置")
    provider = st.selectbox("模型提供方", ["auto", *PROVIDERS], index=0)
    max_queries = st.slider("并行查询数", 1, 6, 3, help="越多越全面，但越慢")
    research_mode = st.selectbox("研究模式", ["auto", *RESEARCH_MODES], index=0)
    clarify = st.checkbox("问题模糊时先追问澄清", value=True)
    verify_sources = st.checkbox("生成后校验来源 URL", value=False)
    use_memory = st.checkbox("启用历史记忆（RAG）", value=False)

st.caption("报告默认展示可追溯原文摘录；引文匹配率不等于事实准确率，未核实内容不会标为已确认。")

question = st.text_area("研究问题", placeholder="例如：2026年开源大语言模型的发展趋势", height=100)

# ---- 澄清两步式状态 ----
if "clarify_qs" not in st.session_state:
    st.session_state.clarify_qs = None
if "answers" not in st.session_state:
    st.session_state.answers = {}

# 阶段 B：已有待澄清问题，展示输入框
if st.session_state.clarify_qs:
    st.subheader("📋 请先补充几个信息")
    for q in st.session_state.clarify_qs:
        st.session_state.answers[q] = st.text_input(q, key=f"ans_{q}")
    colA, colB = st.columns(2)
    if colA.button("✅ 确认并开始研究", type="primary", use_container_width=True):

        async def _cb(qs):
            return {q: st.session_state.answers.get(q, "").strip() for q in qs}

        st.session_state.answers = _run_async(_cb(st.session_state.clarify_qs))
        st.session_state.clarify_qs = None
        st.rerun()
    if colB.button("↩️ 直接研究（不回答）", use_container_width=True):
        st.session_state.answers = {}
        st.session_state.clarify_qs = None
        st.rerun()
    st.stop()

# 阶段 A：主按钮
run = st.button("🚀 开始研究", type="primary", use_container_width=True, disabled=not question.strip())

if run and question.strip():
    if clarify and likely_vague(question.strip()):
        with st.status("📋 检查是否需要澄清 ...", expanded=True):
            model = build_model(_effective_provider(provider) or "")
            rc = _run_config(model) if model is not None else _run_config(None)
            try:
                plan = _run_async(run_clarification(question.strip(), rc))
            except Exception as exc:  # noqa: BLE001 - continue without clarification
                st.warning(f"澄清检查失败，直接研究：{exc}")
                plan = None
        if plan is not None and plan.needs_clarification and plan.questions:
            st.session_state.clarify_qs = plan.questions
            st.session_state.answers = {}
            st.rerun()

    with st.status("准备中 ...", expanded=True) as status:

        def stage_cb(stage: str) -> None:
            status.update(label=STAGE_LABELS.get(stage, stage), state="running")

        try:
            report = _run_async(
                run_research(
                    question.strip(),
                    max_queries=max_queries,
                    provider=_effective_provider(provider),
                    verbose=False,
                    on_stage=stage_cb,
                    use_memory=use_memory,
                    research_mode=None if research_mode == "auto" else research_mode,
                )
            )
        except Exception as exc:  # noqa: BLE001 - UI boundary
            status.update(label="❌ 运行失败", state="error")
            st.error(str(exc))
            st.stop()

        status.update(label="✅ 完成", state="complete", expanded=False)

    if report.verification_state == "insufficient":
        st.warning("本次未取得足够的匹配引文，模型草稿已移除。请调整查询或检查搜索服务。")
    md = report_to_markdown(report, question.strip())
    st.markdown(md)

    path = save_report(report)
    st.success(f"报告已保存：`{path}`")
    st.download_button("⬇️ 下载 Markdown 报告", md, file_name=path.name, mime="text/markdown")

    try:
        from research_agent.export import report_to_pdf

        pdf_path = report_to_pdf(report)
        st.download_button(
            "⬇️ 下载 PDF 报告",
            pdf_path.read_bytes(),
            file_name=pdf_path.name,
            mime="application/pdf",
        )
    except Exception as exc:  # noqa: BLE001 - PDF export is optional in the UI
        st.warning(f"PDF 导出失败：{exc}")

    if verify_sources:
        from research_agent.evals import verify_sources

        with st.spinner("校验来源 URL ..."):
            check = verify_sources(report)
        st.subheader("🔗 来源校验")
        st.write(f"可访问 {check['reachable']}/{check['total']} 个来源")
        if check["failed"]:
            with st.expander("不可访问的来源"):
                for url, reason in check["failed"]:
                    st.write(f"- `{url}` （{reason}）")
