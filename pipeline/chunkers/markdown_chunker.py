"""
Markdown chunker using ## and ### markers.
Emits 11-field chunk schema with chunk_type="headed" and heading_confidence="high".
"""
from typing import List, Dict, Any
import tiktoken
from pipeline.state.chunking_config import ChunkingConfig


def chunk_markdown(text: str, source_doc: str, config: ChunkingConfig) -> List[Dict[str, Any]]:
    """
    Chunk a markdown document using ## and ### markers.
    
    Boundary detection is unambiguous — no heuristic needed, just split on ## and ###.
    Always emits chunk_type="headed" and heading_confidence="high".
    
    Args:
        text: Full markdown document text
        source_doc: Relative path from dataset/ root (e.g. "docs/readme.md")
        config: ChunkingConfig with max_chars and overlap_chars for this doc size
        
    Returns:
        List of chunk dicts with 11 fields each
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    chunks = []
    
    lines = text.split("\n")
    section_heading = ""
    subsection_heading = ""
    current_chunk_lines = []
    section_idx = 0
    subsection_idx = 0
    
    for line in lines:
        # Check for section heading (##)
        if line.startswith("## "):
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
                current_chunk_lines = []
            
            # Update section heading
            section_heading = line[3:].strip()  # Remove "## "
            section_idx += 1
            subsection_idx = 0
        
        # Check for subsection heading (###)
        elif line.startswith("### "):
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
                current_chunk_lines = []
            
            # Update subsection heading
            subsection_heading = line[4:].strip()  # Remove "### "
            subsection_idx += 1
        
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
                
                # Start new chunk with overlap from end of previous chunk
                overlap_lines = current_chunk_lines[-(config.overlap_chars // 100):]  # Rough approx
                current_chunk_lines = overlap_lines + [line]
    
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
        section_idx: Section index (00-99)
        subsection_idx: Subsection index (00-99)
        chunk_idx: Chunk index within subsection (00-99)
        encoding: tiktoken encoding (cl100k_base)
        
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
    
    # Calculate document position ratio (using character count as proxy)
    position_ratio = 0.5  # Placeholder — would need full doc length
    
    # Calculate token count of text field
    token_count = len(encoding.encode(text))
    
    # Build anchor (human-readable path)
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
