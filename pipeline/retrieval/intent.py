# _classify_intent(query) -> "fact" | "summary" | "comparison" | "conversational"
# Regex primary — handles 90%+ of cases, keeps hot path LLM-free.
# LLM fallback (DeepSeek) for genuinely ambiguous queries only.
# Status: DONE
