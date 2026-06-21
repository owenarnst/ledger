// Maps backend rows into the display shapes the screens consume. The backend is
// the source of truth (docs/planning/backend-topic-initialization-note.md); the
// frontend never invents topics, providers, or risk semantics — it relabels.

import { Topic } from './api'

// Lifecycle state → ownership-status badge color (theme.badge kind) + faintness.
// The human-readable label itself comes from the backend's derived
// ownership_status; this map only chooses the calm, non-alarm color (#23 / visual
// tone lock — semantic red/green is reserved for test pass/fail).
const STATE_BADGE_KIND: Record<string, { kind: string; faint?: boolean }> = {
  check_recommended: { kind: 'recommended' },
  in_progress: { kind: 'recommended' },
  revisit_suggested: { kind: 'changed' },
  code_changed_since_practice: { kind: 'changed' },
  practiced: { kind: 'practiced', faint: true },
}

// States where an ownership check would be offered, *if* the Topic also carries
// a curated recipe (topic.checkable). Used by the rail's "checks ready" count.
const ACTIONABLE = new Set(['check_recommended', 'code_changed_since_practice', 'in_progress'])

export const isActionable = (state: string): boolean => ACTIONABLE.has(state)

// Ownership-status badge color (theme.badge kind) + faintness for a lifecycle
// state. The label itself is the backend's derived ownership_status.
export function statusBadge(state: string): { kind: string; faint: boolean } {
  const sb = STATE_BADGE_KIND[state] || { kind: 'recommended' }
  return { kind: sb.kind, faint: !!sb.faint }
}

// Risk class is shown verbatim (underscores → hyphens). We do not translate the
// backend's risk taxonomy into friendlier-but-invented labels.
export const riskLabel = (rc: string): string => (rc || '').replace(/_/g, '-')

// Categorical impact label — High / Medium / Low, never a numeric score (#23).
export function impactLabel(level: string): string {
  const v = (level || '').toLowerCase()
  if (v === 'high' || v === 'medium' || v === 'low') return v[0].toUpperCase() + v.slice(1)
  return v ? v[0].toUpperCase() + v.slice(1) : '—'
}

// One verified-worklist row. Exactly four display fields (#23): the durable Topic
// title, the ownership-status badge, the verified evidence summary, and the
// categorical impact level. No signal chips, score, rank rationale, or why-expansion.
export interface Card {
  id: string
  title: string
  badge: string
  badgeLabel: string
  faint: boolean
  evidenceSummary: string
  impact: string
  raw: Topic
}

// Topics arrive in the analyst's order; the row preserves that order verbatim.
export function toCards(topics: Topic[]): Card[] {
  return topics.map((t) => {
    const sb = STATE_BADGE_KIND[t.state] || { kind: 'recommended' }
    return {
      id: t.id,
      title: t.title,
      badge: sb.kind,
      badgeLabel: t.ownership_status || t.state.replace(/_/g, ' '),
      faint: !!sb.faint,
      evidenceSummary: t.evidence_summary || '',
      impact: impactLabel(t.impact_level),
      raw: t,
    }
  })
}

// Human label for a Development-trace's Provider tag. The expanded view is
// provider-neutral in layout (#24); the label only states the actual Provider that
// authored the trace. Falls back to a title-cased form, never to a fake "Claude".
const TRACE_PROVIDER: Record<string, string> = {
  claude_code: 'Claude Code',
}

export function providerLabel(provider?: string | null): string {
  if (!provider) return 'Session'
  return TRACE_PROVIDER[provider] || provider.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

// Derive the read-only companion test path from a check's editable target.
// retrieval/rerank.py -> tests/test_rerank.py
export function testPathFor(targetFile: string): string | null {
  if (!targetFile) return null
  const base = targetFile.split('/').pop()
  return `tests/test_${base}`
}
