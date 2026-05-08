"""
app.rag — RAG grounding-uplift modules (Phase A).

Phase A (this PR): foundation modules used by routes/rag.py
  - prompt.py    : strict-grounding prompt builder + 4-level confidence
  - chunker.py   : sentence-window expansion for retrieved segments

Phase B (future): hybrid retriever (pgvector + BM25 / RRF) — TBD
Phase C (future): cross-encoder reranker (BGE / cohere-rerank) — TBD

Public API:
  from app.rag.prompt import build_grounded_prompt, STRICT_GROUNDING_SYSTEM_PROMPT
  from app.rag.chunker import expand_with_context, ExpandedRow
"""

from app.rag.prompt import (
    STRICT_GROUNDING_SYSTEM_PROMPT,
    CONFIDENCE_LEVELS,
    build_grounded_prompt,
)
from app.rag.chunker import (
    ExpandedRow,
    expand_with_context,
)

__all__ = [
    "STRICT_GROUNDING_SYSTEM_PROMPT",
    "CONFIDENCE_LEVELS",
    "build_grounded_prompt",
    "ExpandedRow",
    "expand_with_context",
]
