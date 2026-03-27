"""
retrieve() — 7-stage retrieval pipeline.

Entry point for all query processing. Embeds the query once and reuses the
vector across all ChromaDB calls. Returns a fully-populated RetrievalResult.

Stage map:
  0 — embed_query()          : single encode call, vector reused everywhere
  1 — _classify_intent()     : regex primary, LLM fallback
  2 — _detect_scope()        : keyword match against file stems
  3 — build where-filter     : scope + intent-specific logic
  4 — ChromaDB cosine search : k×3 for summary (MMR headroom), k×2 others
  5 — _rerank()              : 5-signal score adjustment
  6 — post-process by intent : fact / summary / comparison / conversational
"""
import logging
import time
from typing import List, Optional

from pipeline.embeddings.helpers import embed_query
from pipeline.llm.router import LLMRouter
from pipeline.state.chunking_config import get_config
from pipeline.state.conversation import ConversationHistory
from pipeline.state.pipeline_state import PipelineState
from pipeline.state.retrieval_result import RetrievalResult

from .intent import _classify_intent
from .mmr import _mmr
from .rerank import _rerank
from .scope import _detect_scope
from .section_extract import _extract_sections_llm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def retrieve(
    query: str,
    state: PipelineState,
    history: Optional[ConversationHistory] = None,
) -> RetrievalResult:
    """
    Run the 7-stage retrieval pipeline for *query*.

    Args:
        query:   Raw user query string.
        state:   PipelineState — must have _model_instance and _collection loaded.
        history: Optional ConversationHistory for conversational-intent handling.

    Returns:
        Fully populated RetrievalResult.
    """
    t_start = time.perf_counter()
    result = RetrievalResult(query=query)

    # ----------------------------------------------------------------- Stage 0
    logger.debug("Stage 0 — embedding query.")
    query_vector = embed_query(query, state)

    llm_router = LLMRouter(state)

    # ----------------------------------------------------------------- Stage 1
    logger.debug("Stage 1 — classifying intent.")
    intent = _classify_intent(query, llm_router)
    result.intent = intent

    # ----------------------------------------------------------------- Stage 2
    logger.debug("Stage 2 — detecting scope.")
    scope = _detect_scope(query, state)
    result.scope = scope

    # ----------------------------------------------------------------- Config
    config = get_config(text="", chunk_count=state.collection_count)

    k_map = {
        "fact": config.k_fact,
        "summary": config.k_summary,
        "comparison": config.k_compare,
        "conversational": config.k_conversational,
    }
    k = k_map.get(intent, config.k_fact)
    result.k = k
    result.model_key = state.model_key

    # ----------------------------------------------------------------- Stage 3
    logger.debug("Stage 3 — building ChromaDB filter (intent=%s, scope=%s).", intent, scope)
    base_filter = _build_scope_filter(scope)
    sections_to_search: List[str] = []

    if intent == "comparison":
        known_sections = _get_known_sections(state)
        extracted = _extract_sections_llm(query, known_sections, llm_router)
        if extracted:
            sections_to_search = extracted
            result.sections = sections_to_search
            if base_filter:
                result.filter_applied = True

    # ----------------------------------------------------------------- Stage 4
    logger.debug("Stage 4 — ChromaDB cosine search.")
    raw_chunks = _execute_search(
        state=state,
        query_vector=query_vector,
        intent=intent,
        k=k,
        base_filter=base_filter,
        sections=sections_to_search,
        history=history,
    )
    if base_filter or sections_to_search:
        result.filter_applied = True

    result.total_fetched = len(raw_chunks)
    logger.debug("Fetched %d candidates from ChromaDB.", result.total_fetched)

    # ----------------------------------------------------------------- Stage 5
    logger.debug("Stage 5 — reranking.")
    reranked = _rerank(raw_chunks, query, state.model_ctx_tokens)

    result.scores_before = [c.get("score_before", 0.0) for c in reranked]
    result.scores_after = [c.get("score_after", 0.0) for c in reranked]

    # ----------------------------------------------------------------- Stage 6
    logger.debug("Stage 6 — intent-specific post-processing (%s).", intent)
    final_chunks = _post_process(
        intent=intent,
        reranked=reranked,
        k=k,
        config=config,
        sections=sections_to_search,
        history=history,
    )

    result.chunks = final_chunks
    result.total_tokens = sum(int(c.get("token_count", 0)) for c in final_chunks)
    result.latency_ms = (time.perf_counter() - t_start) * 1000.0

    logger.info(
        "retrieve() done: intent=%s scope=%s chunks=%d tokens=%d latency=%.1fms",
        intent, scope, len(final_chunks), result.total_tokens, result.latency_ms,
    )
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_scope_filter(scope: Optional[str]) -> dict:
    """Return a ChromaDB where-clause dict for the scope, or {} if none."""
    if scope:
        return {"source_doc": {"$eq": scope}}
    return {}


