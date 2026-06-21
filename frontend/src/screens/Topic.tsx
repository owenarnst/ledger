// Issue #7 — Topic page, two states. Pre-check: Code reality (left, grounded in
// the `code` evidence + revision invariant) + Authoring receipt (right, L1 header
// / L2 tool-chips + summary / L3 imported session record). Post-check: Practice
// history. Everything is provider-labeled from the backend evidence — the hero
// is Claude-authored here (ADR-0001 spine), not the design's placeholder Codex.
import { Fragment } from 'react'
import { badge, chipPlain, chipRisk, toolChip, chipForKind } from '../theme'
import { deriveReceipt, riskLabel } from '../adapt'
import * as api from '../api'

const mono = "'JetBrains Mono', monospace"

interface TopicProps {
  detail: api.TopicDetail
  heroPracticed: boolean
  histStats: { elapsed: string; runs: number; concept: number } | null
  showLog: boolean
  onToggleLog: () => void
  onStartCheck: () => void
  onBack: () => void
}

export default function Topic({ detail, heroPracticed, histStats, showLog, onToggleLog, onStartCheck, onBack }: TopicProps) {
  const r = deriveReceipt(detail)
  // A check is offered only when the backend has a curated recipe for this
  // Topic (and a revision to sandbox). Otherwise the backend refuses it.
  const canCheck = !!detail.current_revision && !!detail.checkable
  const heroBadgeCss = heroPracticed ? badge('practiced') : badge('recommended')
  const heroBadgeLabel = heroPracticed ? 'Practiced' : 'Check recommended'
  const heroCtaLabel = heroPracticed ? 'Practice again' : 'Start check'
  const callers = `${detail.caller_count} ${detail.caller_count === 1 ? 'caller' : 'callers'}`

  const hs = histStats || { elapsed: '—', runs: 0, concept: 0 }
  const history = [
    { k: 'Behavior restored', v: 'Yes', color: 'var(--green)' },
    { k: 'Elapsed', v: hs.elapsed, color: 'var(--tx)' },
    { k: 'Check runs', v: String(hs.runs), color: 'var(--tx)' },
    { k: 'Concept help used', v: hs.concept + (hs.concept === 1 ? ' question' : ' questions'), color: 'var(--tx)' },
    { k: 'Direct solution given', v: 'No', color: 'var(--accent)' },
    { k: 'Code snapshot', v: detail.current_revision?.commit_sha || '—', color: 'var(--mut)' },
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

        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24, marginBottom: 8 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <h1 style={{ fontSize: 24, fontWeight: 600, letterSpacing: '-0.02em', margin: 0 }}>{detail.title}</h1>
              <span style={heroBadgeCss}>{heroBadgeLabel}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginTop: 11, color: 'var(--accent)', fontSize: 14, fontWeight: 500 }}>
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                <path d="M8 1.8 2.5 4.2v3.4c0 3.4 2.3 5.7 5.5 6.6 3.2-.9 5.5-3.2 5.5-6.6V4.2L8 1.8Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
                <path d="M5.8 8.1 7.3 9.6l3-3.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Ownership check recommended
            </div>
          </div>
          <button
            onClick={canCheck ? onStartCheck : undefined}
            disabled={!canCheck}
            style={{
              flex: 'none',
              background: canCheck ? 'var(--accent)' : 'var(--panel2)',
              color: canCheck ? '#1c140f' : 'var(--faint)',
              border: canCheck ? 'none' : '1px solid var(--bd2)',
              borderRadius: 9,
              padding: '11px 20px',
              fontFamily: "'Geist', sans-serif",
              fontSize: 14,
              fontWeight: 600,
              cursor: canCheck ? 'pointer' : 'not-allowed',
              boxShadow: canCheck ? '0 1px 0 rgba(0,0,0,0.2)' : 'none',
            }}
          >
            {canCheck ? heroCtaLabel : 'No check available'}
          </button>
        </div>

        <div style={{ fontSize: 13.5, color: 'var(--mut)', marginBottom: 26, maxWidth: 680 }}>
          {detail.summary}
          {r.trail && (
            <>
              {' '}
              Ledger isn’t claiming you don’t understand it — it’s offering to test whether you can still operate it.
            </>
          )}
        </div>

        {/* 2-col body */}
        <div style={{ display: 'grid', gridTemplateColumns: '1.55fr 1fr', gap: 18, alignItems: 'start' }}>
          {/* code reality */}
          <div style={{ border: '1px solid var(--bd)', borderRadius: 12, background: 'var(--panel)', overflow: 'hidden' }}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--bd)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.01em' }}>Code reality</div>
              <div style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--mut)' }}>{r.codePath}</div>
            </div>
            <div style={{ padding: '13px 18px', borderBottom: '1px solid var(--bd)', display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, color: 'var(--faint)', marginRight: 2 }}>Why load-bearing</span>
              <span style={chipPlain}>{callers}</span>
              <span style={chipRisk}>risk: {riskLabel(detail.risk_class)}</span>
            </div>
            {r.code && (
              <div style={{ padding: '15px 18px', borderBottom: '1px solid var(--bd)' }}>
                <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 7 }}>
                  Behavior in tree
                </div>
                <div style={{ fontSize: 13, color: 'var(--tx)', lineHeight: 1.6 }}>{r.code.body}</div>
              </div>
            )}
            {r.invariant && (
              <div style={{ padding: '15px 18px' }}>
                <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 7 }}>
                  Invariant to hold
                </div>
                <div style={{ fontSize: 13, color: 'var(--tx)', lineHeight: 1.6 }}>{r.invariant}</div>
              </div>
            )}
            {r.trail && (
              <div style={{ padding: '12px 18px', borderTop: '1px solid var(--bd)', fontSize: 12.5, color: 'var(--mut)', lineHeight: 1.55, display: 'flex', gap: 8 }}>
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flex: 'none', marginTop: 2 }}>
                  <circle cx="7" cy="7" r="4.6" stroke="currentColor" strokeWidth="1.3" />
                  <path d="m10.5 10.5 2.5 2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                </svg>
                <span>{r.trail.body}</span>
              </div>
            )}
          </div>

          {/* right stack: authoring receipt */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ border: '1px solid var(--bd)', borderRadius: 12, background: 'var(--panel)', overflow: 'hidden' }}>
              <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--bd)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Authoring receipt</div>
                {r.hasReceipt ? (
                  <>
                    <span style={chipForKind(r.providerChipKind as any)}>{r.providerLabel}</span>
                    <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, fontFamily: mono, fontSize: 10, color: 'var(--faint)' }}>
                      <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
                        <path d="M4 7V5a4 4 0 0 1 8 0v2" stroke="currentColor" strokeWidth="1.3" />
                        <rect x="3" y="7" width="10" height="6.5" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
                      </svg>
                      imported from logs
                    </span>
                  </>
                ) : (
                  <span style={{ marginLeft: 'auto', fontFamily: mono, fontSize: 10, color: 'var(--faint)' }}>
                    extracted from code
                  </span>
                )}
              </div>

              {!r.hasReceipt && (
                <div style={{ padding: '14px 16px', fontSize: 12.5, color: 'var(--mut)', lineHeight: 1.55 }}>
                  No authoring receipt. Ledger surfaced this decision from the code itself, not from a
                  linked coding session — what it searched for the reasoning is shown under Code reality.
                </div>
              )}

              {r.toolSequence.length > 0 && (
                <div style={{ padding: '13px 16px', borderBottom: '1px solid var(--bd)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', fontFamily: mono, fontSize: 11 }}>
                    {r.toolSequence.map((tool, i) => (
                      <Fragment key={i}>
                        {i > 0 && <span style={{ color: 'var(--faint)' }}>→</span>}
                        <span style={toolChip}>{tool}</span>
                      </Fragment>
                    ))}
                  </div>
                </div>
              )}

              {r.receipt && (
                <div style={{ padding: '14px 16px', display: 'flex', gap: 8 }}>
                  <div style={{ fontFamily: mono, fontSize: 10, color: 'var(--accent)', paddingTop: 3, flex: 'none', width: 56 }}>
                    {r.provider === 'codex' ? 'codex' : 'claude'}
                  </div>
                  <div style={{ fontSize: 12.5, color: 'var(--tx)', lineHeight: 1.5 }}>{r.receipt.body}</div>
                </div>
              )}

              {r.hasReceipt && (
                <div style={{ padding: '11px 16px', borderTop: '1px solid var(--bd)', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontFamily: mono, fontSize: 10.5, color: 'var(--faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {[r.sourcePath, r.linkConfidence].filter(Boolean).join(' · ') || 'no source recorded'}
                  </span>
                  {(r.toolSequence.length > 0 || r.sessionId) && (
                    <span
                      className="lg-hover-underline"
                      onClick={onToggleLog}
                      style={{ marginLeft: 'auto', flex: 'none', fontSize: 11.5, color: 'var(--accent)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                    >
                      {showLog ? 'Hide session record' : 'View session record →'}
                    </span>
                  )}
                </div>
              )}

              {showLog && (
                <div className="lg-scroll" style={{ borderTop: '1px solid var(--bd)', background: '#121110', maxHeight: 200, overflow: 'auto' }}>
                  <div style={{ padding: '8px 14px', fontFamily: mono, fontSize: 10.5, color: 'var(--faint)', borderBottom: '1px solid var(--bd)', position: 'sticky', top: 0, background: '#121110' }}>
                    {r.sourcePath || 'imported session record'}
                  </div>
                  <div style={{ padding: '10px 14px', fontFamily: mono, fontSize: 10.5, lineHeight: 1.7, color: '#8c8678' }}>
                    {r.sessionId && <div>session_id: {r.sessionId}</div>}
                    {r.linkConfidence && <div>link_confidence: {r.linkConfidence}</div>}
                    {r.toolSequence.length > 0 && <div style={{ marginTop: 6, color: 'var(--faint)' }}>tool_sequence:</div>}
                    {r.toolSequence.map((tool, i) => (
                      <div key={i} style={{ paddingLeft: 12 }}>
                        {i + 1}. {tool}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* practice history (post-check) */}
        {heroPracticed && (
          <div style={{ marginTop: 26, border: '1px solid var(--bd)', borderRadius: 12, background: 'var(--panel)', overflow: 'hidden', animation: 'fadeUp 240ms ease both' }}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--bd)', display: 'flex', alignItems: 'center', gap: 9 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Practice history</div>
              <span style={{ fontFamily: mono, fontSize: 11, color: 'var(--faint)' }}>1 ownership event recorded</span>
            </div>
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
              <span style={{ color: 'var(--tx)' }}>cost</span> of getting there — time, attempts, whether you reached for the answer — not a pass/fail score.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
