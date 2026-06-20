// Issue #7 — Topic page, two states. Pre-check: Code reality (left) + Authoring
// receipt (right, L1 header / L2 prompt+tool-chips+summary / L3 raw session log).
// Post-check: Practice history. Receipt is provider-labeled (Codex for the hero).
import React from 'react'
import { badge, chipPlain, chipRisk, chipCodex, toolChip } from '../theme.js'
import { hl } from '../highlight.jsx'
import { COMMITTED, CODEX_LOG } from '../fixtures.js'

const mono = "'JetBrains Mono', monospace"

export default function Topic({
  heroPracticed,
  histStats,
  showLog,
  onToggleLog,
  onStartCheck,
  onBack,
}) {
  const heroBadgeCss = heroPracticed ? badge('practiced') : badge('recommended')
  const heroBadgeLabel = heroPracticed ? 'Practiced' : 'Check recommended'
  const heroCtaLabel = heroPracticed ? 'Practice again' : 'Start check'

  const hs = histStats || { elapsed: '4m 12s', runs: 3, concept: 1 }
  const history = [
    { k: 'Behavior restored', v: 'Yes', color: 'var(--green)' },
    { k: 'Elapsed', v: hs.elapsed, color: 'var(--tx)' },
    { k: 'Check runs', v: String(hs.runs), color: 'var(--tx)' },
    { k: 'Concept help used', v: hs.concept + (hs.concept === 1 ? ' question' : ' questions'), color: 'var(--tx)' },
    { k: 'Direct solution given', v: 'No', color: 'var(--accent)' },
    { k: 'Code snapshot', v: '3f9a2c1', color: 'var(--mut)' },
  ]

  return (
    <div className="lg-scroll" style={{ flex: 1, overflow: 'auto' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '30px 44px 80px' }}>
        <div
          className="lg-hover-link"
          onClick={onBack}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            color: 'var(--mut)',
            fontSize: 13,
            cursor: 'pointer',
            marginBottom: 20,
          }}
        >
          ← Worklist
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24, marginBottom: 8 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <h1 style={{ fontSize: 24, fontWeight: 600, letterSpacing: '-0.02em', margin: 0 }}>
                Tenant isolation in document caching
              </h1>
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
            onClick={onStartCheck}
            style={{
              flex: 'none',
              background: 'var(--accent)',
              color: '#1c140f',
              border: 'none',
              borderRadius: 9,
              padding: '11px 20px',
              fontFamily: "'Geist', sans-serif",
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              boxShadow: '0 1px 0 rgba(0,0,0,0.2)',
            }}
          >
            {heroCtaLabel}
          </button>
        </div>

        <div style={{ fontSize: 13.5, color: 'var(--mut)', marginBottom: 26, maxWidth: 680 }}>
          This decision is load-bearing and has no reasoning trail. Ledger isn't claiming you don't understand it — it's
          offering to test whether you can still operate it.
        </div>

        {/* 2-col body */}
        <div style={{ display: 'grid', gridTemplateColumns: '1.55fr 1fr', gap: 18, alignItems: 'start' }}>
          {/* code reality */}
          <div style={{ border: '1px solid var(--bd)', borderRadius: 12, background: 'var(--panel)', overflow: 'hidden' }}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--bd)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.01em' }}>Code reality</div>
              <div style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--mut)' }}>ledger_rag/cache.py</div>
            </div>
            <div style={{ padding: '13px 18px', borderBottom: '1px solid var(--bd)', display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, color: 'var(--faint)', marginRight: 2 }}>Why load-bearing</span>
              <span style={chipPlain}>retrieval path</span>
              <span style={chipPlain}>5 callers</span>
              <span style={chipRisk}>risk: tenant-isolation</span>
            </div>
            <div
              className="lg-scroll"
              style={{ background: '#141310', padding: '16px 18px', overflow: 'auto', fontFamily: mono, fontSize: 13, lineHeight: '21px', color: 'var(--tx)' }}
            >
              {hl(COMMITTED, false)}
            </div>
            <div style={{ padding: '13px 18px', borderTop: '1px solid var(--bd)', fontSize: 12.5, color: 'var(--mut)', lineHeight: 1.55 }}>
              If two tenants issue the same query over overlapping document IDs, a cache key that omits{' '}
              <span style={{ fontFamily: mono, color: 'var(--tx)', fontSize: 12 }}>tenant_id</span> can return one
              tenant's results to another.
            </div>
          </div>

          {/* right stack: authoring receipt */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ border: '1px solid var(--bd)', borderRadius: 12, background: 'var(--panel)', overflow: 'hidden' }}>
              <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--bd)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Authoring receipt</div>
                <span style={chipCodex}>⬡ Codex</span>
                <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, fontFamily: mono, fontSize: 10, color: 'var(--faint)' }}>
                  <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
                    <path d="M4 7V5a4 4 0 0 1 8 0v2" stroke="currentColor" strokeWidth="1.3" />
                    <rect x="3" y="7" width="10" height="6.5" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
                  </svg>
                  imported from logs
                </span>
              </div>
              <div style={{ padding: '13px 16px', borderBottom: '1px solid var(--bd)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', fontFamily: mono, fontSize: 11 }}>
                  <span style={toolChip}>read cache.py</span>
                  <span style={{ color: 'var(--faint)' }}>→</span>
                  <span style={toolChip}>apply_patch</span>
                  <span style={{ color: 'var(--faint)' }}>→</span>
                  <span style={toolChip}>shell pytest -q</span>
                </div>
              </div>
              <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <div style={{ fontFamily: mono, fontSize: 10, color: 'var(--faint)', paddingTop: 3, flex: 'none', width: 40 }}>you</div>
                  <div style={{ fontSize: 12.5, color: 'var(--mut)', lineHeight: 1.5 }}>
                    add a cache in front of the reranker so repeat queries don't re-hit the vector store
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <div style={{ fontFamily: mono, fontSize: 10, color: 'var(--accent)', paddingTop: 3, flex: 'none', width: 40 }}>codex</div>
                  <div style={{ fontSize: 12.5, color: 'var(--tx)', lineHeight: 1.5 }}>
                    Adding a <span style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--accent)' }}>RetrievalCache</span>{' '}
                    keyed on the query and document set, with get/put wrappers around the store…
                  </div>
                </div>
              </div>
              <div style={{ padding: '11px 16px', borderTop: '1px solid var(--bd)', display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontFamily: mono, fontSize: 10.5, color: 'var(--faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  rollout 9f3c · 18d ago · ~/.codex/sessions
                </span>
                <span
                  className="lg-hover-underline"
                  onClick={onToggleLog}
                  style={{ marginLeft: 'auto', flex: 'none', fontSize: 11.5, color: 'var(--accent)', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                >
                  {showLog ? 'Hide session log' : 'View session log →'}
                </span>
              </div>
              {showLog && (
                <div className="lg-scroll" style={{ borderTop: '1px solid var(--bd)', background: '#121110', maxHeight: 188, overflow: 'auto' }}>
                  <div style={{ padding: '8px 14px', fontFamily: mono, fontSize: 10.5, color: 'var(--faint)', borderBottom: '1px solid var(--bd)', position: 'sticky', top: 0, background: '#121110' }}>
                    session-9f3c.jsonl
                  </div>
                  <pre style={{ margin: 0, padding: '10px 14px', fontFamily: mono, fontSize: 10.5, lineHeight: 1.65, color: '#8c8678', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {CODEX_LOG}
                  </pre>
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
                    <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 7 }}>
                      {h.k}
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: h.color }}>{h.v}</div>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ padding: '12px 18px', borderTop: '1px solid var(--bd)', fontSize: 12.5, color: 'var(--mut)', lineHeight: 1.55 }}>
              Green behavior is necessary, not proof of mastery. Ledger records the{' '}
              <span style={{ color: 'var(--tx)' }}>cost</span> of getting there — time, attempts, whether you reached for
              the answer — not a pass/fail score.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
