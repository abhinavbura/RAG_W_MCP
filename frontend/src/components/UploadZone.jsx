// UploadZone — drag/drop + click-to-browse file upload.
// Accepts .md, .txt, .pdf only.
// POST to /ingest as multipart/form-data.
// Calls onUploadStart(run_id) with the run_id from the server response.
import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'

const API = 'http://localhost:8000'
const ALLOWED = ['.md', '.txt', '.pdf']

function isAllowed(filename) {
  const ext = filename.slice(filename.lastIndexOf('.')).toLowerCase()
  return ALLOWED.includes(ext)
}

export default function UploadZone({ onUploadStart }) {
  const [dragging, setDragging] = useState(false)
  const [pending, setPending] = useState([])   // File objects staged for upload
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  // ── drag events ──────────────────────────────────────────────────────────
  const onDragOver = (e) => { e.preventDefault(); setDragging(true) }
  const onDragLeave = () => setDragging(false)

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const files = Array.from(e.dataTransfer.files)
    addFiles(files)
  }

  const onInputChange = (e) => {
    addFiles(Array.from(e.target.files))
    e.target.value = ''   // reset so same file can be re-selected
  }

  const addFiles = (files) => {
    setError(null)
    const valid = files.filter(f => isAllowed(f.name))
    const invalid = files.filter(f => !isAllowed(f.name))
    if (invalid.length) {
      setError(`Rejected: ${invalid.map(f => f.name).join(', ')} — only .md, .txt, .pdf allowed`)
    }
    if (valid.length) {
      setPending(prev => {
        // Deduplicate by name
        const existing = new Set(prev.map(f => f.name))
        return [...prev, ...valid.filter(f => !existing.has(f.name))]
      })
    }
  }

  const removeFile = (name) =>
    setPending(prev => prev.filter(f => f.name !== name))

  // ── upload ───────────────────────────────────────────────────────────────
  const handleUpload = async () => {
    if (!pending.length || loading) return
    setLoading(true)
    setError(null)

    const form = new FormData()
    pending.forEach(f => form.append('files', f))

    try {
      const res = await fetch(`${API}/ingest`, { method: 'POST', body: form })
      const data = await res.json()

      if (!res.ok) {
        setError(data.detail || 'Upload failed')
        return
      }

      setPending([])
      onUploadStart?.(data.run_id)
    } catch (err) {
      setError('Network error — is the backend running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="upload-page">
      {/* Drop zone */}
      <div
        className={`dropzone${dragging ? ' active' : ''}`}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => !loading && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && inputRef.current?.click()}
        aria-label="File upload drop zone"
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".md,.txt,.pdf"
          style={{ display: 'none' }}
          onChange={onInputChange}
        />
        <div className="dropzone-icon">
          <Upload size={24} />
        </div>
        <h2>Drop files here</h2>
        <p>or click to browse — .md · .txt · .pdf</p>
      </div>

      {/* File list */}
      {pending.length > 0 && (
        <div className="progress-monitor" style={{ marginTop: 0 }}>
          {pending.map(f => (
            <div className="progress-file-row" key={f.name}>
              <span className="status-icon pending">○</span>
              <span className="progress-file-name" title={f.name}>{f.name}</span>
              <button
                className="btn btn-ghost"
                style={{ padding: '2px 8px', fontSize: '0.75rem' }}
                onClick={e => { e.stopPropagation(); removeFile(f.name) }}
              >
                ×
              </button>
            </div>
          ))}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '12px' }}>
            <button
              className="btn btn-primary"
              onClick={handleUpload}
              disabled={loading}
            >
              {loading
                ? <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Uploading…</>
                : `Upload ${pending.length} file${pending.length !== 1 ? 's' : ''}`}
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-sm" style={{ color: 'var(--error)', maxWidth: 560 }}>
          {error}
        </p>
      )}
    </div>
  )
}
