"""
Custom exception types for the LLM layer.
"""


class LLMUnavailableError(Exception):
    """
    Raised when both the primary and fallback LLM models fail.

    Callers should catch this specifically and surface it as a 503 to the API layer
    rather than letting it propagate as an unhandled exception.
    """
    pass
