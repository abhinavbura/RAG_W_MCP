"""
Maximal Marginal Relevance (MMR) — used only for summary-intent queries.

Redundancy is approximated by section-name overlap, not by computing cosine
similarity between chunk embeddings. This avoids any extra embed() calls at
query time — the spec explicitly prohibits this for latency reasons.

mmr_lambda controls the precision/diversity trade-off:
  λ → 1.0 : pure relevance re-ranking (same as top-k)
  λ → 0.0 : pure diversity (ignores query similarity)
  Architecture spec values: 0.7 (small), 0.6 (medium), 0.5 (large collection)

After MMR selection order is computed, duplicate sections are deduplicated
so the LLM context doesn't receive two chunks from the same section header.
"""
import logging
from typing import List

logger = logging.getLogger(__name__)


def _mmr(chunks: List[dict], mmr_lambda: float) -> List[dict]:
    """
    Apply MMR to select a diverse, relevant subset of re-ranked chunks.

    Args:
        chunks:     Re-ranked candidate chunks (must have 'score_after' key).
        mmr_lambda: Trade-off factor. Higher = more relevant, less diverse.

    Returns:
        Chunks ordered by MMR score. Consecutive same-section chunks are
        deduplicated (first occurrence kept). Chunks with no section header
        are always kept.
    """
    if not chunks:
        return []

    if len(chunks) == 1:
        return list(chunks)

    # Working copies — avoid mutating the caller's list
    candidates = list(chunks)
    selected: List[dict] = []

    # Seed: pick the highest-scoring candidate first (already sorted by rerank)
    selected.append(candidates.pop(0))

    while candidates:
        best_idx = -1
        best_score = float("-inf")

        for i, candidate in enumerate(candidates):
            relevance = float(candidate.get("score_after", candidate.get("score", 0.0)))

            # Redundancy: 1.0 if this candidate shares a section with ANY selected chunk
            # 0.0 if no section overlap.  Section name comparison is exact-match.
            cand_section = candidate.get("section", "")
            redundancy = 0.0
            if cand_section:
                for sel in selected:
                    if cand_section == sel.get("section", ""):
                        redundancy = 1.0
                        break

            mmr_score = mmr_lambda * relevance - (1.0 - mmr_lambda) * redundancy

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i

        selected.append(candidates.pop(best_idx))

    # Deduplicate by section — keep first occurrence of each section
    seen_sections: set = set()
    deduped: List[dict] = []
    for chunk in selected:
        sec = chunk.get("section", "")
        if not sec:
            # Chunks without a section header are always included
            deduped.append(chunk)
        elif sec not in seen_sections:
            seen_sections.add(sec)
            deduped.append(chunk)

    logger.debug(
        "MMR: %d → %d chunks after section deduplication (lambda=%.2f).",
        len(selected),
        len(deduped),
        mmr_lambda,
    )
    return deduped
