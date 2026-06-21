// Maps backend rows into the display shapes the screens consume. The backend is
// the source of truth (docs/planning/backend-topic-initialization-note.md); the
// frontend never invents topics, providers, or risk semantics — it relabels.

import { Topic, TopicDetail } from './api'

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

const RECEIPT_PROVIDER: Record<string, { label: string; chip: string }> = {
  claude_code: { label: '✳ Claude', chip: 'claude' },
  codex: { label: '⬡ Codex', chip: 'codex' },
}

export interface Receipt {
  code: any
  receipt: any
  trail: any
  // True only when a real conversation receipt grounds this Topic. Extracted
  // topics carry code + trail evidence but no session link, so the UI must not
  // imply an authoring receipt it doesn't have.
  hasReceipt: boolean
  provider: string
  providerLabel: string
  providerChipKind: string
  toolSequence: string[]
  sourcePath: string | null
  sessionId: string | null
  linkConfidence: string | null
  codePath: string
  invariant: string
}

// Pull the authoring-receipt view out of a topic detail's evidence list.
export function deriveReceipt(detail: TopicDetail): Receipt {
  const ev = detail.evidence || []
  const code = ev.find((e) => e.kind === 'code') || null
  const receipt = ev.find((e) => /_receipt$/.test(e.kind)) || null
  const trail = ev.find((e) => e.kind === 'missing_reasoning') || null
  const provider = receipt?.provider || detail.provider || 'claude_code'
  const pm = RECEIPT_PROVIDER[provider] || { label: provider, chip: 'plain' }
  return {
    code,
    receipt,
    trail,
    hasReceipt: !!receipt,
    provider,
    providerLabel: pm.label,
    providerChipKind: pm.chip,
    toolSequence: receipt?.tool_sequence || [],
    sourcePath: receipt?.source_path || null,
    sessionId: receipt?.session_id || null,
    linkConfidence: receipt?.link_confidence || null,
    codePath: detail.current_revision?.code_path || code?.title || '',
    invariant: detail.current_revision?.invariant || '',
  }
}

// Derive the read-only companion test path from a check's editable target.
// retrieval/rerank.py -> tests/test_rerank.py
export function testPathFor(targetFile: string): string | null {
  if (!targetFile) return null
  const base = targetFile.split('/').pop()
  return `tests/test_${base}`
}
