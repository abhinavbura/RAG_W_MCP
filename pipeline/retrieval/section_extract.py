# _extract_sections_llm(query, known_sections) -> dict | None
# Called only for comparison intent.
# DeepSeek call: system prompt enforces JSON {section_a, section_b}.
# Both values must exist in known_sections list.
# If JSON parse fails or sections not in list -> return None (fallback: no filter).
# Status: PLANNED
