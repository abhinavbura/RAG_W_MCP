// ProgressMonitor — SSE stream consumer
// Connects to GET /ingest/progress after upload.
// Displays per-file status in real time: filename, status icon, chunk count.
// Shows final summary: "X ingested, Y skipped, Z failed".
// Calls onDone() when final summary event received.
export default function ProgressMonitor({ onDone }) {
  return null // TODO: implement
}
