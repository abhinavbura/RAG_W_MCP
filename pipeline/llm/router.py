"""
LLMRouter — all LLM calls in the pipeline go through here.

Routing triggers (applied in order):
  1. Task complexity: low tasks (classify/extract/compress) → DeepSeek primary.
     High tasks (answer) → GPT-4o mini primary.
  2. Budget: if llm_tokens_used_gpt >= llm_budget_gpt, all calls route to DeepSeek
     for the rest of the session regardless of task type.
  3. Rate-limit / timeout fallback: if primary returns 429 or times out,
     silently retry on fallback. If both fail, raise LLMUnavailableError.

Updates state.llm_tokens_used_* and state.llm_calls_by_task after every call.
"""
import logging
import os
from typing import Optional, Tuple

import openai
from dotenv import load_dotenv

load_dotenv()

from .errors import LLMUnavailableError

logger = logging.getLogger(__name__)

# Task complexity classification
_LOW_COMPLEXITY_TASKS = {"classify", "extract", "compress"}

# Model identifiers
_GPT_MODEL = "openai/gpt-4o-mini"
_DEEPSEEK_MODEL = "deepseek/deepseek-r1"


class LLMRouter:
    """
    Routes every LLM call to the correct model and handles fallback transparently.
    Instantiated once per retrieve() call — state is passed in at construction.
    """

    def __init__(self, state) -> None:
        self.state = state

        self._client = openai.OpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            base_url="https://openrouter.ai/api/v1",
        )

    # ------------------------------------------------------------------ public

    def route(self, task: str) -> Tuple[str, str]:
        """Return (primary, fallback) model keys for the given task."""
        if task in _LOW_COMPLEXITY_TASKS:
            return "deepseek", "gpt"
        return "gpt", "deepseek"

    def call(
        self,
        task: str,
        user_prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Execute an LLM call for *task*.

        Applies budget check, then tries primary → fallback.
        Never raises unless both models fail.

        Args:
            task:          Task key — drives routing. One of:
                           classify | extract | compress | answer
            user_prompt:   The user-facing message.
            system_prompt: Optional system instruction.

        Returns:
            Model response text.

        Raises:
            LLMUnavailableError: If both primary and fallback models fail.
        """
        primary, fallback = self.route(task)

        # Budget override: if GPT budget exhausted, always use DeepSeek
        if self.state.llm_tokens_used_gpt >= self.state.llm_budget_gpt:
            logger.info("GPT budget exhausted — routing '%s' to DeepSeek.", task)
            primary, fallback = "deepseek", "gpt"

        # Try primary
        try:
            return self._dispatch(primary, task, user_prompt, system_prompt)
        except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as primary_err:
            logger.warning(
                "Primary model '%s' failed for task '%s' (%s). Retrying on fallback '%s'.",
                primary, task, primary_err, fallback,
            )
        except openai.APIError as primary_err:
            # Treat 5xx as transient — retry on fallback
            if hasattr(primary_err, "status_code") and primary_err.status_code >= 500:
                logger.warning(
                    "Primary model '%s' returned %s for task '%s'. Retrying on fallback.",
                    primary, primary_err.status_code, task,
                )
            else:
                raise LLMUnavailableError(str(primary_err)) from primary_err

        # Try fallback
        try:
            result = self._dispatch(fallback, task, user_prompt, system_prompt)
            logger.info("Fallback model '%s' succeeded for task '%s'.", fallback, task)
            return result
        except Exception as fallback_err:
            raise LLMUnavailableError(
                f"Both '{primary}' and '{fallback}' failed for task '{task}'. "
                f"Fallback error: {fallback_err}"
            ) from fallback_err

    # ----------------------------------------------------------------- private

    def _dispatch(
        self,
        model_key: str,
        task: str,
        user_prompt: str,
        system_prompt: Optional[str],
    ) -> str:
        if model_key == "deepseek":
            return self._call_deepseek(task, user_prompt, system_prompt)
        return self._call_gpt(task, user_prompt, system_prompt)

    def _build_messages(
        self, user_prompt: str, system_prompt: Optional[str]
    ) -> list:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _record(self, model_key: str, task: str, tokens: int) -> None:
        if model_key == "deepseek":
            self.state.llm_tokens_used_deepseek += tokens
        else:
            self.state.llm_tokens_used_gpt += tokens
        self.state.llm_calls_by_task[task] = (
            self.state.llm_calls_by_task.get(task, 0) + 1
        )

    def _call_deepseek(
        self, task: str, user_prompt: str, system_prompt: Optional[str]
    ) -> str:
        response = self._client.chat.completions.create(
            model=_DEEPSEEK_MODEL,
            messages=self._build_messages(user_prompt, system_prompt),
            timeout=30,
        )
        tokens = response.usage.total_tokens if response.usage else 0
        self._record("deepseek", task, tokens)
        logger.debug("DeepSeek used %d tokens for task '%s'.", tokens, task)
        return response.choices[0].message.content or ""

    def _call_gpt(
        self, task: str, user_prompt: str, system_prompt: Optional[str]
    ) -> str:
        response = self._client.chat.completions.create(
            model=_GPT_MODEL,
            messages=self._build_messages(user_prompt, system_prompt),
            timeout=30,
        )
        tokens = response.usage.total_tokens if response.usage else 0
        self._record("gpt", task, tokens)
        logger.debug("GPT used %d tokens for task '%s'.", tokens, task)
        return response.choices[0].message.content or ""
