import React, { useState } from 'react'
import UploadZone from './components/UploadZone'
import ProgressMonitor from './components/ProgressMonitor'
import ChatInterface from './components/ChatInterface'
import StateBadge from './components/StateBadge'
import './index.css'

export default function App() {
  const [ingesting, setIngesting] = useState(false)
  const [conversationId] = useState(() => crypto.randomUUID())

  return (
    <div className="app">
      <header>
        <h1>RAG Pipeline</h1>
        <StateBadge />
      </header>
      <main>
        <section className="upload-section">
          <UploadZone onUploadStart={() => setIngesting(true)} />
          {ingesting && <ProgressMonitor onDone={() => setIngesting(false)} />}
        </section>
        <section className="chat-section">
          <ChatInterface conversationId={conversationId} />
        </section>
      </main>
    </div>
  )
}