def _get_known_sections(state: PipelineState) -> List[str]:
    """Fetch all distinct non-empty section names from the ChromaDB collection."""
    if not state._collection:
        return []
    try:
        res = state._collection.get(include=["metadatas"])
        sections = set()
        for meta in (res.get("metadatas") or []):
            sec = (meta or {}).get("section", "")
            if sec:
                sections.add(sec)
        return sorted(sections)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch known sections: %s.", exc)
        return []


def _execute_search(
    state: PipelineState,
    query_vector: List[float],
    intent: str,
    k: int,
    base_filter: dict,
    sections: List[str],
    history: Optional[ConversationHistory],
) -> List[dict]:
    """
    Fire ChromaDB queries and return a flat list of chunk dicts with 'score'.

    Comparison: two separate queries (one per section), merged.
    Others:     single query with combined filter.
    """
    collection = state._collection

    def _query(n_results: int, where: Optional[dict] = None) -> List[dict]:
        kwargs: dict = {
            "query_embeddings": [query_vector],
            "n_results": max(1, n_results),
            "include": ["metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        try:
            res = collection.query(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error("ChromaDB query failed: %s.", exc)
            return []

        chunks: List[dict] = []
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for meta, dist in zip(metas, dists):
            chunk = dict(meta or {})
            # ChromaDB cosine distance ∈ [0, 2]; convert to similarity ∈ [0, 1]
            chunk["score"] = max(0.0, 1.0 - dist / 2.0)
            chunks.append(chunk)
        return chunks

    # Comparison: two queries, one per extracted section
    if intent == "comparison" and sections:
        results: List[dict] = []
        half_k = max(1, k // 2)
        for sec in sections:
            sec_filter: dict = {"section": {"$eq": sec}}
            if base_filter:
                sec_filter = {"$and": [base_filter, sec_filter]}
            results.extend(_query(half_k, sec_filter))
        return results

    # All other intents: single query
    fetch_k = k * 3 if intent == "summary" else k * 2

    # Conversational: exclude previously seen chunks
    where = dict(base_filter)  # shallow copy
    if intent == "conversational" and history:
        excluded = history.excluded_ids()
        if excluded:
            # ChromaDB supports $nin for IDs via the 'ids' query parameter,
            # but NOT as a metadata where filter. We fetch more and filter client-side.
            chunks = _query(fetch_k + len(excluded), where or None)
            excluded_set = set(excluded)
            return [c for c in chunks if c.get("id") not in excluded_set]

    return _query(fetch_k, where or None)


def _post_process(
    intent: str,
    reranked: List[dict],
    k: int,
    config,
    sections: List[str],
    history: Optional[ConversationHistory],
) -> List[dict]:
    """Apply intent-specific final selection logic."""

    if intent == "fact":
        return reranked[:k]

    if intent == "summary":
        mmr_result = _mmr(reranked, config.mmr_lambda)
        return mmr_result[:k]

    if intent == "comparison":
        if sections:
            # Interleave results from each section for equal representation
            sec_a = [c for c in reranked if c.get("section") == sections[0]]
            sec_b = [c for c in reranked if c.get("section") == sections[1]] if len(sections) > 1 else []
            interleaved: List[dict] = []
            for a, b in zip(sec_a, sec_b):
                interleaved.extend([a, b])
            # Append any remainder from the longer list
            longer = sec_a[len(sec_b):] if len(sec_a) > len(sec_b) else sec_b[len(sec_a):]
            interleaved.extend(longer)
            return interleaved[:k]
        return reranked[:k]

    if intent == "conversational":
        final = reranked[:k]
        if history:
            # Prepend recent context chunks so the LLM can resolve references
            recent = history.recent_chunks(n=2)
            recent_ids = {c.get("id", "") for c in recent}
            # Avoid duplicates between recent and freshly retrieved chunks
            fresh = [c for c in final if c.get("id", "") not in recent_ids]
            final = recent + fresh

            # Trim to model context budget
            budget = 0
            trimmed: List[dict] = []
            for chunk in final:
                tok = int(chunk.get("token_count", 0))
                if budget + tok <= 4096:  # conservative context budget for conversational
                    trimmed.append(chunk)
                    budget += tok
                else:
                    break
            return trimmed
        return final

    return reranked[:k]
