"""
Intent classification for the retrieval pipeline.

Primary path: regex — handles ~90% of queries with zero LLM latency.
Fallback: DeepSeek via LLMRouter — only triggered when regex matches
          zero or multiple intent categories simultaneously.

Returns one of: "fact" | "summary" | "comparison" | "conversational"
Never raises — defaults to "fact" if classification is impossible.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled patterns — order matters for priority when no LLM is available.
# Each pattern is anchored to whole words (\b) to avoid false partial matches.
# ---------------------------------------------------------------------------

# Comparison must be tested BEFORE fact — "what is the difference" would
# naively match both fact (what) and comparison (difference).
_COMPARISON = re.compile(
    r"\b(compare|compar|comparison|difference|differ|vs\.?|versus|contrast|"
    r"better than|worse than|between .+ and)\b",
    re.IGNORECASE,
)

# Summary: explicit summarisation verbs plus "what is / are" as overview triggers.
_SUMMARY = re.compile(
    r"\b(summari[sz]e?|summarise|overview|give.{0,10}overview|explain|"
    r"describe|tell me about|what (is|are|does)|how does)\b",
    re.IGNORECASE,
)

# Fact: specific question words that expect a concrete, single-answer response.
# Intentionally excluded: "what is" (→ summary), "what does" (→ summary).
_FACT = re.compile(
    r"\b(who|which|when|where|how (much|many|long|often|far)|"
    r"list|name|identify|give me the|what (are the|is the name|is the date))\b",
    re.IGNORECASE,
)

# Conversational: pronoun-heavy follow-up queries that reference a prior turn.
_CONVERSATIONAL = re.compile(
    r"\b(you|your|that|this|it|they|them|those|these|he|she|"
    r"previously|earlier|the (above|previous|last)|as mentioned)\b",
    re.IGNORECASE,
)

_VALID_INTENTS = {"fact", "summary", "comparison", "conversational"}

_PRIORITY_ORDER = ["comparison", "summary", "fact", "conversational"]


def _classify_intent(query: str, llm_router=None) -> str:
    """
    Classify query intent.

    Args:
        query:      Raw query string.
        llm_router: LLMRouter instance. If provided, used as fallback when
                    regex is ambiguous. Passing None skips LLM entirely.

    Returns:
        One of: "fact" | "summary" | "comparison" | "conversational".
    """
    matched: dict[str, bool] = {}

    if _COMPARISON.search(query):
        matched["comparison"] = True
    if _SUMMARY.search(query):
        matched["summary"] = True
    if _FACT.search(query):
        matched["fact"] = True
    if _CONVERSATIONAL.search(query):
        matched["conversational"] = True

    # Unambiguous — exactly one pattern matched
    if len(matched) == 1:
        intent = next(iter(matched))
        logger.debug("Intent '%s' resolved by regex (unambiguous).", intent)
        return intent

    # Multiple patterns matched — try LLM fallback
    if llm_router and len(matched) > 1:
        logger.debug(
            "Ambiguous intent (%s) — delegating to LLM.", list(matched.keys())
        )
        try:
            system_prompt = (
                "You classify query intent. "
                "Return exactly one word from: fact, summary, comparison, conversational. "
                "No explanation, no punctuation — just the single word."
            )
            result = llm_router.call("classify", query, system_prompt).strip().lower()
            if result in _VALID_INTENTS:
                logger.debug("LLM classified intent as '%s'.", result)
                return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM intent classification failed: %s. Using priority fallback.", exc)

    # Priority fallback — prefer comparison > summary > fact > conversational
    for intent in _PRIORITY_ORDER:
        if intent in matched:
            logger.debug("Intent '%s' resolved by priority fallback.", intent)
            return intent

    # Nothing matched at all — default to fact
    logger.debug("No intent matched for query — defaulting to 'fact'.")
    return "fact"
