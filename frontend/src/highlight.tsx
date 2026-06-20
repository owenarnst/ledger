// Minimal Python syntax highlighter, ported from the design's hl().
// Returns an array of React nodes (one <div> per line). Used by both the
// editor overlay and the read-only panes. The real editor can swap this for
// Monaco later (build-plan.md) — the buffer contract is identical.

const KW = new Set([
  'def', 'class', 'return', 'import', 'from', 'for', 'in', 'if', 'else', 'elif', 'and', 'or', 'not',
  'with', 'as', 'lambda', 'yield', 'raise', 'try', 'except', 'finally', 'while', 'pass', 'assert',
  'async', 'await', 'is', 'None', 'True', 'False',
])
const BUILTIN = new Set(['str', 'list', 'dict', 'int', 'float', 'bool', 'set', 'tuple', 'len', 'sorted', 'hashlib'])
const C = { kw: '#b58ac9', str: '#cba36a', num: '#cf9b6a', fn: '#e3c479', builtin: '#83a0c4', self: '#8c8678', com: '#5f5a50' }

export function hl(code: string, dim: boolean): React.ReactNode {
  const base = dim ? '#9a9384' : '#ddd8cd'
  const lines = (code || '').split('\n')
  return lines.map((line: string, li: number) => {
    const spans: React.ReactNode[] = []
    let k = 0
    let codePart = line
    let com = ''
    let q: string | null = null
    let hi = -1
    for (let i = 0; i < line.length; i++) {
      const ch = line[i]
      if (q) {
        if (ch === q) q = null
      } else if (ch === '"' || ch === "'") {
        q = ch
      } else if (ch === '#') {
        hi = i
        break
      }
    }
    if (hi >= 0) {
      codePart = line.slice(0, hi)
      com = line.slice(hi)
    }
    const re = /("[^"]*"|'[^']*'|\b\d+\.?\d*\b|[A-Za-z_][A-Za-z0-9_]*|\s+|[^\sA-Za-z0-9_])/g
    let m: RegExpExecArray | null
    let prev = ''
    while ((m = re.exec(codePart))) {
      const t = m[0]
      let col: string | null = null
      let ital = false
      if (/^["']/.test(t)) col = C.str
      else if (/^\d/.test(t)) col = C.num
      else if (/^[A-Za-z_]/.test(t)) {
        if (KW.has(t)) col = C.kw
        else if (t === 'self') {
          col = C.self
          ital = true
        } else if (prev === 'def' || prev === 'class') col = C.fn
        else if (BUILTIN.has(t)) col = C.builtin
      }
      spans.push(
        <span key={k++} style={col ? { color: col, fontStyle: ital ? 'italic' : 'normal' } : { color: base }}>
          {t}
        </span>,
      )
      if (t.trim()) prev = t
    }
    if (com)
      spans.push(
        <span key={k++} style={{ color: C.com, fontStyle: 'italic' }}>
          {com}
        </span>,
      )
    return (
      <div key={li} style={{ minHeight: '21px', lineHeight: '21px', whiteSpace: 'pre' }}>
        {spans.length ? spans : '​'}
      </div>
    )
  })
}
