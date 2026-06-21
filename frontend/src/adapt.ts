// Maps backend rows into the display shapes the screens consume. The backend is
// the source of truth (docs/planning/backend-topic-initialization-note.md); the
// frontend never invents topics, providers, or risk semantics — it relabels.

import { Topic, TopicDetail } from './api'
import { ChipKind } from './theme'

const STATE_BADGE: Record<string, { badge: string; badgeLabel: string; faint?: boolean }> = {
  check_recommended: { badge: 'recommended', badgeLabel: 'Check recommended' },
  code_changed_since_practice: { badge: 'changed', badgeLabel: 'Code changed since practice' },
  practiced: { badge: 'practiced', badgeLabel: 'Practiced', faint: true },
  in_progress: { badge: 'recommended', badgeLabel: 'In progress' },
}

// States where an ownership check would be offered, *if* the Topic also carries
// a curated recipe (topic.checkable). The first topic that is both actionable
// and checkable becomes the demo hero — the one the backend can sandbox.
const ACTIONABLE = new Set(['check_recommended', 'code_changed_since_practice', 'in_progress'])

export const isActionable = (state: string): boolean => ACTIONABLE.has(state)

// Risk class is shown verbatim (underscores → hyphens). We do not translate the
// backend's risk taxonomy into friendlier-but-invented labels.
export const riskLabel = (rc: string): string => (rc || '').replace(/_/g, '-')

export interface Chip {
  label: string
  k: ChipKind
}

export function providerChip(topic: Topic): Chip | null {
  if (topic.claude_authored) return { label: '✳ Claude-authored', k: 'claude' }
  if (topic.provider === 'codex') return { label: '⬡ Codex-authored', k: 'codex' }
  return null
}

export function badgeForState(state: string) {
  return STATE_BADGE[state] || { badge: 'recommended', badgeLabel: state }
}

export interface Card {
  id: string
  title: string
  badge: string
  badgeLabel: string
  faint: boolean
  isHero: boolean
  expanded: boolean
  why: string
  chips: Chip[]
  raw: Topic
}

// topics arrive ordered by rank. The first actionable one becomes the hero.
export function toCards(topics: Topic[]): Card[] {
  let heroTaken = false
  return topics.map((t) => {
    const sb = badgeForState(t.state)
    const isHero = !heroTaken && ACTIONABLE.has(t.state) && !!t.checkable
    if (isHero) heroTaken = true
    const callers = `${t.caller_count} ${t.caller_count === 1 ? 'caller' : 'callers'}`
    const chips = [
      { label: callers, k: 'plain' },
      { label: `risk: ${riskLabel(t.risk_class)}`, k: 'risk' },
      providerChip(t),
    ].filter(Boolean) as Chip[]
    return {
      id: t.id,
      title: t.title,
      badge: sb.badge,
      badgeLabel: sb.badgeLabel,
      faint: !!sb.faint,
      isHero,
      expanded: isHero,
      why: t.why_now || '',
      chips,
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
