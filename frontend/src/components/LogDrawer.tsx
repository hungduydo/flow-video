import { useEffect, useRef, useState } from 'react'
import { streamLogs } from '../api/jobs'
import { useJobStore } from '../stores/jobStore'

export function LogDrawer() {
  const { activeJobId, isLogOpen, closeLog } = useJobStore()
  const [lines, setLines] = useState<string[]>([])
  const [done, setDone] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!activeJobId) return
    setLines([])
    setDone(false)
    const cleanup = streamLogs(
      activeJobId,
      (line) => setLines(prev => [...prev, line]),
      (status) => {
        setLines(prev => [...prev, `✓ Job ${status.toUpperCase()}`])
        setDone(true)
      },
    )
    return cleanup
  }, [activeJobId])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [lines])

  if (!isLogOpen) return null

  return (
    <div style={{
      position: 'absolute', bottom: 0, left: 0, right: 0,
      height: 248, background: '#08080b',
      borderTop: '1px solid #1a1a1f',
      display: 'flex', flexDirection: 'column', zIndex: 30,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 16px', borderBottom: '1px solid #111116', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {!done && activeJobId && (
            <span style={{
              width: 6, height: 6, borderRadius: '50%', background: '#10b981',
              display: 'inline-block', animation: 'pulseDot 1.2s infinite',
            }} />
          )}
          <span style={{ fontSize: 11, color: '#3a3a44', fontFamily: "'DM Mono', monospace", letterSpacing: '0.03em' }}>
            output
          </span>
          {activeJobId && (
            <span style={{ fontSize: 11, color: '#252530', fontFamily: "'DM Mono', monospace" }}>
              {activeJobId.slice(0, 8)}…
            </span>
          )}
        </div>
        <button
          onClick={closeLog}
          style={{ background: 'none', border: 'none', color: '#333340', cursor: 'pointer', fontSize: 18, lineHeight: 1, padding: '2px 4px' }}
        >
          ×
        </button>
      </div>

      {/* Log body */}
      <div
        ref={scrollRef}
        style={{
          flex: 1, overflowY: 'auto', padding: '10px 16px',
          fontFamily: "'DM Mono', monospace", fontSize: 11.5,
          color: '#666678', lineHeight: 2,
        }}
      >
        {lines.length === 0 ? (
          <span style={{ color: '#252530' }}>waiting for output…</span>
        ) : (
          lines.map((line, i) => (
            <div
              key={i}
              style={{
                color: line.startsWith('✓') ? '#10b981'
                     : line.includes('→')   ? '#4f83ff'
                     : '#666678',
              }}
            >
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
