from research_agent.models import Finding, ResearchNotes, Source
from research_agent.runner import notes_are_empty


def test_notes_are_empty_true_when_nothing():
    assert notes_are_empty(ResearchNotes(query="q")) is True
    assert notes_are_empty(None) is True


def test_notes_are_empty_false_when_findings():
    notes = ResearchNotes(query="q", findings=[Finding(content="x")])
    assert notes_are_empty(notes) is False


def test_notes_are_empty_false_when_sources():
    notes = ResearchNotes(query="q", sources=[Source(title="t", url="https://a.com")])
    assert notes_are_empty(notes) is False
