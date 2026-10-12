from research_agent.clarify import build_clarifier, refine_with_answers
from research_agent.models import ClarificationPlan


def test_refine_with_answers_appends():
    out = refine_with_answers("AI 就业现状", {"时间范围": "2024-2026", "地区": "中国"})
    assert "AI 就业现状" in out
    assert "2024-2026" in out
    assert "中国" in out


def test_refine_with_answers_empty():
    assert refine_with_answers("q", {}) == "q"


def test_clarification_plan_model():
    plan = ClarificationPlan(needs_clarification=True, questions=["时间范围?"])
    assert plan.needs_clarification is True
    assert plan.questions == ["时间范围?"]


def test_clarification_plan_defaults():
    plan = ClarificationPlan(needs_clarification=False)
    assert plan.questions == []


def test_build_clarifier():
    agent = build_clarifier("什么是强化学习")
    assert agent.output_type is ClarificationPlan
    assert "中文" in agent.instructions

def test_likely_vague_clear_question_is_false():
    from research_agent.clarify import likely_vague

    assert likely_vague("2026年开源大模型的发展趋势") is False


def test_likely_vague_short_or_marker_is_true():
    from research_agent.clarify import likely_vague

    assert likely_vague("人工智能岗位") is True
    assert likely_vague("帮我研究一下") is True
    assert likely_vague("") is True