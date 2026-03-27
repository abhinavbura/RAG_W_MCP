// ProgressMonitor — SSE stream consumer for /ingest/progress.
// Opens EventSource after upload. Displays per-file status rows in real time.
// Shows final summary and calls onDone() when stream ends.
import { useEffect, useRef, useState } from 'react'

const API = 'http://localhost:8000'

const StatusIcon = ({ status }) => {
  if (status === 'ingested') return <span className="status-icon ingested">✓</span>
  if (status === 'skipped')  return <span className="status-icon ingested" style={{ opacity: 0.6 }}>↷</span>
  if (status === 'failed')   return <span className="status-icon failed">✗</span>
  return <span className="status-icon pending">…</span>
}

export default function ProgressMonitor({ runId, onDone }) {
  const [files, setFiles] = useState([])   // [{filename, status, chunks_added, error}]
  const [summary, setSummary] = useState(null)
  const esRef = useRef(null)

  useEffect(() => {
    if (!runId) return

    // Reset state for new run
    setFiles([])
    setSummary(null)

    const es = new EventSource(`${API}/ingest/progress?run_id=${encodeURIComponent(runId)}`)
    esRef.current = es

    es.onmessage = (e) => {
      let data
      try { data = JSON.parse(e.data) } catch { return }

      if (data.type === 'error') {
        setSummary({ error: data.message })
        es.close()
        onDone?.()
        return
      }

      // Final summary event — has total_ingested field
      if ('total_ingested' in data) {
        setSummary(data)
        es.close()
        onDone?.()
        return
      }

      // Per-file progress event
      setFiles(prev => {
        const idx = prev.findIndex(f => f.filename === data.filename)
        if (idx >= 0) {
          const next = [...prev]
          next[idx] = data
          return next
        }
        return [...prev, data]
      })
    }

    es.onerror = () => {
      es.close()
      onDone?.()
    }

    return () => { es.close() }
  }, [runId])

  if (!runId) return null

  return (
    <div className="progress-monitor">
      {files.map((f, i) => (
        <div className="progress-file-row" key={f.filename + i}>
          <StatusIcon status={f.status} />
          <span className="progress-file-name" title={f.filename}>{f.filename}</span>
          {f.chunks_added > 0 && (
            <span className="text-muted text-sm" style={{ flexShrink: 0 }}>
              {f.chunks_added} chunks
            </span>
          )}
          {f.error && (
            <span className="text-muted text-sm" style={{ color: 'var(--error)', flexShrink: 0 }}>
              {f.error}
            </span>
          )}
        </div>
      ))}

      {summary && !summary.error && (
        <div className="progress-summary">
          {summary.total_ingested ?? 0} ingested ·&nbsp;
          {summary.total_skipped ?? 0} skipped ·&nbsp;
          {summary.total_failed ?? 0} failed ·&nbsp;
          {summary.collection_count ?? 0} total chunks
        </div>
      )}

      {summary?.error && (
        <div className="progress-summary" style={{ color: 'var(--error)' }}>
          Error: {summary.error}
        </div>
      )}
    </div>
  )
}
