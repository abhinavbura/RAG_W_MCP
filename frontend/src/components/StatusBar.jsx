import { useState, useEffect } from 'react';
import { Terminal, AlertCircle } from 'lucide-react';

export default function StatusBar() {
  const [log, setLog] = useState({ message: 'System ready', level: 'INFO', name: 'system' });

  useEffect(() => {
    const eventSource = new EventSource('http://localhost:8000/logs/stream');

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLog(data);
      } catch (e) {
        console.error("Failed to parse log data", e);
      }
    };

    eventSource.onerror = () => {
      setLog({ message: 'Disconnected from server logging stream.', level: 'WARNING', name: 'sse' });
    };

    return () => eventSource.close();
  }, []);

  const isError = log.level === 'ERROR' || log.level === 'WARNING' || log.level === 'CRITICAL';

  return (
    <div className={`status-bar ${isError ? 'error' : ''}`}>
      <div className="status-content">
        {isError ? <AlertCircle size={14} /> : <Terminal size={14} />}
        <span className="status-name">[{log.name}]</span>
        <span className="status-msg">{log.message}</span>
      </div>
    </div>
  );
}
