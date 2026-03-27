// StateBadge — polls GET /state on mount and every 30s.
// Shows: green dot + chunk count + model key.
// Shows orange dot + warning text if model_upgrade_warning is set.
import { useEffect, useState } from 'react'

const API = 'http://localhost:8000'

export default function StateBadge() {
  const [info, setInfo] = useState(null)

  const fetchState = () => {
    fetch(`${API}/state`)
      .then(r => r.json())
      .then(d => setInfo(d))
      .catch(() => {})
  }

  useEffect(() => {
    fetchState()
    const id = setInterval(fetchState, 30_000)
    return () => clearInterval(id)
  }, [])

  if (!info) return null

  const hasWarning = !!info.model_upgrade_warning

  return (
    <div className={`state-badge${hasWarning ? ' warning' : ''}`}>
      <span className="dot" />
      {hasWarning
        ? info.model_upgrade_warning
        : `${info.collection_count ?? 0} chunks · ${info.model_key || '—'}`}
    </div>
  )
}
