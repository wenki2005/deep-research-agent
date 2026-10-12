from research_agent.agents import build_agents, language_instruction


def test_language_instruction_chinese():
    inst = language_instruction("ai岗位现状怎么样")
    assert "中文" in inst


def test_language_instruction_english():
    inst = language_instruction("What is the latest trend of LLM?")
    assert "中文" not in inst
    assert "same language" in inst


def test_build_agents_appends_language():
    bundle = build_agents("什么是强化学习")
    assert "中文" in bundle.planner.instructions
    assert "中文" in bundle.researcher.instructions
    assert "中文" in bundle.writer.instructions
    assert bundle.planner.output_type.__name__ == "ResearchPlan"
    assert bundle.writer.output_type.__name__ == "ResearchReport"