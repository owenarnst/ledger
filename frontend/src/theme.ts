// Style helpers ported from the design's renderVals() badge/chip builders.
// CSS-string builders in the design become style objects here.

export const mono = "'JetBrains Mono', monospace"

export type BadgeKind = 'recommended' | 'changed' | 'practiced' | string

export function badge(kind: BadgeKind): React.CSSProperties {
  const base: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '3px 10px',
    borderRadius: 7,
    fontSize: 11.5,
    fontWeight: 500,
    fontFamily: "'Geist', sans-serif",
    whiteSpace: 'nowrap',
  }
  if (kind === 'recommended')
    return { ...base, background: 'rgba(200,116,77,0.12)', color: '#d6a07e', border: '1px solid rgba(200,116,77,0.24)' }
  if (kind === 'changed')
    return { ...base, background: 'rgba(133,160,196,0.13)', color: '#a6bcdb', border: '1px solid rgba(133,160,196,0.26)' }
  if (kind === 'practiced')
    return { ...base, background: 'rgba(154,147,132,0.10)', color: '#9a9384', border: '1px solid var(--bd2)' }
  return base
}

const monoChip: React.CSSProperties = {
  whiteSpace: 'nowrap',
  fontFamily: mono,
  fontSize: 11,
  padding: '3px 9px',
  borderRadius: 6,
}

export const chipPlain: React.CSSProperties = { ...monoChip, color: '#9a9384', background: '#201e18', border: '1px solid var(--bd)' }
export const chipRisk: React.CSSProperties = { ...monoChip, color: '#9a9384', background: '#201e18', border: '1px solid var(--bd2)' }
export const chipClaude: React.CSSProperties = {
  ...monoChip,
  color: '#d6a07e',
  background: 'rgba(200,116,77,0.10)',
  border: '1px solid rgba(200,116,77,0.22)',
}
export const toolChip: React.CSSProperties = {
  whiteSpace: 'nowrap',
  color: '#cdcabf',
  background: '#201e18',
  border: '1px solid var(--bd2)',
  padding: '3px 8px',
  borderRadius: 5,
}

// Categorical impact pill (#23/#24). Calm and neutral — emphasis varies only by
// text weight/brightness across High → Low; semantic red/green stays reserved for
// test pass/fail (visual tone lock). Never a numeric score.
export function impactChip(level: string): React.CSSProperties {
  const base: React.CSSProperties = {
    whiteSpace: 'nowrap',
    fontFamily: "'Geist', sans-serif",
    fontSize: 11.5,
    fontWeight: 500,
    padding: '3px 10px',
    borderRadius: 7,
    border: '1px solid var(--bd2)',
    background: 'var(--panel2)',
  }
  const v = (level || '').toLowerCase()
  if (v === 'high') return { ...base, color: 'var(--tx)' }
  if (v === 'medium') return { ...base, color: 'var(--mut)' }
  return { ...base, color: 'var(--faint)' }
}

export type ChipKind = 'claude' | 'risk' | 'plain'

export function chipForKind(k: ChipKind): React.CSSProperties {
  if (k === 'claude') return chipClaude
  if (k === 'risk') return chipRisk
  return chipPlain
}
