# --- Owner: (assign, see docs/TEAM_SPLIT.md) | retrieval over our legal sources (capability 3) ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Embed the legal sources in sources/, then find the passages most similar to each clause.

Why retrieval rather than pasting every source into each prompt: the sources together are far longer
than the few passages one clause needs, every extra token costs free-tier quota, and handing the model
only the relevant passages (each with an ID) lets us check deterministically that its citation points
at a passage we actually gave it.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SOURCES_DIR = Path(__file__).resolve().parent.parent / "sources"
INDEX_PATH = SOURCES_DIR / "index.npz"


@dataclass
class Chunk:
    chunk_id: str
    citation: str
    source: str
    text: str


def load_chunks(sources_dir: Path = SOURCES_DIR) -> list[Chunk]:
    """Each source is markdown. Every '## ' section is one chunk, and its first line names the citation:

        ## c186-15B-4 | M.G.L. c. 186 §15B(4)
        text...
    """
    chunks: list[Chunk] = []
    for path in sorted(sources_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        body = path.read_text(encoding="utf-8")
        for section in re.split(r"^## ", body, flags=re.MULTILINE)[1:]:
            header, _, text = section.partition("\n")
            chunk_id, _, citation = header.partition("|")
            text = text.strip()
            if text:
                chunks.append(Chunk(chunk_id.strip(), citation.strip() or chunk_id.strip(), path.stem, text))
    return chunks


def _fingerprint(chunks: list[Chunk], model: str) -> str:
    h = hashlib.sha256(model.encode())
    for c in chunks:
        h.update(c.chunk_id.encode())
        h.update(c.text.encode())
    return h.hexdigest()[:16]


class SourceIndex:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray):
        self.chunks = chunks
        self.vectors = vectors
        self.by_id = {c.chunk_id: c for c in chunks}

    @classmethod
    def build(cls, llm, sources_dir: Path = SOURCES_DIR, cache_path: Path | None = INDEX_PATH) -> "SourceIndex":
        """Embed every chunk, reusing the cached vectors in sources/index.npz when the sources are unchanged."""
        chunks = load_chunks(sources_dir)
        if not chunks:
            raise FileNotFoundError(f"No source chunks found in {sources_dir}")
        model = getattr(llm, "embed_model", "fake")
        fingerprint = _fingerprint(chunks, model)
        if cache_path and cache_path.exists():
            cached = np.load(cache_path, allow_pickle=False)
            if str(cached["fingerprint"]) == fingerprint:
                return cls(chunks, cached["vectors"])
        texts = [f"{c.citation}\n{c.text}" for c in chunks]
        vectors = llm.embed(texts, task_type="RETRIEVAL_DOCUMENT")
        if cache_path:
            try:
                np.savez(cache_path, vectors=vectors, fingerprint=np.array(fingerprint))
            except OSError:
                pass  # read-only file system on some hosts; we just re-embed next cold start
        return cls(chunks, vectors)

    def search_many(self, llm, queries: list[str], k: int) -> list[list[tuple[Chunk, float]]]:
        """Top-k chunks for each query, by cosine similarity. One embedding request for all queries."""
        if not queries:
            return []
        q = llm.embed(queries, task_type="RETRIEVAL_QUERY")
        scores = q @ self.vectors.T
        results = []
        for row in scores:
            top = np.argsort(-row)[:k]
            results.append([(self.chunks[i], float(row[i])) for i in top])
        return results


def format_passages(chunks: list[Chunk]) -> str:
    return "\n\n".join(f"[{c.chunk_id}] ({c.citation})\n{c.text}" for c in chunks)

