"""Input guardrail that keeps low-quality prompts from wasting a research run."""

from __future__ import annotations

from typing import Any

from agents import GuardrailFunctionOutput, RunContextWrapper, input_guardrail
from pydantic import BaseModel

_GREETINGS = {"hi", "hello", "hey", "你好", "您好", "hola", "test", "yo"}

# Chinese carries much more information per character than English, so a low
# threshold (4 chars) works well for both languages.
_MIN_LENGTH = 4


class QuestionCheck(BaseModel):
    is_valid: bool
    reason: str


@input_guardrail
async def research_question_guardrail(
    context: RunContextWrapper[Any], agent: Any, input: str | list[Any]
) -> GuardrailFunctionOutput:
    """Reject empty, too-short or greeting-only inputs before any model call runs."""
    text = " ".join(input) if isinstance(input, list) else str(input)
    text = text.strip()

    if len(text) < _MIN_LENGTH:
        return GuardrailFunctionOutput(
            output_info=QuestionCheck(
                is_valid=False, reason=f"输入太短（至少 {_MIN_LENGTH} 个字符），请提供更具体的研究主题。"
            ),
            tripwire_triggered=True,
        )
    if text.lower() in _GREETINGS:
        return GuardrailFunctionOutput(
            output_info=QuestionCheck(is_valid=False, reason="输入看起来是问候语，不是研究主题。"),
            tripwire_triggered=True,
        )
    return GuardrailFunctionOutput(
        output_info=QuestionCheck(is_valid=True, reason="Looks like a valid research topic."),
        tripwire_triggered=False,
    )