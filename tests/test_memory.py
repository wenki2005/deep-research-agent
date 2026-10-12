from research_agent.memory import MemoryStore
from research_agent.models import KeyFinding, ResearchReport, Source


def _report(title="报告A"):
    return ResearchReport(
        title=title,
        summary="这是一份关于AI岗位的报告摘要",
        key_findings=[KeyFinding(topic="t1", details="d1" * 10)],
        sources=[Source(title="s", url="https://example.com/a")],
        limitations="L",
        recommendations="R",
    )


def _fake_embed(text):
    # deterministic pseudo-embedding by first 4 chars
    return [float(ord(c)) for c in (text[:4].ljust(4, "x"))]


def test_memory_add_and_search(tmp_path):
    store = MemoryStore(persist_dir=tmp_path, embed_fn=_fake_embed)
    store.add_report(_report("AI岗位报告"))
    assert store.count() == 1
    hits = store.search("AI岗位", k=2)
    assert len(hits) >= 1
    assert "AI岗位" in hits[0]["document"]


def test_memory_empty_search(tmp_path):
    store = MemoryStore(persist_dir=tmp_path, embed_fn=_fake_embed)
    assert store.count() == 0
    assert store.search("anything") == []


def test_memory_dedupe_on_re_add(tmp_path):
    store = MemoryStore(persist_dir=tmp_path, embed_fn=_fake_embed)
    store.add_report(_report("同一份报告"))
    store.add_report(_report("同一份报告"))
    assert store.count() == 1