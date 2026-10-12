import pytest

from research_agent.guardrails import research_question_guardrail

# `@input_guardrail` wraps the function into an InputGuardrail object;
# the raw async function lives in `.guardrail_function`.
GUARDRAIL_FN = research_question_guardrail.guardrail_function


@pytest.mark.asyncio
async def test_rejects_empty_input():
    out = await GUARDRAIL_FN(None, None, "")
    assert out.tripwire_triggered is True
    assert out.output_info.is_valid is False


@pytest.mark.asyncio
async def test_rejects_greeting():
    out = await GUARDRAIL_FN(None, None, "hi")
    assert out.tripwire_triggered is True


@pytest.mark.asyncio
async def test_rejects_too_short():
    out = await GUARDRAIL_FN(None, None, "你好")
    assert out.tripwire_triggered is True


@pytest.mark.asyncio
async def test_accepts_short_chinese_topic():
    out = await GUARDRAIL_FN(None, None, "ai岗位现状")
    assert out.tripwire_triggered is False
    assert out.output_info.is_valid is True


@pytest.mark.asyncio
async def test_accepts_valid_question():
    out = await GUARDRAIL_FN(None, None, "研究一下2026年人工智能在医疗诊断领域的最新进展")
    assert out.tripwire_triggered is False
    assert out.output_info.is_valid is True