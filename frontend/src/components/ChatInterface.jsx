// ChatInterface — full chat UI.
// Generates/persists conversation_id in localStorage.
// POST to /query with {query, conversation_id}.
// Renders messages with intent badges + passes chunks to SourceChunksPanel.
import { useEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import SourceChunksPanel from './SourceChunksPanel'

const API = 'http://localhost:8000'

// Simple random ID — no uuid library dependency needed
function genConvId() {
  return 'conv-' + Math.random().toString(36).slice(2, 10)
}

const INTENT_LABELS = {
  fact: 'Fact',
  summary: 'Summary',
  comparison: 'Comparison',
  conversational: 'Conversational',
}

function IntentBadge({ intent }) {
  if (!intent) return null
  return (
    <span className={`intent-badge ${intent}`}>
      {INTENT_LABELS[intent] ?? intent}
    </span>
  )
}

export default function ChatInterface() {
  const [convId] = useState(() => {
    const stored = localStorage.getItem('rag_conv_id')
    if (stored) return stored
    const id = genConvId()
    localStorage.setItem('rag_conv_id', id)
    return id
  })

  const [messages, setMessages] = useState([])
  // messages: [{role: 'user'|'assistant', text, intent?, chunks?}]

  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // chunks shown in the side panel = from the latest assistant message
  const latestChunks = [...messages].reverse().find(m => m.role === 'assistant')?.chunks ?? []

  const listRef = useRef(null)

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages, loading])

  const handleSubmit = async (e) => {
    e?.preventDefault()
    const text = query.trim()
    if (!text || loading) return

    setQuery('')
    setError(null)

    // Optimistically add user bubble
    setMessages(prev => [...prev, { role: 'user', text }])
    setLoading(true)

    try {
      const res = await fetch(`${API}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text, conversation_id: convId }),
      })
      const data = await res.json()

      if (!res.ok) {
        setError(data.detail || 'Query failed')
        return
      }

      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          text: data.answer,
          intent: data.intent,
          chunks: data.chunks ?? [],
        },
      ])
    } catch (err) {
      setError('Network error — is the backend running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleNewConversation = () => {
    const id = genConvId()
    localStorage.setItem('rag_conv_id', id)
    // Reload to pick up new id (simplest; avoids prop-drilling)
    window.location.reload()
  }

  return (
    <div className="chat-page">
      {/* ── Main chat column ─────────────────────────────────────────── */}
      <div className="chat-main">
        {/* Messages */}
        <div className="messages-list" ref={listRef}>
          {messages.length === 0 && (
            <p className="text-muted text-sm" style={{ alignSelf: 'center', marginTop: 40 }}>
              Ask anything about your ingested documents.
            </p>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`message-bubble ${msg.role}`}
            >
              {msg.role === 'assistant' && msg.intent && (
                <div>
                  <IntentBadge intent={msg.intent} />
                </div>
              )}
              <p style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{msg.text}</p>
            </div>
          ))}

          {loading && (
            <div className="message-bubble assistant">
              <span className="spinner" />
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <p className="text-sm" style={{ color: 'var(--error)', paddingBottom: 8 }}>
            {error}
          </p>
        )}

        {/* Input bar */}
        <form className="chat-input-bar" onSubmit={handleSubmit}>
          <textarea
            className="chat-input"
            rows={2}
            placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={loading}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <button
              className="btn btn-primary"
              type="submit"
              disabled={!query.trim() || loading}
              aria-label="Send query"
            >
              <Send size={16} />
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              onClick={handleNewConversation}
              title="Start a new conversation"
              style={{ padding: '6px 10px', fontSize: '0.7rem' }}
            >
              New
            </button>
          </div>
        </form>
      </div>

      {/* ── Source chunks side panel ──────────────────────────────────── */}
      <SourceChunksPanel chunks={latestChunks} />
    </div>
  )
}
