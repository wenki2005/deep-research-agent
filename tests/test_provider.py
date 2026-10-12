from research_agent.runner import build_model


def test_build_model_local_returns_model(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL", "qwen3:4b")
    model = build_model("local")
    assert model is not None
    assert getattr(model, "model", "") == "qwen3:4b"


def test_build_model_openai_default_is_none():
    assert build_model("openai") is None


def test_build_model_openai_custom_url_requires_model(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    try:
        build_model("openai")
        assert False, "should raise"
    except RuntimeError as exc:
        assert "OPENAI_MODEL" in str(exc)


def test_build_model_openai_custom_url_returns_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "deepseek-chat")
    model = build_model("openai")
    assert model is not None
    assert getattr(model, "model", "") == "deepseek-chat"