"""Pydantic schemas used for structured outputs across the pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    """A single cited source."""

    title: str = Field(description="Title of the source")
    url: str = Field(description="URL of the source")
    relevance: str = Field(default="", description="Why this source matters for the topic")
    source_type: Literal["official", "government", "academic", "media", "industry", "social", "blog", "unknown"] = Field(
        default="unknown", description="Source category used for quality scoring"
    )
    published_at: str | None = Field(default=None, description="Publication date if available, ISO-8601 preferred")
    quality_score: int = Field(default=0, ge=0, le=100, description="Deterministic source quality score")


class ResearchPlan(BaseModel):
    """Structured output of the Planner agent."""

    angle: str = Field(description="Research angle / strategy in one or two sentences")
    queries: list[str] = Field(description="3-6 concrete search queries that together cover the topic")


class Finding(BaseModel):
    """A single factual finding collected by the Researcher."""

    content: str = Field(description="A factual finding with concrete details, numbers and dates when available")
    status: Literal["confirmed", "reported_not_verified", "rumor", "disputed", "unknown"] = Field(
        default="unknown", description="Epistemic status of this finding"
    )
    confidence: Literal["high", "medium", "low"] = Field(default="low", description="Confidence based on evidence")
    source_urls: list[str] = Field(default_factory=list, description="URLs that directly support this finding")
    support_level: Literal["unverified", "snippet_quote", "page_quote"] = "unverified"
    evidence_quote: str = Field(default="", description="Short verbatim quote or excerpt supporting the finding")
    published_at: str | None = Field(default=None, description="Date of the supporting evidence if known")


class ResearchNotes(BaseModel):
    """Structured output of the Researcher agent."""

    query: str = Field(description="The search query these notes answer")
    findings: list[Finding] = Field(default_factory=list, description="Key findings for this query")
    sources: list[Source] = Field(default_factory=list, description="Sources that back the findings")


class KeyFinding(BaseModel):
    """A consolidated finding in the final report."""

    topic: str = Field(description="Short topic / heading of this finding")
    details: str = Field(description="Detailed finding, with facts and figures where possible")
    status: Literal["confirmed", "reported_not_verified", "rumor", "disputed", "unknown"] = Field(default="unknown")
    confidence: Literal["high", "medium", "low"] = Field(default="low")
    evidence: list[Finding] = Field(default_factory=list, description="Supporting researcher findings")


class ResearchReport(BaseModel):
    """Structured output of the Writer agent — the final deliverable."""

    title: str = Field(description="Concise, descriptive report title")
    question: str = Field(default="", description="Original user question; set by orchestrator")
    summary: str = Field(description="Executive summary in 3-5 sentences")
    key_findings: list[KeyFinding] = Field(description="3-6 consolidated key findings")
    sources: list[Source] = Field(default_factory=list, description="All cited sources")
    limitations: str = Field(default="", description="Known limitations of this research")
    recommendations: str = Field(default="", description="Suggested next steps for the reader")
    research_mode: Literal["standard", "hot_topic", "academic", "industry", "policy", "technical"] = Field(
        default="standard"
    )
    evidence_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="Fraction of findings with direct evidence")
    verification_state: Literal["unchecked", "insufficient", "partial", "quoted"] = "unchecked"
    verification_summary: str = Field(default="", description="What is confirmed, disputed, or unverified")

    @field_validator("evidence_coverage", mode="before")
    @classmethod
    def normalize_evidence_coverage(cls, value: float | str) -> float:
        """Accept both ratios (0.75) and common percentage output (75/100)."""
        coverage = float(value)
        return coverage / 100 if coverage > 1 else coverage


class ClarificationPlan(BaseModel):
    """Structured output of the Clarifier agent (human-in-the-loop stage)."""

    needs_clarification: bool = Field(description="Whether clarifying questions are needed")
    questions: list[str] = Field(default_factory=list, description="1-3 concise clarifying questions")
