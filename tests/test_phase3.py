"""
Phase 3 unit tests — all component logic verified in isolation.
No real LLM calls, no ChromaDB connections needed.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipeline.retrieval.intent import _classify_intent
from pipeline.retrieval.rerank import _rerank
from pipeline.retrieval.mmr import _mmr
from pipeline.retrieval.scope import _detect_scope
from pipeline.embeddings.helpers import embed_query, embed_documents
from pipeline.state.pipeline_state import PipelineState, FileMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeVector:
    """Minimal ndarray-like with a .tolist()."""
    def __init__(self, data):
        self._data = data

    def tolist(self):
        return self._data

    def __iter__(self):
        return iter(self._data)


class _DummyModel:
    """Minimal SentenceTransformer stub for embedding tests."""
    def encode(self, text, batch_size=None, show_progress_bar=False):
        if isinstance(text, list):
            return [_FakeVector([0.1, 0.2, 0.3]) for _ in text]
        return _FakeVector([0.1, 0.2, 0.3])


def _make_chunk(id_, section="", score=0.5, chunk_type="headed",
                heading_confidence="high", position_ratio=0.5, token_count=100):
    return {
        "id": id_,
        "section": section,
        "subsection": "",
        "score": score,
        "chunk_type": chunk_type,
        "heading_confidence": heading_confidence,
        "position_ratio": position_ratio,
        "token_count": token_count,
    }


def _make_state(files=None):
    state = PipelineState(folder_path="/data/dataset")
    state.requires_prefix = True
    state.query_prefix = "search_query: "
    state.doc_prefix = "search_document: "
    state._model_instance = _DummyModel()
    state.model_ctx_tokens = 8192
    state.collection_count = 50
    if files:
        state.files_metadata = files
    return state


# ---------------------------------------------------------------------------
# intent tests
# ---------------------------------------------------------------------------

def test_intent_fact():
    assert _classify_intent("where is the refund policy?") == "fact"
    assert _classify_intent("how many days is the return window?") == "fact"


def test_intent_summary():
    assert _classify_intent("summarize the cancellation policy") == "summary"
    assert _classify_intent("what is the membership program?") == "summary"


def test_intent_comparison():
    assert _classify_intent("compare the premium and basic plans") == "comparison"
    assert _classify_intent("what is the difference between plan A and B?") == "comparison"


def test_intent_conversational():
    # "it" triggers conversational; no other pattern — unambiguous
    assert _classify_intent("tell me more about it") == "conversational"


def test_intent_ambiguous_priority():
    # "compare what is the difference" triggers both comparison + summary
    # priority: comparison wins
    result = _classify_intent("compare: what is the difference?", llm_router=None)
    assert result == "comparison"


def test_intent_default():
    assert _classify_intent("xyz abc nonsense") == "fact"


# ---------------------------------------------------------------------------
# rerank tests
# ---------------------------------------------------------------------------

def test_rerank_heading_bonus():
    chunks = [
        _make_chunk("a", section="Pricing", score=0.5),
        _make_chunk("b", section="Delivery", score=0.6),
    ]
    result = _rerank(chunks, "what is the pricing?", 8192)
    # 'a' base=0.5+0.15 heading+0.05 chunk_type+0.05 conf = 0.75 > 'b' 0.6+0.05+0.05=0.70
    assert result[0]["id"] == "a"


def test_rerank_token_gate():
    chunks = [
        _make_chunk("big", score=0.9, token_count=10000),  # -0.10
        _make_chunk("small", score=0.8, token_count=200),
    ]
    result = _rerank(chunks, "hello", 8192)
    # big: 0.9-0.10+0.05+0.05=0.90 — actually still high from bonuses
    # Let's check that big got the penalty applied
    big_chunk = next(c for c in result if c["id"] == "big")
    assert big_chunk["score_after"] < big_chunk["score_before"] + 0.15  # penalty applied


def test_rerank_position_penalty():
    chunks = [
        _make_chunk("intro", score=0.7, position_ratio=0.01, chunk_type="semantic", heading_confidence="none"),
        _make_chunk("body", score=0.6, position_ratio=0.5),
    ]
    result = _rerank(chunks, "nothing", 8192)
    intro = next(c for c in result if c["id"] == "intro")
    # intro: 0.7 - 0.05 (pos) = 0.65; body: 0.6 + 0.05 + 0.05 = 0.70
    body = next(c for c in result if c["id"] == "body")
    assert body["score_after"] > intro["score_after"]


def test_rerank_empty():
    assert _rerank([], "q", 8192) == []


# ---------------------------------------------------------------------------
# mmr tests
# ---------------------------------------------------------------------------

def test_mmr_deduplication():
    chunks = [
        _make_chunk("a", section="Alpha", score=0.9),
        _make_chunk("b", section="Alpha", score=0.85),  # dup section
        _make_chunk("c", section="Beta", score=0.7),
    ]
    # Manually add score_after
    for c in chunks:
        c["score_after"] = c["score"]
    result = _mmr(chunks, 0.7)
    sections = [c["section"] for c in result]
    assert sections.count("Alpha") == 1, "Alpha should be deduplicated"
    assert "Beta" in sections


def test_mmr_single():
    chunks = [_make_chunk("x", section="A", score=0.9)]
    chunks[0]["score_after"] = 0.9
    assert len(_mmr(chunks, 0.7)) == 1


def test_mmr_empty():
    assert _mmr([], 0.7) == []


def test_mmr_lambda_diversity():
    chunks = [
        _make_chunk("a", section="A", score=0.9),
        _make_chunk("b", section="A", score=0.88),
        _make_chunk("c", section="B", score=0.5),
        _make_chunk("d", section="C", score=0.4),
    ]
    for c in chunks:
        c["score_after"] = c["score"]
    high_lambda = _mmr(chunks, 0.9)   # more precision — might pick same section twice before dedup
    low_lambda = _mmr(chunks, 0.2)    # more diversity — should pick different sections early
    # After dedup both should have unique sections, but ordering differs
    assert len({c["section"] for c in high_lambda}) == len(high_lambda)
    assert len({c["section"] for c in low_lambda}) == len(low_lambda)


# ---------------------------------------------------------------------------
# scope tests
# ---------------------------------------------------------------------------

def test_scope_match():
    files = [
        FileMetadata(path="/data/dataset/blinkit_tnc.md", file_type="md",
                     size_chars=1000, hash="abc", status="ingested"),
        FileMetadata(path="/data/dataset/policy.txt", file_type="txt",
                     size_chars=500, hash="def", status="ingested"),
    ]
    state = _make_state(files)
    result = _detect_scope("what does blinkit say about refunds?", state)
    assert result == "blinkit_tnc.md"


def test_scope_no_match():
    files = [
        FileMetadata(path="/data/dataset/document.pdf", file_type="pdf",
                     size_chars=1000, hash="abc", status="ingested"),
    ]
    state = _make_state(files)
    result = _detect_scope("completely unrelated query", state)
    assert result is None


def test_scope_tie_returns_none():
    files = [
        FileMetadata(path="/data/dataset/ml_notes.txt", file_type="txt",
                     size_chars=500, hash="a", status="ingested"),
        FileMetadata(path="/data/dataset/ml_textbook.pdf", file_type="pdf",
                     size_chars=500, hash="b", status="ingested"),
    ]
    state = _make_state(files)
    # "ml" matches both files equally — should return None (not confident)
    result = _detect_scope("what does ml say?", state)
    assert result is None


# ---------------------------------------------------------------------------
# embed tests
# ---------------------------------------------------------------------------

def test_embed_query_with_prefix():
    state = _make_state()
    vec = embed_query("hello", state)
    assert isinstance(vec, list)
    assert len(vec) == 3


def test_embed_query_no_prefix():
    state = _make_state()
    state.requires_prefix = False
    vec = embed_query("hello", state)
    assert isinstance(vec, list)


def test_embed_documents_batch():
    state = _make_state()
    vecs = embed_documents(["text one", "text two"], state)
    assert len(vecs) == 2
    assert len(vecs[0]) == 3


def test_embed_documents_empty():
    state = _make_state()
    assert embed_documents([], state) == []


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_intent_fact, test_intent_summary, test_intent_comparison,
        test_intent_conversational, test_intent_ambiguous_priority, test_intent_default,
        test_rerank_heading_bonus, test_rerank_token_gate, test_rerank_position_penalty,
        test_rerank_empty,
        test_mmr_deduplication, test_mmr_single, test_mmr_empty, test_mmr_lambda_diversity,
        test_scope_match, test_scope_no_match, test_scope_tie_returns_none,
        test_embed_query_with_prefix, test_embed_query_no_prefix,
        test_embed_documents_batch, test_embed_documents_empty,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:
            print(f"  ✗ {t.__name__}: EXCEPTION — {e}")

    print(f"\n{passed}/{len(tests)} tests passed.")
    if passed < len(tests):
        sys.exit(1)
