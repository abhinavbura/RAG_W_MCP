"""
File readers for MD, TXT, and PDF files.
"""
from pathlib import Path
from typing import Optional


def read_md(path: str) -> str:
    """
    Read markdown file as UTF-8 text.
    
    Args:
        path: Absolute or relative path to .md file
        
    Returns:
        File contents as string
        
    Raises:
        FileNotFoundError: If file does not exist
        IOError: If file cannot be read
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        raise IOError(f"Failed to read markdown file {path}: {str(e)}")


def read_txt(path: str) -> str:
    """
    Read text file as UTF-8 text.
    
    Args:
        path: Absolute or relative path to .txt file
        
    Returns:
        File contents as string
        
    Raises:
        FileNotFoundError: If file does not exist
        IOError: If file cannot be read
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        raise IOError(f"Failed to read text file {path}: {str(e)}")


def read_pdf(path: str) -> str:
    """
    Read PDF file and extract text from text layer.
    
    Strategy:
    - Per page: call get_text("text")
    - Skip pages where extracted text < 20 chars (image-only or scanned pages)
    - Strip individual lines under 3 chars (image artifact noise)
    - Raise ValueError if no pages yield text
    
    Args:
        path: Absolute or relative path to .pdf file
        
    Returns:
        Combined text from all valid pages
        
    Raises:
        ValueError: If no text-layer pages found in PDF
        IOError: If PDF cannot be read
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("PyMuPDF (fitz) required for PDF reading. Install with: pip install pymupdf")
    
    try:
        doc = fitz.open(path)
    except Exception as e:
        raise IOError(f"Failed to open PDF file {path}: {str(e)}")
    
    all_text = []
    valid_pages = 0
    
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            
            # Skip pages with insufficient text (image-only or scanned)
            if len(text.strip()) < 20:
                continue
            
            # Strip lines under 3 chars (image artifact noise)
            lines = text.split("\n")
            filtered_lines = [line for line in lines if len(line.strip()) >= 3 or line.strip() == ""]
            page_text = "\n".join(filtered_lines)
            
            if page_text.strip():
                all_text.append(page_text)
                valid_pages += 1
    finally:
        doc.close()
    
    if valid_pages == 0:
        raise ValueError(f"No text-layer pages found in PDF {path}. PDF may be image-only or scanned.")
    
    return "\n\n".join(all_text)
