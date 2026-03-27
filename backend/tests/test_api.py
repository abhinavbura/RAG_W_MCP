"""
FastAPI endpoint tests using httpx AsyncClient.
These are unit tests — they mock pipeline internals to avoid needing a real ChromaDB.
"""
import os
import sys
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_pipeline(tmp_path):
    """
    Patch PipelineState and ingest_folder so backend tests run without
    ChromaDB, real embeddings, or file system fixtures.
    """
    mock_state = MagicMock()
    mock_state._collection = MagicMock()
    mock_state.collection_count = 42
    mock_state.model_key = "nomic"
    mock_state.ingested_files = ["test.md"]
    mock_state.skipped_files = []
    mock_state.failed_files = []
    mock_state.total_chunks_added = 10
    mock_state.model_upgrade_warning = ""
    mock_state.llm_tokens_used_deepseek = 0
    mock_state.llm_tokens_used_gpt = 0
    mock_state.to_dict.return_value = {
        "collection_count": 42,
        "model_key": "nomic",
        "ingested_files": ["test.md"],
        "skipped_files": [],
        "failed_files": [],
        "total_chunks_added": 10,
        "model_upgrade_warning": "",
        "llm_tokens_used_deepseek": 0,
        "llm_tokens_used_gpt": 0,
    }

    with (
        patch("backend.main.state", mock_state),
        patch("backend.main.ingest_folder", return_value=mock_state),
        patch("backend.main.DATASET_PATH", tmp_path),
        patch("backend.main.STATE_PATH", tmp_path / ".rag_state.json"),
    ):
        from backend.main import app
        yield TestClient(app), mock_state


def test_ingest_valid_files(mock_pipeline, tmp_path):
    client, _ = mock_pipeline
    content = b"# Hello world"
    response = client.post(
        "/ingest",
        files=[("files", ("notes.md", BytesIO(content), "text/markdown"))],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert "notes.md" in data["files_received"]
    assert "run_id" in data


def test_ingest_rejects_invalid_extension(mock_pipeline, tmp_path):
    client, _ = mock_pipeline
    response = client.post(
        "/ingest",
        files=[("files", ("malware.exe", BytesIO(b"badfile"), "application/octet-stream"))],
    )
    assert response.status_code == 400
    assert "Rejected" in response.json()["detail"]


def test_get_state(mock_pipeline):
    client, _ = mock_pipeline
    response = client.get("/state")
    assert response.status_code == 200
    data = response.json()
    assert data["collection_count"] == 42
    assert data["model_key"] == "nomic"
    assert isinstance(data["ingested_files"], list)


def test_query_returns_answer(mock_pipeline):
    client, mock_state = mock_pipeline
    mock_result = MagicMock()
    mock_result.chunks = [{"text": "Refunds take 7 days.", "section": "Refunds", "anchor": "Refunds", "token_count": 10}]
    mock_result.intent = "fact"
    mock_result.scope = None
    mock_result.total_tokens = 10

    with (
        patch("backend.main.retrieve", return_value=mock_result),
        patch("backend.main.LLMRouter") as MockRouter,
    ):
        MockRouter.return_value.call.return_value = "Refunds take 7 days."
        response = client.post(
            "/query",
            json={"query": "what is the refund policy?", "conversation_id": "test-session-1"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Refunds take 7 days."
    assert data["intent"] == "fact"
    assert len(data["chunks"]) == 1


def test_query_same_conversation_id_reuses_history(mock_pipeline):
    """Second query with same conversation_id should reuse the ConversationHistory."""
    client, mock_state = mock_pipeline
    mock_result = MagicMock()
    mock_result.chunks = []
    mock_result.intent = "conversational"
    mock_result.scope = None
    mock_result.total_tokens = 0

    with (
        patch("backend.main.retrieve", return_value=mock_result),
        patch("backend.main.LLMRouter") as MockRouter,
    ):
        MockRouter.return_value.call.return_value = "Sure."
        client.post("/query", json={"query": "hello", "conversation_id": "shared-session"})
        client.post("/query", json={"query": "and then?", "conversation_id": "shared-session"})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
