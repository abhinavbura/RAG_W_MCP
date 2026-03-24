# In-memory ConversationHistory store, keyed by conversation_id.
# Dict[str, ConversationHistory]
# Lives in FastAPI process memory — swap to Redis for multi-user deployment.

from pipeline.state.conversation import ConversationHistory

_store: dict[str, ConversationHistory] = {}


def get_or_create(conversation_id: str) -> ConversationHistory:
    if conversation_id not in _store:
        _store[conversation_id] = ConversationHistory()
    return _store[conversation_id]


def get(conversation_id: str) -> ConversationHistory | None:
    return _store.get(conversation_id)
