# LLMRouter — all LLM calls in the pipeline go through here.
# Handles routing, fallback, timeout, and token tracking.
# The rest of the pipeline never calls a model API directly.
#
# LLMRouter(state)
#   route(task) -> (primary_model, fallback_model)
#   call(task, prompt, system_prompt=None) -> str
#   _call_deepseek(prompt, system_prompt) -> str
#   _call_gpt(prompt, system_prompt) -> str
#   _handle_fallback(task, prompt, system_prompt) -> str
#
# Routing triggers (applied in order):
#   1. Task complexity — low (classify/extract/compress) -> DeepSeek; high (answer) -> GPT-4o mini
#   2. Budget — if llm_tokens_used_gpt >= llm_budget_gpt -> all calls route to DeepSeek
#   3. Rate limit fallback — HTTP 429 or timeout -> retry on fallback model
#
# Updates state.llm_tokens_used_* and state.llm_calls_by_task after every call.
# Raises LLMUnavailableError if both models fail.
