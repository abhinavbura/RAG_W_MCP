# FastAPI application — 4 endpoints
#
# POST /ingest
#   Accepts List[UploadFile]. Validates extensions (.md .txt .pdf only — 400 otherwise).
#   Streams files to dataset/ via shutil.copyfileobj.
#   Kicks off ingest_folder() as BackgroundTask.
#   Returns {status, files_received}.
#
# POST /query
#   Body: {query, conversation_id}
#   Loads or creates ConversationHistory for conversation_id.
#   Calls retrieve() -> LLMRouter.call("answer") -> appends turn.
#   Returns {answer, chunks, intent, scope, total_tokens}.
#
# GET /state
#   Returns serialised PipelineState: collection_count, model_key,
#   ingested_files, session stats, model_upgrade_warning.
#
# GET /ingest/progress  (SSE)
#   EventSourceResponse stream.
#   Yields one event per file: {filename, status, chunks_added, error}.
#   Final summary event: {total_ingested, total_skipped, total_failed, collection_count}.
