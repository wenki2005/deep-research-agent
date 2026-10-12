"""FastAPI service layer for deploying the research workflow."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .config import PROVIDERS
from .formatting import report_to_markdown
from .routing import RESEARCH_MODES, infer_mode
from .runner import run_research, save_report

app = FastAPI(
    title="Deep Research Agent API",
    version="1.0.0",
    description="Evidence-oriented multi-agent research workflow.",
)


class ResearchRequest(BaseModel):
    question: str = Field(min_length=4, max_length=2000)
    provider: Literal["local", "openai"] | None = None
    research_mode: Literal["standard", "hot_topic", "academic", "industry", "policy", "technical"] | None = None
    max_queries: int = Field(default=4, ge=1, le=8)
    use_memory: bool = False
    export_pdf: bool = False


class ResearchResponse(BaseModel):
    task_id: str
    question: str
    mode: str
    report: dict
    markdown: str
    markdown_path: str
    pdf_path: str | None = None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "deep-research-agent", "utc": datetime.now(timezone.utc).isoformat()}


@app.post("/research", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> ResearchResponse:
    task_id = str(uuid.uuid4())
    mode = request.research_mode or infer_mode(request.question)
    report = await run_research(
        request.question,
        max_queries=request.max_queries,
        provider=request.provider,
        verbose=False,
        use_memory=request.use_memory,
        research_mode=mode,
    )
    markdown = report_to_markdown(report, request.question)
    markdown_path = save_report(report)
    pdf_path: str | None = None
    if request.export_pdf:
        from .export import report_to_pdf

        pdf_path = str(report_to_pdf(report))
    return ResearchResponse(
        task_id=task_id,
        question=request.question,
        mode=mode,
        report=report.model_dump(),
        markdown=markdown,
        markdown_path=str(markdown_path),
        pdf_path=pdf_path,
    )


@app.get("/config")
async def config() -> dict:
    """Expose safe runtime capabilities; never expose API keys."""
    return {"providers": list(PROVIDERS), "modes": list(RESEARCH_MODES)}


def main() -> None:
    """Start the API server for the `research-api` console command."""
    import uvicorn

    uvicorn.run("research_agent.api:app", host="0.0.0.0", port=8000, reload=False)
