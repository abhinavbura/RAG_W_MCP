// SourceChunksPanel — shows retrieved chunks alongside the answer.
// Per chunk: anchor path, source_doc filename, text snippet (first 200 chars).

export default function SourceChunksPanel({ chunks }) {
  if (!chunks || chunks.length === 0) {
    return (
      <aside className="chunks-panel">
        <p className="chunks-panel-header">Sources</p>
        <p className="text-muted text-sm" style={{ padding: '8px 4px' }}>
          No sources yet.
        </p>
      </aside>
    )
  }

  return (
    <aside className="chunks-panel">
      <p className="chunks-panel-header">Sources ({chunks.length})</p>

      {chunks.map((chunk, i) => {
        const anchor = chunk.anchor || chunk.section || '—'
        const sourceDoc = chunk.source_doc || ''
        // Show just the filename, not the full relative path
        const filename = sourceDoc.split('/').pop() || sourceDoc
        const snippet = (chunk.text || '').slice(0, 200)

        return (
          <div className="chunk-card" key={chunk.id || i}>
            <div className="chunk-anchor" title={anchor}>{anchor}</div>
            <div className="chunk-source">📄 {filename}</div>
            <div className="chunk-text">
              {snippet}{chunk.text && chunk.text.length > 200 ? '…' : ''}
            </div>
          </div>
        )
      })}
    </aside>
  )
}
