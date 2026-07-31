"""
Lightweight FAISS-backed vector store with JSON metadata sidecar.

This is intentionally a thin, swappable interface: the method names
(add, search) mirror what a real mem0 client exposes, so a team can
later replace VectorStore's internals with the actual mem0 SDK
(mem0.Memory) without touching any calling code.

Deletion note: FAISS's flat index doesn't support cheap arbitrary removal
without an ID-mapped index wrapper and a rebuild, so `delete()` here is a
SOFT delete — the metadata entry is flagged `is_deleted: true` and filtered
out of every read path (search, list_all). The underlying vector stays in
the FAISS index (wasted space, not wasted correctness) until a periodic
compaction rebuilds the index from only non-deleted entries. Fine for the
scale this is built for; revisit if the deleted fraction grows large.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import faiss
import numpy as np

from app.core.config import settings
from app.services.embedding_service import embed_text, embed_texts

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output size


class VectorStore:
    def __init__(self, index_path: str | None = None, meta_path: str | None = None):
        self.index_path = index_path or settings.VECTOR_INDEX_PATH
        self.meta_path = meta_path or settings.VECTOR_META_PATH
        Path(self.index_path).parent.mkdir(parents=True, exist_ok=True)

        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
        else:
            self.index = faiss.IndexFlatIP(EMBEDDING_DIM)  # cosine sim via normalized vectors

        if os.path.exists(self.meta_path):
            with open(self.meta_path, "r") as f:
                self.metadata: list[dict] = json.load(f)
        else:
            self.metadata = []

    def _persist(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, "w") as f:
            json.dump(self.metadata, f)

    def add(self, text: str, metadata: dict) -> str:
        """Add a single memory. Returns the generated memory id."""
        vec = embed_text(text).reshape(1, -1)
        self.index.add(vec)
        memory_id = str(uuid.uuid4())
        self.metadata.append({
            "id": memory_id,
            "text": text,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_deleted": False,
            **metadata,
        })
        self._persist()
        return memory_id

    def add_many(self, texts: list[str], metadatas: list[dict]) -> list[str]:
        vecs = embed_texts(texts)
        self.index.add(vecs)
        ids = []
        now = datetime.now(timezone.utc).isoformat()
        for text, meta in zip(texts, metadatas):
            memory_id = str(uuid.uuid4())
            ids.append(memory_id)
            self.metadata.append({"id": memory_id, "text": text, "created_at": now, "is_deleted": False, **meta})
        self._persist()
        return ids

    def search(self, query: str, top_k: int = 5, filter_fn=None) -> list[dict]:
        """Semantic search. Optional filter_fn(meta) -> bool applied post-search. Excludes soft-deleted entries."""
        if self.index.ntotal == 0:
            return []
        vec = embed_text(query).reshape(1, -1)
        k = min(top_k * 4, self.index.ntotal)  # over-fetch to allow filtering
        scores, indices = self.index.search(vec, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            meta = self.metadata[idx]
            if meta.get("is_deleted"):
                continue
            if filter_fn and not filter_fn(meta):
                continue
            results.append({**meta, "score": float(score)})
            if len(results) >= top_k:
                break
        return results

    def list_all(self, filter_fn=None) -> list[dict]:
        """
        Browse (not semantic search) every non-deleted memory, optionally
        filtered. Used for the Memories tab, where the person wants to see
        everything Athena has stored, not just top-K results for a query.
        """
        results = [m for m in self.metadata if not m.get("is_deleted")]
        if filter_fn:
            results = [m for m in results if filter_fn(m)]
        return results

    def get(self, memory_id: str) -> dict | None:
        for m in self.metadata:
            if m.get("id") == memory_id and not m.get("is_deleted"):
                return m
        return None

    def delete(self, memory_id: str) -> bool:
        for m in self.metadata:
            if m.get("id") == memory_id:
                m["is_deleted"] = True
                self._persist()
                return True
        return False


vector_store = VectorStore()
