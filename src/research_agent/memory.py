"""Vector memory: persist past research reports and retrieve relevant ones.

Uses ChromaDB for storage and Ollama's /api/embeddings for local embeddings,
so the whole memory pipeline runs fully offline.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import requests

from .config import get_embed_model, get_ollama_api_url
from .formatting import report_to_markdown
from .models import ResearchReport

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PERSIST_DIR = PROJECT_ROOT / "memory"
DEFAULT_COLLECTION = "research_reports"


def ollama_embed(
    texts: list[str], model: str | None = None, base_url: str | None = None
) -> list[list[float]]:
    """Embed texts via Ollama's native /api/embeddings endpoint."""
    model = model or get_embed_model()
    base_url = base_url or get_ollama_api_url()
    result: list[list[float]] = []
    for text in texts:
        resp = requests.post(
            f"{base_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=90,
        )
        resp.raise_for_status()
        result.append(resp.json()["embedding"])
    return result


class MemoryStore:
    """Chroma-backed store of past reports with cosine similarity search.

    embed_fn is injectable for testing; by default it uses Ollama embeddings.
    """

    def __init__(
        self,
        persist_dir: Path | str | None = None,
        collection: str = DEFAULT_COLLECTION,
        embed_fn=None,
    ) -> None:
        import chromadb

        self.persist_dir = Path(persist_dir) if persist_dir else DEFAULT_PERSIST_DIR
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._col = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )
        self._embed_fn = embed_fn

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if self._embed_fn is not None:
            return [self._embed_fn(t) for t in texts]
        return ollama_embed(texts)

    def add_report(self, report: ResearchReport, document: str | None = None) -> str:
        """Store a report (as rendered markdown) and return its stable id."""
        doc = document or report_to_markdown(report)
        embedding = self._embed([doc])[0]
        rid = hashlib.sha1((report.title + doc[:200]).encode("utf-8")).hexdigest()[:16]
        self._col.upsert(
            ids=[rid],
            embeddings=[embedding],
            documents=[doc],
            metadatas=[
                {
                    "title": report.title,
                    "created": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                }
            ],
        )
        return rid

    def search(self, query: str, k: int = 3) -> list[dict]:
        """Return the k most relevant past reports as dicts."""
        if self.count() == 0:
            return []
        embedding = self._embed([query])[0]
        res = self._col.query(query_embeddings=[embedding], n_results=k)
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        return [
            {"id": ids[i], "document": docs[i], "metadata": metas[i] if metas else {}}
            for i in range(len(docs))
        ]

    def count(self) -> int:
        return self._col.count()