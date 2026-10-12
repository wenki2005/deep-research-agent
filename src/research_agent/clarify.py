"""Clarifying-questions stage (human-in-the-loop) before research starts.

Follows the deep-research pattern: if the user's question is ambiguous, ask 1-2
short clarifying questions and fold the answers back into the research question.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from agents import Agent, RunConfig, Runner

from .agents import language_instruction
from .models import ClarificationPlan

CLARIFIER_INSTRUCTIONS = """You are a research intake specialist.

Decide whether a research question is clear enough to research immediately.

STRICT RULE: if the question names a concrete topic (a noun phrase that can be
searched) and a hint of scope (time period / region / industry), then it is CLEAR:
set needs_clarification=false and questions=[].

Ask 1-2 short clarifying questions ONLY when the question is genuinely vague:
- the actual topic is missing (e.g. "help me research" - research what?)
- too broad with no focus (e.g. just "AI")
- scope is missing and the topic alone is too ambiguous to act on

Examples:
- "2026 trends of open-source LLMs" -> CLEAR -> no questions
- "AI job market" -> topic clear, scope missing -> ask at most 2 questions
- "help me look something up" -> vague -> ask 1-2 questions

Return a `ClarificationPlan`. questions must be 1-2 items maximum, each under 20 words.
"""



_VAGUE_MARKERS = (
    "帮我", "查一下", "了解一下", "随便", "看看", "有什么", "怎么样",
    "帮我研究", "调研一下", "help me", "tell me about", "what about", "explain",
)


def likely_vague(question: str) -> bool:
    """Deterministic gate: only run the LLM clarifier for plausibly vague input.

    Clear questions (a concrete topic + scope) skip clarification entirely, which
    keeps the UX snappy and avoids wasting a model call.
    """
    q = question.strip()
    if not q:
        return True
    if len(q) <= 6:
        return True
    return any(marker in q.lower() for marker in _VAGUE_MARKERS)
AskQuestions = Callable[[list[str]], Awaitable[dict[str, str]]]


def build_clarifier(question: str) -> Agent:
    """Clarifier agent whose prompt is language-aligned with the question."""
    return Agent(
        name="Clarifier",
        instructions=CLARIFIER_INSTRUCTIONS + language_instruction(question),
        output_type=ClarificationPlan,
    )


async def run_clarification(
    question: str, run_config: RunConfig, max_turns: int = 6
) -> ClarificationPlan:
    """Ask the model whether clarification is needed and get proposed questions."""
    result = await Runner.run(
        build_clarifier(question), question, run_config=run_config, max_turns=max_turns
    )
    return result.final_output


def refine_with_answers(question: str, answers: dict[str, str]) -> str:
    """Fold clarifying Q&A back into the research question."""
    if not answers:
        return question
    parts = [question, "", "补充信息（用户回答的澄清问题）："]
    for q, a in answers.items():
        parts.append(f"- {q}: {a}")
    return "\n".join(parts)