# LLMUnavailableError — raised when both primary and fallback models fail.
# Typed error so callers can handle it specifically.


class LLMUnavailableError(Exception):
    """Raised when both primary and fallback LLM models are unavailable."""
    pass
