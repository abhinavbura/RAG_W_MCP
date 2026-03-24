"""
Chunk dispatcher — routes to appropriate chunker based on file type and structure.
Pops text_for_embedding from chunks after chunking (used at embed time only).
"""
from typing import List, Dict, Any
from pipeline.state.chunking_config import ChunkingConfig
from pipeline.chunkers.structure_detector import detect_structure
from pipeline.chunkers.markdown_chunker import chunk_markdown
from pipeline.chunkers.structured_chunker import chunk_txt_structured
from pipeline.chunkers.semantic_chunker import chunk_txt_semantic


def chunk_document(
    text: str,
    source_doc: str,
    file_type: str,
    config: ChunkingConfig,
    model: Any = None,
) -> List[Dict[str, Any]]:
    """
    Dispatcher — route to correct chunker based on file_type and structure.
    
    Routing logic:
    - file_type == "md" → chunk_markdown()
    - file_type in ["txt", "pdf"] + structure == "structured" → chunk_txt_structured()
    - file_type in ["txt", "pdf"] + structure == "flat" → chunk_txt_semantic() (requires model)
    
    Post-processing:
    - Pops text_for_embedding from each chunk (used at embed-time, never stored in ChromaDB)
    
    Args:
        text: Document text
        source_doc: Relative path from dataset/ root
        file_type: "md" | "txt" | "pdf"
        config: ChunkingConfig for this doc/collection size
        model: SentenceTransformer instance (required for semantic chunking)
        
    Returns:
        List of chunks with 11 fields each, text_for_embedding already popped
    """
    if file_type == "md":
        # Markdown file — use ## and ### markers
        chunks = chunk_markdown(text, source_doc, config)
    
    elif file_type in ["txt", "pdf"]:
        # TXT or PDF — detect structure first
        structure = detect_structure(text)
        
        if structure == "structured":
            # Has headings — use heuristic-based chunking
            chunks = chunk_txt_structured(text, source_doc, config)
        else:
            # Flat prose — use semantic similarity-based chunking
            if model is None:
                raise ValueError("Model required for semantic chunking")
            chunks = chunk_txt_semantic(text, source_doc, config, model)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
    
    # Pop text_for_embedding from each chunk (used at embed time, never stored)
    for chunk in chunks:
        chunk.pop("text_for_embedding", None)
    
    return chunks
