"""
FastAPI application — 4 endpoints + SSE progress stream.

Startup: loads PipelineState from .rag_state.json if it exists.
All pipeline calls use the single module-level `state` object.
"""
import asyncio
import json
import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from pipeline.state.pipeline_state import PipelineState
from pipeline.state.conversation import ConversationTurn
from pipeline.state.chunking_config import get_config
from pipeline.llm.router import LLMRouter
from pipeline.retrieval.retrieve import retrieve
from pipeline.ingestion.ingest_folder import ingest_folder
import backend.conversation_store as conv_store

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Global queue for streaming server logs
_log_queue: asyncio.Queue = asyncio.Queue()

class AsyncLogQueueHandler(logging.Handler):
    """Pushes log records to an asyncio.Queue for SSE streaming."""
    def emit(self, record: logging.LogRecord):
        # Ignore uvicorn access logs to avoid infinite loop / noise
        if "uvicorn.access" in record.name:
            return
        try:
            loop = asyncio.get_running_loop()
            log_entry = {
                "level": record.levelname,
                "message": record.getMessage(),
                "name": record.name
            }
            loop.call_soon_threadsafe(_log_queue.put_nowait, log_entry)
        except Exception:
            pass

# Attach custom handler to the root logger
_queue_handler = AsyncLogQueueHandler()
_queue_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(_queue_handler)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATASET_PATH = Path(os.environ.get("DATASET_PATH", "./dataset"))
PROCESSED_PATH = DATASET_PATH / "processed"
STATE_PATH = DATASET_PATH / ".rag_state.json"
ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}

# ---------------------------------------------------------------------------
# Module-level state (shared across all requests)
# ---------------------------------------------------------------------------
state: PipelineState = None  # type: ignore[assignment]

# SSE: keyed by ingest-run-id
_ingest_queues: Dict[str, asyncio.Queue] = {}

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global state
    DATASET_PATH.mkdir(parents=True, exist_ok=True)
    PROCESSED_PATH.mkdir(parents=True, exist_ok=True)

    if STATE_PATH.exists():
        try:
            state = PipelineState.load(str(STATE_PATH))
            logger.info("Loaded PipelineState from %s", STATE_PATH)
        except Exception as exc:
            logger.warning("Could not load state: %s. Starting fresh.", exc)
            state = PipelineState(folder_path=str(DATASET_PATH))
    else:
        state = PipelineState(folder_path=str(DATASET_PATH))
        logger.info("Starting with fresh PipelineState.")

    yield

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="RAG Pipeline API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    conversation_id: str

# ---------------------------------------------------------------------------
# POST /ingest
# ---------------------------------------------------------------------------

@app.post("/ingest")
async def ingest(files: List[UploadFile], background_tasks: BackgroundTasks):
    saved: List[str] = []
    rejected: List[str] = []

    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            rejected.append(file.filename)
            continue

        dest = DATASET_PATH / file.filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        saved.append(file.filename)

    if rejected:
        raise HTTPException(
            status_code=400,
            detail=f"Rejected files (unsupported type): {rejected}. Allowed: .md .txt .pdf",
        )

    # Create a queue for SSE progress
    run_id = f"run-{len(_ingest_queues) + 1}"
    q: asyncio.Queue = asyncio.Queue()
    _ingest_queues[run_id] = q

    background_tasks.add_task(_run_ingest, run_id, q)

    return {"status": "accepted", "files_received": saved, "run_id": run_id}


async def _run_ingest(run_id: str, q: asyncio.Queue):
    """Run ingest_folder in a thread, feeding events into the SSE queue."""
    global state
    loop = asyncio.get_event_loop()

    def _progress_callback(event: dict):
        loop.call_soon_threadsafe(q.put_nowait, event)

    try:
        state = await asyncio.to_thread(
            ingest_folder, str(DATASET_PATH), _progress_callback
        )
    except Exception as exc:
        logger.error("ingest_folder failed: %s", exc)
        await q.put({"type": "error", "message": str(exc)})
    finally:
        await q.put(None)  # sentinel — signals stream end


# ---------------------------------------------------------------------------
# GET /ingest/progress  (SSE)
# ---------------------------------------------------------------------------

@app.get("/ingest/progress")
async def ingest_progress(run_id: str):
    q = _ingest_queues.get(run_id)
    if q is None:
        raise HTTPException(status_code=404, detail="run_id not found")

    async def event_generator():
        while True:
            event = await q.get()
            if event is None:
                break
            yield {"data": json.dumps(event)}
        _ingest_queues.pop(run_id, None)

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# GET /logs/stream  (SSE)
# ---------------------------------------------------------------------------

@app.get("/logs/stream")
async def logs_stream():
    """Stream live server logs to the frontend via SSE."""
    async def event_generator():
        while True:
            try:
                # Use a small timeout so we can periodically check for client disconnects if needed
                # However, await q.get() is usually fine as starlette handles disconnects.
                event = await _log_queue.get()
                yield {"data": json.dumps(event)}
            except asyncio.CancelledError:
                break

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# POST /query
# ---------------------------------------------------------------------------

@app.post("/query")
async def query(req: QueryRequest):
    if state is None or state._collection is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready. Ingest documents first.")

    history = conv_store.get_or_create(req.conversation_id)

    # Retrieval
    result = await asyncio.to_thread(retrieve, req.query, state, history)

    # Build LLM prompt from retrieved chunks
    context_parts = []
    for chunk in result.chunks:
        anchor = chunk.get("anchor", chunk.get("section", ""))
        text = chunk.get("text", "")
        context_parts.append(f"[{anchor}]\n{text}")
    context = "\n\n---\n\n".join(context_parts)

    system_prompt = (
        "You are a helpful assistant. Answer the user's question using ONLY the provided context. "
        "If the context doesn't contain the answer, say so clearly. "
        "Be concise and accurate."
    )
    user_prompt = f"Context:\n{context}\n\nQuestion: {req.query}"

    router = LLMRouter(state)
    answer = await asyncio.to_thread(router.call, "answer", user_prompt, system_prompt)

    # Append turn to history
    config = get_config(chunk_count=state.collection_count)
    turn = ConversationTurn(
        query=req.query,
        intent=result.intent,
        chunks=result.chunks,
        token_count=result.total_tokens,
    )
    history.add_turn(turn)

    return {
        "answer": answer,
        "chunks": result.chunks,
        "intent": result.intent,
        "scope": result.scope,
        "total_tokens": result.total_tokens,
    }


# ---------------------------------------------------------------------------
# GET /state
# ---------------------------------------------------------------------------

@app.get("/state")
async def get_state():
    if state is None:
        return {"status": "not_initialised"}
    d = state.to_dict()
    # Return only the fields relevant to the frontend
    return {
        "collection_count": d.get("collection_count", 0),
        "model_key": d.get("model_key", ""),
        "ingested_files": d.get("ingested_files", []),
        "skipped_files": d.get("skipped_files", []),
        "failed_files": d.get("failed_files", []),
        "total_chunks_added": d.get("total_chunks_added", 0),
        "model_upgrade_warning": d.get("model_upgrade_warning", ""),
        "llm_tokens_used_deepseek": d.get("llm_tokens_used_deepseek", 0),
        "llm_tokens_used_gpt": d.get("llm_tokens_used_gpt", 0),
    }
