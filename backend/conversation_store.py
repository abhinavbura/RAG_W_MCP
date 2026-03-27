"""
Conversation history store — one ConversationHistory per conversation_id.
Keyed in memory. Cleared by calling clear().
"""
from typing import Dict
from pipeline.state.conversation import ConversationHistory


_store: Dict[str, ConversationHistory] = {}


def get_or_create(conversation_id: str) -> ConversationHistory:
    """Return existing history or create a fresh one."""
    if conversation_id not in _store:
        _store[conversation_id] = ConversationHistory()
    return _store[conversation_id]


def clear(conversation_id: str) -> None:
    """Remove a conversation from the store."""
    _store.pop(conversation_id, None)


def all_ids() -> list:
    """Return all active conversation IDs."""
    return list(_store.keys())
