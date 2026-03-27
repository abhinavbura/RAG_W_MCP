"""
Re-ranking — applies 5 score-adjustment signals to ChromaDB cosine results.

Input:  list of chunk dicts, each with a 'score' key (cosine similarity 0–1).
Output: same list sorted descending by adjusted score, with 'score_before'
        and 'score_after' keys added for debugging.

Signal summary (from architecture spec):
  +0.15  heading match    — any query word in section or subsection name
  +0.05  chunk_type       — chunk_type == "headed"
  +0.05  heading_conf     — heading_confidence == "high"
  -0.05  position penalty — position_ratio < 0.05 or > 0.95 (boilerplate)
  -0.10  token gate       — token_count > model_ctx_tokens (truncated embed)
"""
import logging
import re
from copy import deepcopy
from typing import List

logger = logging.getLogger(__name__)


def _rerank(chunks: List[dict], query: str, model_ctx_tokens: int) -> List[dict]:
    """
    Apply 5 score-adjustment signals to a list of candidate chunks.

    Args:
        chunks:           Candidate chunks from ChromaDB, each has a 'score' field.
        query:            The user's raw query string (used for heading word match).
        model_ctx_tokens: Max input tokens for the current embedding model.
                          Chunks exceeding this were truncated at embed time.

    Returns:
        Deep-copied list sorted descending by adjusted score.
        Each chunk gains 'score_before' and 'score_after' fields.
    """
    if not chunks:
        return []

    query_words = set(re.findall(r"\b\w+\b", query.lower()))
    # Remove short words that pollute heading matches
    query_words -= {"the", "a", "an", "is", "in", "of", "for", "to", "and", "or", "i"}

    scored: List[dict] = []

    for chunk in chunks:
        c = deepcopy(chunk)
        base = float(c.get("score", 0.0))
        adj = base

        # --- Signal 1: heading match (+0.15) ---
        section_words = set(
            re.findall(r"\b\w+\b", f"{c.get('section', '')} {c.get('subsection', '')}".lower())
        )
        if section_words & query_words:
            adj += 0.15

        # --- Signal 2: chunk_type bonus (+0.05) ---
        if c.get("chunk_type") == "headed":
            adj += 0.05

        # --- Signal 3: heading_confidence bonus (+0.05) ---
        if c.get("heading_confidence") == "high":
            adj += 0.05

        # --- Signal 4: position penalty (-0.05) ---
        try:
            pos = float(c.get("position_ratio", 0.5))
        except (TypeError, ValueError):
            pos = 0.5
        if pos < 0.05 or pos > 0.95:
            adj -= 0.05

        # --- Signal 5: token gate (-0.10) ---
        try:
            tok = int(c.get("token_count", 0))
        except (TypeError, ValueError):
            tok = 0
        if tok > model_ctx_tokens:
            adj -= 0.10

        c["score_before"] = round(base, 6)
        c["score_after"] = round(adj, 6)
        scored.append(c)

    scored.sort(key=lambda x: x["score_after"], reverse=True)
    logger.debug(
        "Reranked %d chunks. Top score: %.4f → %.4f.",
        len(scored),
        scored[0].get("score_before", 0) if scored else 0,
        scored[0].get("score_after", 0) if scored else 0,
    )
    return scored
