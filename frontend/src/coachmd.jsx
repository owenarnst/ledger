// The real coach (claude -p) returns markdown prose. This renders it in the
// design's voice: `## Heading` → the small mono section label, blank-line
// paragraphs, inline **bold** and `code`. It asserts no structure the coach
// didn't produce — unrecognized text just renders as paragraphs.
import React from 'react'

const mono = "'JetBrains Mono', monospace"

const LABEL_COLOR = {
  'diagnostic question': 'var(--cool)',
  'suggested observation': 'var(--mut)',
}

function inline(text) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.map((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p))
      return (
        <strong key={i} style={{ color: 'var(--tx)', fontWeight: 600 }}>
          {p.slice(2, -2)}
        </strong>
      )
    if (/^`[^`]+`$/.test(p))
      return (
        <span key={i} style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--accent)' }}>
          {p.slice(1, -1)}
        </span>
      )
    return p
  })
}

export function renderCoach(text) {
  const blocks = []
  let buf = []
  const flush = () => {
    if (buf.length) {
      blocks.push({ type: 'p', text: buf.join(' ').trim() })
      buf = []
    }
  }
  for (const line of (text || '').split('\n')) {
    const heading = line.match(/^#{1,6}\s+(.*)$/)
    if (heading) {
      flush()
      blocks.push({ type: 'h', text: heading[1].trim() })
    } else if (line.trim() === '') {
      flush()
    } else {
      buf.push(line.trim())
    }
  }
  flush()

  return blocks.map((b, i) => {
    if (b.type === 'h') {
      const color = LABEL_COLOR[b.text.toLowerCase()] || 'var(--accent)'
      return (
        <div
          key={i}
          style={{
            fontFamily: mono,
            fontSize: 10,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            color,
            margin: i === 0 ? '0 0 6px' : '13px 0 6px',
          }}
        >
          {b.text}
        </div>
      )
    }
    return (
      <div key={i} style={{ fontSize: 13, color: 'var(--tx)', lineHeight: 1.55, marginBottom: 6 }}>
        {inline(b.text)}
      </div>
    )
  })
}
