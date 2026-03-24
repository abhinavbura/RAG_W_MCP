# _mmr(candidates, k, mmr_lambda) -> list[dict]
# Used only for summary intent.
# Redundancy proxy: section name overlap — no extra embedding calls at query time.
# mmr_lambda from ChunkingConfig: 0.7 (small) -> 0.5 (large).
# Deduplicates by section after MMR.
# Status: DONE
