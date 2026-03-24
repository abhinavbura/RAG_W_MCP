"""
Document structure detection and heading heuristics.
"""
import re
from typing import List


MAX_HEADING_LEN = 60  # Headings longer than this are unlikely


def detect_structure(text: str) -> str:
    """
    Detect whether a document has structured headings or flat prose.
    
    Strategy: Two-zone sampling
    - Zone 1: First 50 non-empty lines
    - Zone 2: Middle 50 non-empty lines (centred at total_lines / 2)
    - Heading score = heading_lines / total_sampled per zone
    - Take peak score. If >= 0.05 → "structured", else "flat"
    
    Args:
        text: Document text
        
    Returns:
        "structured" or "flat"
    """
    lines = [line for line in text.split("\n") if line.strip()]
    
    if len(lines) == 0:
        # Edge case: empty document
        return "flat"
    
    # Zone 1: First 50 non-empty lines
    zone1_lines = lines[:min(50, len(lines))]
    zone1_headings = sum(1 for line in zone1_lines if _is_heading_line(line))
    zone1_score = zone1_headings / len(zone1_lines) if zone1_lines else 0.0
    
    # Zone 2: Middle 50 non-empty lines (centred at total_lines / 2)
    mid_idx = len(lines) // 2
    start_idx = max(0, mid_idx - 25)
    end_idx = min(len(lines), mid_idx + 25)
    zone2_lines = lines[start_idx:end_idx]
    zone2_headings = sum(1 for line in zone2_lines if _is_heading_line(line))
    zone2_score = zone2_headings / len(zone2_lines) if zone2_lines else 0.0
    
    # Take peak score across both zones
    peak_score = max(zone1_score, zone2_score)
    
    # Threshold: >= 0.05 (at least 1 in 20 sampled lines must look like a heading)
    return "structured" if peak_score >= 0.05 else "flat"


def _is_heading_line(line: str) -> bool:
    """
    Detect if a line is a heading using 5 heuristics.
    Conservative — would rather miss a heading than falsely split a sentence.
    
    Heuristics:
    1. Markdown markers: line starts with #, ##, or ###
    2. Numbered patterns: 1. / 1.1 / Section N / Chapter N
    3. ALL CAPS: line.isupper() is True and len >= 3
    4. Title Case: line.istitle() is True and word_count >= 2
    5. Colon-terminated: ends with ":" and word_count <= 6
    
    Args:
        line: Single line of text
        
    Returns:
        True if line appears to be a heading
    """
    line = line.strip()
    
    if not line or len(line) > MAX_HEADING_LEN:
        return False
    
    # Heuristic 1: Markdown markers
    if line.startswith(("# ", "## ", "### ")):
        return True
    
    # Heuristic 2: Numbered patterns (1. / 1.1 / Section N / Chapter N)
    # Match: "1.", "1.1", "1.1.1", "Section 1", "Chapter 1", etc.
    if re.match(r"^(\d+\.?)+\s+|^(section|chapter|part|unit)\s+\d+", line, re.IGNORECASE):
        return True
    
    # Heuristic 3: ALL CAPS (but not acronyms like "OK" or "ID")
    if line.isupper() and len(line) >= 3:
        return True
    
    # Heuristic 4: Title Case with >= 2 words
    word_count = len(line.split())
    if line.istitle() and word_count >= 2:
        return True
    
    # Heuristic 5: Colon-terminated with <= 6 words
    if line.endswith(":") and word_count <= 6:
        return True
    
    return False


def _heading_level(line: str) -> int:
    """
    Map heading heuristics to level 1 (section) or level 2 (subsection).
    Mirrors ## vs ### from markdown chunker.
    
    Args:
        line: Heading line text
        
    Returns:
        1 for section-level, 2 for subsection-level
    """
    line = line.strip()
    
    # Markdown markers: # and ## are section, ### and beyond are subsection
    if line.startswith("### "):
        return 2
    if line.startswith(("# ", "## ")):
        return 1
    
    # Numbered patterns: 1., 1.1, 1.1.1 detect subsection depth
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", line)
    if match:
        if match.group(3):  # e.g. 1.1.1 — subsection
            return 2
        elif match.group(2):  # e.g. 1.1 — subsection
            return 2
        else:  # e.g. 1 — section
            return 1
    
    # Section/Chapter markers
    if re.match(r"^(section|chapter|part|unit)\s+\d+", line, re.IGNORECASE):
        # Check if it has further numbering (e.g. "Section 1.1")
        if re.search(r"\d+\.\d+", line):
            return 2
        return 1
    
    # Title Case and ALL CAPS default to section
    # Colon-terminated defaults to section
    return 1


def _clean_heading(line: str) -> str:
    """
    Clean heading text for storage.
    Strips: ## markers, numbered prefixes, Section/Chapter labels, trailing colons.
    
    Args:
        line: Raw heading line
        
    Returns:
        Cleaned heading text
    """
    line = line.strip()
    
    # Strip markdown markers
    line = re.sub(r"^#+\s*", "", line)
    
    # Strip numbered prefixes (1. / 1.1 / etc.)
    line = re.sub(r"^(\d+\.?)+\s+", "", line)
    
    # Strip Section/Chapter/Part/Unit labels
    line = re.sub(r"^(section|chapter|part|unit)\s+\d+(?:\.\d+)*\s*:?\s*", "", line, flags=re.IGNORECASE)
    
    # Strip trailing colons
    line = re.sub(r"\s*:$", "", line)
    
    return line.strip()
