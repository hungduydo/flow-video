import { useEffect, useRef, useState } from 'react'
import { streamLogs } from '../api/jobs'
import { useJobStore } from '../stores/jobStore'

export function LogDrawer() {
  const { activeJobId, isLogOpen, closeLog } = useJobStore()
  const [lines, setLines] = useState<string[]>([])
  const [done, setDone] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!activeJobId) return
    setLines([])
    setDone(false)
    const cleanup = streamLogs(
      activeJobId,
      (line) => setLines((prev) => [...prev, line]),
      (status) => {
        setLines((prev) => [...prev, `\n✅ Job ${status.toUpperCase()}`])
        setDone(true)
      }
    )
    return cleanup
  }, [activeJobId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  if (!isLogOpen) return null

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 0, left: 0, right: 0,
        height: 320,
        background: '#0d1117',
        borderTop: '1px solid #1e2433',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 50,
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800">
        <div className="flex items-center gap-2">
          {!done && (
            <span className="inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          )}
          <span className="text-sm font-mono text-slate-400">
            {activeJobId ? `Job ${activeJobId.slice(0, 8)}…` : 'Logs'}
          </span>
        </div>
        <button onClick={closeLog} className="text-slate-500 hover:text-slate-300 text-sm">
          ✕ Close
        </button>
      </div>

      {/* Log body */}
      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs text-slate-300 leading-relaxed">
        {lines.length === 0 ? (
          <span className="text-slate-600">Waiting for output…</span>
        ) : (
          lines.map((line, i) => (
            <div key={i} className={line.startsWith('\n') ? 'mt-2 text-green-400 font-bold' : ''}>
              {line}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
