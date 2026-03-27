"""
Section extraction for comparison-intent queries.

Called only when intent == "comparison".
Makes a single DeepSeek call with a constrained system prompt.
The LLM picks from the KNOWN section list — it cannot hallucinate a section name.

Fallback: returns None on any parse failure or if sections aren't in the known list.
Caller falls back to a full-collection search with no section filter.
"""
import json
import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# Strip markdown code fences that LLMs sometimes wrap JSON in
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_sections_llm(
    query: str,
    known_sections: List[str],
    llm_router,
) -> Optional[List[str]]:
    """
    Ask the LLM to identify the two sections being compared in a query.

    Args:
        query:          The user's comparison query.
        known_sections: Distinct section names currently in ChromaDB metadata.
        llm_router:     LLMRouter — routes to DeepSeek (free-tier, JSON task).

    Returns:
        [section_a, section_b] — both guaranteed to be in known_sections.
        Returns None if extraction fails or sections cannot be validated.
    """
    if not known_sections:
        logger.debug("No known sections available — skipping section extraction.")
        return None

    system_prompt = (
        "You extract exactly two section names that are being compared in a query. "
        "Respond with a single JSON object and nothing else: "
        '{"section_a": "<name>", "section_b": "<name>"}. '
        "Both values MUST be copied verbatim from the provided section list."
    )
    sections_list = "\n".join(f"- {s}" for s in known_sections)
    user_prompt = f"Query: {query}\n\nAvailable sections:\n{sections_list}"

    try:
        raw = llm_router.call("extract", user_prompt, system_prompt)

        # Strip markdown code fences if present
        fence_match = _CODE_FENCE_RE.search(raw)
        json_str = fence_match.group(1) if fence_match else raw

        # Find JSON object boundaries as a safety net
        start = json_str.find("{")
        end = json_str.rfind("}")
        if start == -1 or end == -1:
            logger.warning("Section extraction response contained no JSON object.")
            return None

        data = json.loads(json_str[start : end + 1])
        sec_a = data.get("section_a", "").strip()
        sec_b = data.get("section_b", "").strip()

        if sec_a in known_sections and sec_b in known_sections:
            logger.debug("Sections extracted: '%s' vs '%s'.", sec_a, sec_b)
            return [sec_a, sec_b]

        logger.warning(
            "Extracted sections not in known list: '%s', '%s'. Falling back.", sec_a, sec_b
        )
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse section extraction JSON: %s.", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Section extraction LLM call failed: %s.", exc)

    return None
