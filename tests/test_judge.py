from research_agent.judge import _extract_json


def test_extract_plain_json():
    data = _extract_json('{"relevance": 4, "total": 3.5}')
    assert data is not None
    assert data["relevance"] == 4
    assert data["total"] == 3.5


def test_extract_fenced_json():
    text = "```json\n{\"relevance\": 5}\n```"
    assert _extract_json(text) == {"relevance": 5}


def test_extract_json_with_surrounding_text():
    text = "好的，评分如下：\n{\"relevance\": 3, \"comments\": \"ok\"}\n完毕"
    data = _extract_json(text)
    assert data is not None
    assert data["comments"] == "ok"


def test_extract_json_garbage():
    assert _extract_json("no json here") is None
    assert _extract_json("") is None
    assert _extract_json(None) is None