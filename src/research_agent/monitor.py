"""One-shot active-monitoring job.

The scheduler is intentionally external: Windows Task Scheduler, cron, or a
CI job can call this command on a schedule. Keeping the job one-shot makes it
easy to retry, observe, and deploy without a long-running scheduler process.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .export import report_to_pdf
from .runner import run_research, save_report


async def run_monitor(config_path: Path) -> dict:
    """Run a configured research snapshot and return its artifact paths."""
    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    report = await run_research(
        config["question"],
        max_queries=int(config.get("max_queries", 3)),
        provider=config.get("provider"),
        verbose=True,
        use_memory=bool(config.get("use_memory", True)),
        research_mode=config.get("research_mode"),
    )
    markdown_path = save_report(report)
    pdf_path = report_to_pdf(report) if config.get("export_pdf", False) else None
    return {"markdown": str(markdown_path), "pdf": str(pdf_path) if pdf_path else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one active research monitoring snapshot")
    parser.add_argument("config", type=Path, help="Path to monitor.yaml")
    args = parser.parse_args(argv)
    artifacts = asyncio.run(run_monitor(args.config))
    print(f"saved markdown: {artifacts['markdown']}")
    if artifacts["pdf"]:
        print(f"saved pdf: {artifacts['pdf']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
