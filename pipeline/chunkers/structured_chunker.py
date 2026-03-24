"""
Structured text chunker using heading heuristics.
Triggered for TXT/PDF files with detected structure.
Emits 11-field chunk schema with chunk_type="headed" and heading_confidence="high".
"""
from typing import List, Dict, Any
import tiktoken
from pipeline.state.chunking_config import ChunkingConfig
from pipeline.chunkers.structure_detector import _is_heading_line, _heading_level, _clean_heading


def chunk_txt_structured(text: str, source_doc: str, config: ChunkingConfig) -> List[Dict[str, Any]]:
    """
    Chunk a structured text document using heading heuristics.
    
    Uses _is_heading_line() for boundary detection (same 5 heuristics as structure detection).
    Always emits chunk_type="headed" and heading_confidence="high".
    
    Args:
        text: Full text document
        source_doc: Relative path from dataset/ root
        config: ChunkingConfig with parameters for this doc size
        
    Returns:
        List of chunk dicts with 11 fields each
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    chunks = []
    
    lines = text.split("\n")
    section_heading = ""
    subsection_heading = ""
    section_idx = 0
    subsection_idx = 0
    current_chunk_lines = []
    
    for line in lines:
        # Check if this line is a heading
        if _is_heading_line(line):
            # Flush current chunk if it exists
            if current_chunk_lines:
                chunk_dict = _create_chunk(
                    text="\n".join(current_chunk_lines),
                    section=section_heading,
                    subsection=subsection_heading,
                    source_doc=source_doc,
                    section_idx=section_idx,
                    subsection_idx=subsection_idx,
                    chunk_idx=len(chunks),
                    encoding=encoding,
                )
                chunks.append(chunk_dict)
            
            # Determine heading level
            level = _heading_level(line)
            cleaned = _clean_heading(line)
            
            if level == 1:
                # Section-level heading
                section_heading = cleaned
                section_idx += 1
                subsection_idx = 0
                subsection_heading = ""
            else:
                # Subsection-level heading
                subsection_heading = cleaned
                subsection_idx += 1
            
            current_chunk_lines = []
        else:
            # Regular content line
            current_chunk_lines.append(line)
            
            # Check if chunk is getting too large
            chunk_text = "\n".join(current_chunk_lines)
            if len(chunk_text) > config.max_chars:
                # Remove last line to bring under limit
                current_chunk_lines.pop()
                
                # Flush this chunk
                if current_chunk_lines:
                    chunk_dict = _create_chunk(
                        text="\n".join(current_chunk_lines),
                        section=section_heading,
                        subsection=subsection_heading,
                        source_doc=source_doc,
                        section_idx=section_idx,
                        subsection_idx=subsection_idx,
                        chunk_idx=len(chunks),
                        encoding=encoding,
                    )
                    chunks.append(chunk_dict)
                
                # Start new chunk with character-level overlap
                if config.overlap_chars > 0:
                    chunk_text = "\n".join(current_chunk_lines)
                    overlap_text = chunk_text[-config.overlap_chars:] if len(chunk_text) >= config.overlap_chars else chunk_text
                    current_chunk_lines = overlap_text.split("\n") + [line]
                else:
                    current_chunk_lines = [line]
    
    # Flush final chunk
    if current_chunk_lines:
        chunk_dict = _create_chunk(
            text="\n".join(current_chunk_lines),
            section=section_heading,
            subsection=subsection_heading,
            source_doc=source_doc,
            section_idx=section_idx,
            subsection_idx=subsection_idx,
            chunk_idx=len(chunks),
            encoding=encoding,
        )
        chunks.append(chunk_dict)
    
    return chunks


def _create_chunk(
    text: str,
    section: str,
    subsection: str,
    source_doc: str,
    section_idx: int,
    subsection_idx: int,
    chunk_idx: int,
    encoding: Any,
) -> Dict[str, Any]:
    """
    Create a single chunk dict with all 11 fields.
    
    Args:
        text: Chunk body text
        section: Section heading
        subsection: Subsection heading
        source_doc: Relative source document path
        section_idx: Section index
        subsection_idx: Subsection index
        chunk_idx: Chunk index
        encoding: tiktoken encoding
        
    Returns:
        Dict with all 11 fields for this chunk
    """
    # Build text_for_embedding: prepend section and subsection headings
    embedding_text_parts = []
    if section:
        embedding_text_parts.append(section)
    if subsection:
        embedding_text_parts.append(subsection)
    if embedding_text_parts:
        embedding_text_parts.append("")  # Blank line separator
    embedding_text_parts.append(text)
    text_for_embedding = "\n".join(embedding_text_parts)
    
    # Calculate position ratio (placeholder)
    position_ratio = 0.5
    
    # Calculate token count of text field
    token_count = len(encoding.encode(text))
    
    # Build anchor
    anchor_parts = []
    if section:
        anchor_parts.append(section)
    if subsection:
        anchor_parts.append(subsection)
    anchor = " > ".join(anchor_parts) if anchor_parts else ""
    
    # Build unique id
    chunk_id = f"{source_doc}_{section_idx:02d}_{subsection_idx:02d}_{chunk_idx:02d}"
    
    return {
        "id": chunk_id,
        "text": text,
        "text_for_embedding": text_for_embedding,
        "section": section,
        "subsection": subsection,
        "anchor": anchor,
        "source_doc": source_doc,
        "chunk_type": "headed",
        "heading_confidence": "high",
        "position_ratio": position_ratio,
        "token_count": token_count,
    }
