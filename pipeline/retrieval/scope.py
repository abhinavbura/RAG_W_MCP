# _detect_scope(query, state) -> str | None
# Tokenise each source_doc stem from state.files_metadata.
# Match tokens against query words.
# Confident match -> return source_doc path string.
# No match -> return None (search whole collection).
# Status: PLANNED
