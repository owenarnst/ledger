// Style helpers ported from the design's renderVals() badge/chip builders.
// CSS-string builders in the design become style objects here.

export const mono = "'JetBrains Mono', monospace"

export function badge(kind) {
  const base = {
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

const monoChip = {
  whiteSpace: 'nowrap',
  fontFamily: mono,
  fontSize: 11,
  padding: '3px 9px',
  borderRadius: 6,
}

export const chipPlain = { ...monoChip, color: '#9a9384', background: '#201e18', border: '1px solid var(--bd)' }
export const chipRisk = { ...monoChip, color: '#9a9384', background: '#201e18', border: '1px solid var(--bd2)' }
export const chipClaude = {
  ...monoChip,
  color: '#d6a07e',
  background: 'rgba(200,116,77,0.10)',
  border: '1px solid rgba(200,116,77,0.22)',
}
export const chipCodex = {
  ...monoChip,
  color: '#a6bcdb',
  background: 'rgba(133,160,196,0.10)',
  border: '1px solid rgba(133,160,196,0.24)',
}
export const toolChip = {
  whiteSpace: 'nowrap',
  color: '#cdcabf',
  background: '#201e18',
  border: '1px solid var(--bd2)',
  padding: '3px 8px',
  borderRadius: 5,
}

export function chipForKind(k) {
  if (k === 'claude') return chipClaude
  if (k === 'codex') return chipCodex
  if (k === 'risk') return chipRisk
  return chipPlain
}
