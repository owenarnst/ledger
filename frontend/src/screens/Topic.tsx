// Issue #24 — Expanded Topic page. Presents the analyst-discovered, verified Topic
// (ADR-0002 / #22) as provider-neutral, progressively-disclosed Evidence. One
// screen, two states; it answers: what to own · why it matters · what Evidence
// supports it · what to do next. There is NO reasoning-trail / missing-reasoning
// section — computing an absence can't be grounded honestly — and the page never
// reveals the mutation, intended patch, or upcoming defect (Start check is the
// hand-off to the workspace).
import { Fragment, useState } from 'react'
import { badge, impactChip, toolChip } from '../theme'
import { impactLabel, providerLabel, statusBadge } from '../adapt'
import * as api from '../api'

const mono = "'JetBrains Mono', monospace"

const sectionLabel: React.CSSProperties = {
  fontFamily: mono,
  fontSize: 10,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--faint)',
  marginBottom: 9,
}

// One trace segment: a user prompt (accent-quoted) or a tool call (chip + target).
// The verified "prompt + tool-call hunk" the analyst cited from the transcript.
function TraceSegmentRow({ seg }: { seg: api.TraceSegment }) {
  if (seg.kind === 'prompt') {
    return (
      <div
        style={{
          borderLeft: '2px solid var(--accent)',
          background: 'var(--panel2)',
          borderRadius: '0 7px 7px 0',
          padding: '8px 12px',
          display: 'flex',
          gap: 9,
          alignItems: 'baseline',
        }}
      >
        <span style={{ fontFamily: mono, fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--accent)', flex: 'none' }}>
          Prompt
        </span>
        <span style={{ fontSize: 12.5, color: 'var(--tx)', lineHeight: 1.5 }}>{seg.text}</span>
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', gap: 9, alignItems: 'center', minWidth: 0 }}>
      <span style={{ ...toolChip, flex: 'none' }}>{seg.tool}</span>
      {seg.target && (
        <span style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--mut)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {seg.target}
        </span>
      )}
    </div>
  )
}

// One provider-neutral Evidence record, collapsed by default. Activating it (click
// or keyboard) reveals the exact excerpt, durable source locator, and link
// confidence. Code anchors and the Agent trace share this layout; only the
// collapsed summary and expanded body (code excerpt vs prompt + tool-call hunk) differ.
function EvidenceRow({ rec, variant }: { rec: api.EvidenceRecord; variant: 'code' | 'trace' }) {
  const [open, setOpen] = useState(false)
  const locator = rec.source_path || rec.title || '—'
  const primary = variant === 'code' ? locator : rec.session_id || locator
  return (
    <div style={{ borderTop: '1px solid var(--bd)' }}>
      <div
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen((v) => !v)
          }
        }}
        className="lg-hover-row"
        style={{ padding: '12px 16px', cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'flex-start' }}
      >
        <span
          style={{
            color: 'var(--faint)',
            fontSize: 11,
            flex: 'none',
            transform: open ? 'rotate(90deg)' : 'none',
            transition: 'transform 120ms',
            paddingTop: 2,
          }}
        >
          ▶
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {variant === 'trace' && (
              <span
                style={{
                  fontFamily: "'Geist', sans-serif",
                  fontSize: 11,
                  fontWeight: 500,
                  color: 'var(--mut)',
                  border: '1px solid var(--bd2)',
                  background: 'var(--panel2)',
                  borderRadius: 6,
                  padding: '2px 8px',
                }}
              >
                {providerLabel(rec.provider)}
              </span>
            )}
            <span style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--tx)', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {primary}
            </span>
          </div>
          {rec.relevance && (
            <div style={{ fontSize: 12.5, color: 'var(--mut)', lineHeight: 1.5, marginTop: 5 }}>{rec.relevance}</div>
          )}
        </div>
      </div>

      {open && (
        <div style={{ padding: '0 16px 14px 40px' }}>
          {variant === 'trace' && rec.segments && rec.segments.length > 0 ? (
            // The verified prompt + tool-call hunk, in transcript order.
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7, margin: '4px 0 12px' }}>
              {rec.segments.map((seg, i) => (
                <TraceSegmentRow key={i} seg={seg} />
              ))}
            </div>
          ) : (
            <>
              {rec.body && (
                <pre
                  className="lg-scroll"
                  style={{
                    margin: '4px 0 12px',
                    padding: '11px 13px',
                    background: '#121110',
                    border: '1px solid var(--bd)',
                    borderRadius: 8,
                    fontFamily: mono,
                    fontSize: 11.5,
                    lineHeight: 1.6,
                    color: '#cdcabf',
                    overflowX: 'auto',
                    whiteSpace: 'pre',
                  }}
                >
                  {rec.body}
                </pre>
              )}
              {variant === 'trace' && rec.tool_sequence && rec.tool_sequence.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                  {rec.tool_sequence.map((tool, i) => (
                    <Fragment key={i}>
                      {i > 0 && <span style={{ color: 'var(--faint)', fontFamily: mono, fontSize: 11 }}>→</span>}
                      <span style={toolChip}>{tool}</span>
                    </Fragment>
                  ))}
                </div>
              )}
            </>
          )}
          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', fontFamily: mono, fontSize: 10.5, color: 'var(--faint)' }}>
            <span>
              <span style={{ color: 'var(--mut)' }}>source</span> {locator}
            </span>
            {rec.link_confidence && (
              <span>
                <span style={{ color: 'var(--mut)' }}>link confidence</span> {rec.link_confidence}
              </span>
            )}
            {rec.excerpt_sha && (
              <span>
                <span style={{ color: 'var(--mut)' }}>excerpt</span> {rec.excerpt_sha}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

interface EvidenceGroupProps {
  title: string
  records: api.EvidenceRecord[]
  variant: 'code' | 'trace'
  emptyNote: string
}

function EvidenceGroup({ title, records, variant, emptyNote }: EvidenceGroupProps) {
  return (
    <div style={{ border: '1px solid var(--bd)', borderRadius: 12, background: 'var(--panel)', overflow: 'hidden' }}>
      <div style={{ padding: '13px 16px', display: 'flex', alignItems: 'center', gap: 9 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{title}</span>
        <span style={{ fontFamily: mono, fontSize: 11, color: 'var(--faint)' }}>
          {records.length} {records.length === 1 ? 'record' : 'records'}
        </span>
      </div>
      {records.length === 0 ? (
        <div style={{ padding: '0 16px 14px', fontSize: 12.5, color: 'var(--faint)' }}>{emptyNote}</div>
      ) : (
        records.map((rec, i) => <EvidenceRow key={i} rec={rec} variant={variant} />)
      )}
    </div>
  )
}

interface TopicProps {
  detail: api.TopicDetail
  heroPracticed: boolean
  histStats: { elapsed: string; runs: number; concept: number } | null
  onStartCheck: (difficulty: api.Difficulty) => void
  onBack: () => void
}

export default function Topic({ detail, heroPracticed, histStats, onStartCheck, onBack }: TopicProps) {
  const [selectedDifficulty, setSelectedDifficulty] = useState<api.Difficulty>('medium')
  const canCheck = !!detail.current_revision
  const sb = statusBadge(detail.state)
  const statusBadgeCss = badge(sb.kind)
  const impact = impactLabel(detail.impact_level)
  const heroStatusLabel = heroPracticed ? 'Ownership check completed' : 'Ownership check recommended'
  const checkAction = heroPracticed ? 'Practice again' : 'Start check'

  const obligation = detail.summary || detail.current_revision?.invariant || ''
  const invariant = detail.current_revision?.invariant || ''
  const codeAnchors = detail.code_anchors || []
  const traces = detail.development_traces || []

  const hs = histStats || { elapsed: '—', runs: 0, concept: 0 }
  const codeChangedAfter = detail.state === 'code_changed_since_practice'
  const history = [
    { k: 'Behavior restored', v: 'Yes', color: 'var(--green)' },
    { k: 'Elapsed', v: hs.elapsed, color: 'var(--tx)' },
    { k: 'Check runs', v: String(hs.runs), color: 'var(--tx)' },
    { k: 'Concept help used', v: hs.concept + (hs.concept === 1 ? ' question' : ' questions'), color: 'var(--tx)' },
    { k: 'Direct solution given', v: 'No', color: 'var(--accent)' },
    { k: 'Code changed after', v: codeChangedAfter ? 'Yes' : 'No', color: codeChangedAfter ? 'var(--accent)' : 'var(--mut)' },
  ]

  return (
    <div className="lg-scroll" style={{ flex: 1, overflow: 'auto' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '30px 44px 80px' }}>
        <div
          className="lg-hover-link"
          onClick={onBack}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--mut)', fontSize: 13, cursor: 'pointer', marginBottom: 20 }}
        >
          ← Worklist
        </div>

        {/* Header: title · ownership status · impact · Check action */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24, marginBottom: 26 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <h1 style={{ fontSize: 24, fontWeight: 600, letterSpacing: '-0.02em', margin: 0 }}>{detail.title}</h1>
              <span style={{ ...statusBadgeCss, ...(sb.faint ? { opacity: 0.85 } : null) }}>{detail.ownership_status}</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--faint)' }}>
                  Impact
                </span>
                <span style={impactChip(detail.impact_level)}>{impact}</span>
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginTop: 11, color: 'var(--accent)', fontSize: 14, fontWeight: 500 }}>
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                <path d="M8 1.8 2.5 4.2v3.4c0 3.4 2.3 5.7 5.5 6.6 3.2-.9 5.5-3.2 5.5-6.6V4.2L8 1.8Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
                <path d="M5.8 8.1 7.3 9.6l3-3.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {heroStatusLabel}
            </div>
          </div>
          <div style={{ flex: 'none', minWidth: 310, display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: 9 }}>
            {canCheck ? (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 4, padding: 4, border: '1px solid var(--bd2)', borderRadius: 11, background: 'var(--panel)' }}>
                  {[
                    { difficulty: 'easy' as api.Difficulty, label: 'Easy', sub: 'quiz' },
                    { difficulty: 'medium' as api.Difficulty, label: 'Medium', sub: 'guided' },
                    { difficulty: 'hard' as api.Difficulty, label: 'Hard', sub: 'sandbox' },
                  ].map((item) => {
                    const active = selectedDifficulty === item.difficulty
                    return (
                      <button
                        key={item.difficulty}
                        onClick={() => setSelectedDifficulty(item.difficulty)}
                        style={{
                          border: 'none',
                          borderRadius: 8,
                          padding: '8px 8px 7px',
                          background: active ? 'var(--accent)' : 'transparent',
                          color: active ? '#1c140f' : 'var(--mut)',
                          cursor: 'pointer',
                          textAlign: 'center',
                          boxShadow: active ? '0 1px 0 rgba(0,0,0,0.2)' : 'none',
                        }}
                      >
                        <div style={{ fontSize: 12.5, fontWeight: 700 }}>{item.label}</div>
                        <div style={{ marginTop: 1, fontFamily: mono, fontSize: 9.5, opacity: 0.78 }}>{item.sub}</div>
                      </button>
                    )
                  })}
                </div>
                <button
                  onClick={() => onStartCheck(selectedDifficulty)}
                  style={{
                    background: 'linear-gradient(180deg, var(--accent), #b9673f)',
                    color: '#1c140f',
                    border: 'none',
                    borderRadius: 9,
                    padding: '11px 16px',
                    fontFamily: "'Geist', sans-serif",
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: 'pointer',
                    boxShadow: '0 1px 0 rgba(0,0,0,0.2)',
                  }}
                >
                  {checkAction} →
                </button>
              </>
            ) : (
              <button
                disabled
                style={{ background: 'var(--panel2)', color: 'var(--faint)', border: '1px solid var(--bd2)', borderRadius: 9, padding: '11px 20px', fontFamily: "'Geist', sans-serif", fontSize: 14, fontWeight: 600, cursor: 'not-allowed' }}
              >
                No sandbox available
              </button>
            )}
          </div>
        </div>

        {/* What you need to own + Why it matters */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, alignItems: 'start', marginBottom: 18 }}>
          <div style={{ border: '1px solid var(--bd)', borderRadius: 12, background: 'var(--panel)', padding: '16px 18px' }}>
            <div style={sectionLabel}>What you need to own</div>
            <div style={{ fontSize: 13.5, color: 'var(--tx)', lineHeight: 1.6 }}>{obligation || 'Not yet specified.'}</div>
            {invariant && invariant !== obligation && (
              <div style={{ marginTop: 13, paddingTop: 13, borderTop: '1px solid var(--bd)' }}>
                <div style={{ ...sectionLabel, color: 'var(--accent)' }}>Invariant to hold</div>
                <div style={{ fontSize: 13, color: 'var(--tx)', lineHeight: 1.6 }}>{invariant}</div>
              </div>
            )}
          </div>
          <div style={{ border: '1px solid var(--bd)', borderRadius: 12, background: 'var(--panel)', padding: '16px 18px' }}>
            <div style={sectionLabel}>Why it matters</div>
            <div style={{ fontSize: 13.5, color: 'var(--tx)', lineHeight: 1.6 }}>
              {detail.impact_consequence || 'Consequence not yet specified.'}
            </div>
            <div style={{ marginTop: 13, display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--mut)' }}>
              Rated
              <span style={impactChip(detail.impact_level)}>{impact}</span>
              impact.
            </div>
          </div>
        </div>

        {/* Supporting Evidence — provider-neutral, progressively disclosed */}
        <div style={{ ...sectionLabel, marginBottom: 12 }}>Supporting Evidence</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <EvidenceGroup
            title="Code anchors"
            records={codeAnchors}
            variant="code"
            emptyNote="No code anchors recorded for this Topic."
          />
          <EvidenceGroup
            title="Agent trace"
            records={traces}
            variant="trace"
            emptyNote="No agent trace is linked to this Topic yet."
          />
        </div>

        {/* Ownership history */}
        <div style={{ marginTop: 26, border: '1px solid var(--bd)', borderRadius: 12, background: 'var(--panel)', overflow: 'hidden' }}>
          <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--bd)', display: 'flex', alignItems: 'center', gap: 9 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Ownership history</div>
            <span style={{ fontFamily: mono, fontSize: 11, color: 'var(--faint)' }}>
              {heroPracticed ? '1 ownership event recorded' : 'no checks completed yet'}
            </span>
          </div>
          {heroPracticed ? (
            <>
              <div style={{ padding: 8 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 1, background: 'var(--bd)' }}>
                  {history.map((h, i) => (
                    <div key={i} style={{ background: 'var(--panel)', padding: '14px 16px' }}>
                      <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 7 }}>{h.k}</div>
                      <div style={{ fontSize: 14, fontWeight: 500, color: h.color }}>{h.v}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div style={{ padding: '12px 18px', borderTop: '1px solid var(--bd)', fontSize: 12.5, color: 'var(--mut)', lineHeight: 1.55 }}>
                Green behavior is necessary, not proof of mastery. Ledger records the{' '}
                <span style={{ color: 'var(--tx)' }}>cost</span> of getting there — time, attempts, whether you reached for the
                answer — not a pass/fail score.
              </div>
            </>
          ) : (
            <div style={{ padding: '16px 18px', fontSize: 13, color: 'var(--mut)', lineHeight: 1.6 }}>
              You haven't run an ownership check on this Topic yet. Start a check to record your first practice —
              elapsed time, check runs, whether you used conceptual help, and whether the code changed afterward.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
