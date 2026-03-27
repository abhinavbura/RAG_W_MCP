import { useState } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import { Upload, MessageSquare, Brain } from 'lucide-react'
import StateBadge from './components/StateBadge'
import UploadZone from './components/UploadZone'
import ProgressMonitor from './components/ProgressMonitor'
import ChatInterface from './components/ChatInterface'

function UploadPage() {
  const [runId, setRunId] = useState(null)
  const [done, setDone] = useState(false)

  const handleUploadStart = (id) => {
    setDone(false)
    setRunId(id)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1, overflow: 'auto' }}>
      <UploadZone onUploadStart={handleUploadStart} />
      {runId && (
        <div style={{ width: '100%', maxWidth: 560, padding: '0 32px 32px' }}>
          <ProgressMonitor runId={runId} onDone={() => setDone(true)} />
          {done && (
            <p className="text-sm text-muted" style={{ marginTop: 12, textAlign: 'center' }}>
              Ingestion complete — head to Chat to query your documents.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export default function App() {
  return (
    <div className="app-shell">
      {/* ── Top bar ── */}
      <header className="topbar">
        <div className="topbar-brand">
          <div className="brand-icon">
            <Brain size={18} color="#fff" />
          </div>
          RAG Pipeline
        </div>

        <nav className="topbar-nav">
          <NavLink
            to="/"
            end
            className={({ isActive }) => `nav-btn${isActive ? ' active' : ''}`}
          >
            <Upload size={15} />
            Upload
          </NavLink>
          <NavLink
            to="/chat"
            className={({ isActive }) => `nav-btn${isActive ? ' active' : ''}`}
          >
            <MessageSquare size={15} />
            Chat
          </NavLink>
        </nav>

        <StateBadge />
      </header>

      {/* ── Page content ── */}
      <main className="main-content">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/chat" element={<ChatInterface />} />
        </Routes>
      </main>
    </div>
  )
}
