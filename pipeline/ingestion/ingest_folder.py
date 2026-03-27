"""
Four-phase ingestion pipeline entry point.
Scan → Model Selection → Per-File Loop → Finalise
PipelineState saved after every file — crash recovery by design.
"""
from pathlib import Path
from typing import Callable, Optional
import logging
from pipeline.state.pipeline_state import PipelineState, FileMetadata
from pipeline.state.chunking_config import get_config
from pipeline.chunkers.structure_detector import detect_structure
from pipeline.chunkers.chunk_document import chunk_document
from pipeline.ingestion.readers import read_md, read_txt, read_pdf
from pipeline.ingestion.hash_store import _hash_file, _load_hash_store, _save_hash_store
from pipeline.ingestion.archive import _archive_file
from pipeline.ingestion.model_loader import _get_or_load_model, select_model_for_folder_size


logger = logging.getLogger(__name__)


def ingest_folder(
    folder_path: str,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> PipelineState:
    """
    Four-phase ingestion pipeline.

    Phase 1 — Scan: Find all files, compute hashes, classify new/changed/unchanged
    Phase 2 — Model: Select embedding model based on cumulative folder size
    Phase 3 — Per-file: Read → detect → chunk → embed → store → archive
    Phase 4 — Finalise: Save hash store, collection count, state

    PipelineState is saved after every file — crash recovery by design.

    Args:
        folder_path:       Absolute path to dataset/ folder.
        progress_callback: Optional callable that receives a dict per event:
                           per-file: {type, filename, status, chunks_added, error}
                           final:    {type, total_ingested, total_skipped,
                                     total_failed, collection_count}

    Returns:
        PipelineState with all metadata and session statistics

    Raises:
        ValueError: If folder does not exist or is invalid
    """
    folder_path = str(Path(folder_path).resolve())
    if not Path(folder_path).is_dir():
        raise ValueError(f"Folder does not exist: {folder_path}")
    
    # Initialize state
    state = PipelineState(folder_path=folder_path)
    state.generate_session_id()
    
    logger.info(f"Starting ingestion session {state.session_id} in {folder_path}")
    
    try:
        # Phase 1 — Scan
        logger.info("Phase 1: Scanning folder...")
        _phase1_scan(state, folder_path)
        logger.info(f"  Found {state.total_files} files ({state.total_size_chars} chars total)")
        logger.info(f"  Files to ingest: {len(state.files_to_ingest)}")
        
        # Phase 2 — Model Selection
        logger.info("Phase 2: Model selection...")
        _phase2_model_select(state, folder_path)
        logger.info(f"  Model: {state.model_key} ({state.model_name})")
        if state.model_upgrade_warning:
            logger.warning(f"  ⚠️  {state.model_upgrade_warning}")
        
        # Phase 3 — Per-File Loop
        logger.info(f"Phase 3: Processing {len(state.files_to_ingest)} files...")
        _phase3_per_file_loop(state, folder_path, progress_callback)
        logger.info(f"  Ingested: {len(state.ingested_files)}")
        logger.info(f"  Skipped: {len(state.skipped_files)}")
        logger.info(f"  Failed: {len(state.failed_files)}")
        logger.info(f"  Total chunks added: {state.total_chunks_added}")
        
        # Phase 4 — Finalise
        logger.info("Phase 4: Finalizing...")
        _phase4_finalise(state, folder_path)
        if progress_callback:
            progress_callback({
                "type": "summary",
                "total_ingested": len(state.ingested_files),
                "total_skipped": len(state.skipped_files),
                "total_failed": len(state.failed_files),
                "collection_count": state.collection_count,
            })
        logger.info(f"  Collection total: {state.collection_count} chunks")
        
        logger.info(f"✓ Ingestion complete (session {state.session_id})")
        return state
        
    except Exception as e:
        logger.error(f"✗ Ingestion failed: {str(e)}")
        state.record_failed("INGESTION_PIPELINE", str(e))
        state.save(str(Path(folder_path) / ".rag_state.json"))
        raise


def _phase1_scan(state: PipelineState, folder_path: str) -> None:
    """Phase 1: Scan folder and classify files."""
    hash_store = _load_hash_store(folder_path)
    
    folder = Path(folder_path)
    files = sorted(folder.rglob("*"))
    
    for file_path in files:
        if not file_path.is_file():
            continue
        
        # Check file extension
        ext = file_path.suffix.lower()
        if ext not in [".md", ".txt", ".pdf"]:
            continue
        
        state.total_files += 1
        
        try:
            # Read file and compute metadata
            if ext == ".md":
                text = read_md(str(file_path))
            elif ext == ".txt":
                text = read_txt(str(file_path))
            else:  # .pdf
                text = read_pdf(str(file_path))
            
            size_chars = len(text)
            state.total_size_chars += size_chars
            
            # Compute MD5 hash
            file_hash = _hash_file(str(file_path))
            
            # Classify file
            relative_path = str(file_path.relative_to(folder))
            status = "unchanged"
            if relative_path not in hash_store:
                status = "new"
            elif hash_store[relative_path] != file_hash:
                status = "changed"
            
            # Create FileMetadata
            fm = FileMetadata(
                path=relative_path,
                file_type=ext[1:],  # "md", "txt", "pdf"
                size_chars=size_chars,
                hash=file_hash,
                status=status,
            )
            state.files_metadata.append(fm)
            
            # Add to files_to_ingest if new or changed
            if status in ["new", "changed"]:
                state.files_to_ingest.append(relative_path)
            else:
                state.record_skipped(relative_path)
                
        except Exception as e:
            logger.error(f"Error scanning {file_path}: {str(e)}")
            fm = FileMetadata(
                path=str(file_path.relative_to(folder)),
                file_type=ext[1:],
                size_chars=0,
                hash="",
                status="failed",
                error=str(e),
            )
            state.files_metadata.append(fm)


def _phase2_model_select(state: PipelineState, folder_path: str) -> None:
    """Phase 2: Model selection."""
    try:
        import chromadb
    except ImportError:
        raise ImportError("chromadb required. Install with: pip install chromadb")
    
    # Initialize ChromaDB client
    db_path = str(Path(folder_path).parent / "chroma_db")
    client = chromadb.PersistentClient(path=db_path)
    state.db_path = db_path
    
    # Check if collection exists
    try:
        collection = client.get_collection(name=state.collection_name)
        state.collection_exists = True
        
        # Read model_key from metadata
        metadata = collection.metadata
        if "model_key" in metadata:
            state.model_key = metadata["model_key"]
            state.model_source = "collection_metadata"
            logger.info(f"  Using existing model: {state.model_key}")
        else:
            logger.warning("  Existing collection has no model_key metadata")
            
    except Exception:
        # Collection doesn't exist — select model from folder size
        state.collection_exists = False
        state.model_key = select_model_for_folder_size(state.total_size_chars)
        state.model_source = "computed"
        logger.info(f"  New collection — selected model: {state.model_key}")
    
    # Get model info
    from pipeline.ingestion.model_loader import get_model_info
    model_info = get_model_info(state.model_key)
    state.model_name = model_info["name"]
    state.model_dims = model_info["dims"]
    state.model_ctx_tokens = model_info["ctx_tokens"]
    state.requires_prefix = model_info["requires_prefix"]
    state.query_prefix = model_info["query_prefix"]
    state.doc_prefix = model_info["doc_prefix"]
    
    # Check if folder outgrew locked model
    if state.collection_exists:
        upgraded_model = select_model_for_folder_size(state.total_size_chars)
        if upgraded_model != state.model_key:
            state.model_upgrade_warning = (
                f"Folder size ({state.total_size_chars} chars) now warrants {upgraded_model}, "
                f"but collection is locked to {state.model_key}. Wipe and re-ingest to upgrade."
            )
    
    # Load model
    model = _get_or_load_model(state.model_key)
    state._model_instance = model
    
    # Get or create collection
    if state.collection_exists:
        state._collection = client.get_collection(name=state.collection_name)
    else:
        state._collection = client.create_collection(
            name=state.collection_name,
            metadata={"hnsw:space": "cosine", "model_key": state.model_key}
        )


def _phase3_per_file_loop(
    state: PipelineState,
    folder_path: str,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> None:
    """Phase 3: Per-file processing loop."""
    folder = Path(folder_path)
    
    for relative_path in state.files_to_ingest:
        file_path = folder / relative_path
        
        try:
            logger.info(f"  Processing {relative_path}...")
            
            # Find FileMetadata for this file
            fm = None
            for file_meta in state.files_metadata:
                if file_meta.path == relative_path:
                    fm = file_meta
                    break
            
            if not fm:
                raise ValueError(f"FileMetadata not found for {relative_path}")
            
            # Read file
            ext = file_path.suffix.lower()[1:]  # "md", "txt", "pdf"
            if ext == "md":
                text = read_md(str(file_path))
            elif ext == "txt":
                text = read_txt(str(file_path))
            else:  # pdf
                text = read_pdf(str(file_path))
            
            # Detect structure
            structure = detect_structure(text)
            
            # Get config
            config = get_config(text=text, chunk_count=state.collection_count)
            
            # Update current file state
            state.set_current_file(fm, "large" if len(text) > 500000 else "medium" if len(text) > 100000 else "small", structure, "semantic" if structure == "flat" else "structured", config.to_dict())
            
            # Chunk document
            chunks = chunk_document(text, relative_path, ext, config, state._model_instance)
            
            # Clean up: text_for_embedding already popped in chunk_document()
            
            # Embed chunks
            embeds_texts = []
            for chunk in chunks:
                # Reconstruct text_for_embedding for embedding (with heading prepended)
                embed_text = chunk["text"]
                if chunk["section"]:
                    embed_text = chunk["section"] + "\n" + embed_text
                if chunk["subsection"]:
                    embed_text = chunk["subsection"] + "\n" + embed_text
                embeds_texts.append(embed_text)
            
            embeddings = state._model_instance.encode(embeds_texts, batch_size=32, show_progress_bar=False)
            
            # Delete old chunks for this file
            try:
                old_ids = state._collection.get(
                    where={"source_doc": {"$eq": relative_path}}
                )["ids"]
                if old_ids:
                    state._collection.delete(ids=old_ids)
            except Exception:
                pass  # No old chunks to delete
            
            # Store new chunks
            state._collection.add(
                ids=[chunk["id"] for chunk in chunks],
                embeddings=embeddings.tolist(),
                documents=[chunk["text"] for chunk in chunks],
                metadatas=[{
                    "source_doc": chunk["source_doc"],
                    "section": chunk["section"],
                    "subsection": chunk["subsection"],
                    "chunk_type": chunk["chunk_type"],
                    "position_ratio": chunk["position_ratio"],
                    "token_count": chunk["token_count"],
                } for chunk in chunks],
            )
            
            # Archive file
            _archive_file(str(file_path), folder_path)
            
            # Record success
            state.record_ingested(relative_path, len(chunks))
            state.save(str(folder / ".rag_state.json"))
            logger.info(f"    ✓ {len(chunks)} chunks ingested")
            if progress_callback:
                progress_callback({
                    "type": "file",
                    "filename": relative_path,
                    "status": "ingested",
                    "chunks_added": len(chunks),
                    "error": "",
                })
            
        except Exception as e:
            logger.error(f"    ✗ Failed: {str(e)}")
            state.record_failed(relative_path, str(e))
            state.save(str(folder / ".rag_state.json"))
            if progress_callback:
                progress_callback({
                    "type": "file",
                    "filename": relative_path,
                    "status": "failed",
                    "chunks_added": 0,
                    "error": str(e),
                })


def _phase4_finalise(state: PipelineState, folder_path: str) -> None:
    """Phase 4: Finalize and save state."""
    # Build final hash store (only successfully archived files)
    final_hashes = {}
    for fm in state.files_metadata:
        if fm.status == "ingested":
            final_hashes[fm.path] = fm.hash
    
    # Save hash store
    _save_hash_store(folder_path, final_hashes)
    
    # Update collection count
    if state._collection:
        state.update_collection_count(state._collection)
    
    # Save final state
    state.save(str(Path(folder_path) / ".rag_state.json"))
