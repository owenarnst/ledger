// Issue #15 — Check workspace. 3-pane: Task (resizable) | Sandbox (file tree +
// editor overlay + run bar + output) | Coach (resizable, Claude-only). The run
// verdict is driven by the banner state; exit code is the oracle (mocked here).
import React from 'react'
import { hl } from '../highlight.jsx'
import { TEST, CONFTEST, OUT_FAIL, OUT_PASS } from '../fixtures.js'

const mono = "'JetBrains Mono', monospace"

const FILE_META = [
  { name: 'cache.py', icon: '■', modified: true },
  { name: 'test_cache.py', icon: '□', modified: false },
  { name: 'conftest.py', icon: '□', modified: false },
]

const COACH_CHIPS = [
  { label: 'Just tell me what to change', q: 'Just tell me what I need to change.' },
  { label: 'What is this code supposed to do?', q: 'What is this code supposed to do?' },
  { label: 'Where do I start?', q: 'Where do I start?' },
]

function banner(phase, runs) {
  const base = {
    padding: '9px 16px',
    fontFamily: mono,
    fontSize: 11.5,
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  }
  if (phase === 'creating')
    return {
      label: '◴ Creating sandbox…',
      css: { ...base, color: 'var(--mut)', background: '#1a1813' },
      out: 'Provisioning temp dir, applying curated mutation, validating exactly one check fails…',
    }
  if (phase === 'running')
    return { label: '◴ Running pytest…', css: { ...base, color: 'var(--mut)', background: '#1a1813' }, out: '' }
  if (phase === 'fail')
    return {
      label: '✕ 1 failed · 1 passed',
      css: { ...base, color: 'var(--red)', background: 'rgba(217,106,94,0.10)', borderBottom: '1px solid rgba(217,106,94,0.25)' },
      out: OUT_FAIL,
    }
  if (phase === 'pass')
    return {
      label: '✓ 2 passed',
      css: { ...base, color: 'var(--green)', background: 'rgba(95,176,126,0.10)', borderBottom: '1px solid rgba(95,176,126,0.25)' },
      out: OUT_PASS,
    }
  return {
    label: 'No checks run yet',
    css: { ...base, color: 'var(--faint)', background: '#1a1813' },
    out: 'Edit ledger_rag/cache.py, then Run checks. Behavior must go green on exit code 0.',
  }
}

export default function Workspace({
  taskW,
  coachW,
  dragTask,
  dragCoach,
  activeFile,
  setActiveFile,
  code,
  onCode,
  phase,
  running,
  runs,
  runChecks,
  thread,
  coachInput,
  onCoachInput,
  onCoachKey,
  sendCoach,
  askChip,
  canComplete,
  completeCheck,
}) {
  const editable = activeFile === 'cache.py'
  const roContent = activeFile === 'test_cache.py' ? TEST : activeFile === 'conftest.py' ? CONFTEST : ''
  const lineNos = (code || '').split('\n').map((_, i) => i + 1)
  const roLineNos = roContent.split('\n').map((_, i) => i + 1)
  const b = banner(phase, runs)

  const runBtnStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    background: running ? 'rgba(200,116,77,0.5)' : 'var(--accent)',
    color: '#1c140f',
    border: 'none',
    borderRadius: 8,
    padding: '8px 16px',
    fontFamily: "'Geist', sans-serif",
    fontSize: 13,
    fontWeight: 600,
    cursor: running ? 'default' : 'pointer',
  }

  const resizeStyle = { width: 8, flex: 'none', margin: '0 -4px', zIndex: 6, cursor: 'col-resize', background: 'transparent' }

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
        {/* TASK */}
        <div
          className="lg-scroll"
          style={{ width: taskW, flex: 'none', borderRight: '1px solid var(--bd)', background: 'var(--panel)', overflow: 'auto', padding: '18px' }}
        >
          <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 14 }}>
            Task
          </div>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontFamily: mono,
              fontSize: 10.5,
              color: 'var(--red)',
              border: '1px solid rgba(217,106,94,0.3)',
              background: 'rgba(217,106,94,0.08)',
              padding: '3px 8px',
              borderRadius: 5,
              marginBottom: 14,
            }}
          >
            ● behavior failing
          </div>
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 10px', letterSpacing: '-0.01em' }}>Cross-tenant cache leak</h2>
          <p style={{ fontSize: 13, color: 'var(--mut)', lineHeight: 1.6, margin: '0 0 16px' }}>
            RetrievalCache is serving one tenant's documents to another. When two tenants issue the same query over the
            same document set, the second caller receives the first caller's cached results.
          </p>
          <div style={{ borderTop: '1px solid var(--bd)', paddingTop: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--faint)', marginBottom: 6 }}>Failing test</div>
            <div style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--tx)', wordBreak: 'break-all' }}>
              test_cache_isolation_<wbr />between_tenants
            </div>
          </div>
          <div style={{ borderTop: '1px solid var(--bd)', paddingTop: 14, marginTop: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--faint)', marginBottom: 6 }}>Invariant to restore</div>
            <div style={{ fontSize: 12.5, color: 'var(--mut)', lineHeight: 1.55 }}>
              Each tenant must only ever receive results computed for that tenant.
            </div>
          </div>
        </div>
        <div className="lg-resize" onMouseDown={dragTask} title="Drag to resize" style={resizeStyle} />

        {/* SANDBOX */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg)' }}>
          <div style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
            {/* file tree */}
            <div style={{ width: 172, flex: 'none', borderRight: '1px solid var(--bd)', background: 'var(--panel)', padding: '12px 8px', overflow: 'auto' }}>
              <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--faint)', padding: '4px 8px 10px' }}>
                Sandbox
              </div>
              {FILE_META.map((f) => (
                <div
                  key={f.name}
                  onClick={() => setActiveFile(f.name)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '6px 9px',
                    marginBottom: 2,
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontFamily: mono,
                    fontSize: 12,
                    ...(activeFile === f.name ? { background: 'var(--panel2)', color: 'var(--tx)' } : { color: 'var(--mut)' }),
                  }}
                >
                  <span style={{ opacity: 0.7 }}>{f.icon}</span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                  {f.modified && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', flex: 'none' }} />}
                </div>
              ))}
            </div>

            {/* editor + output */}
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div style={{ flex: 'none', height: 38, borderBottom: '1px solid var(--bd)', background: 'var(--panel)', display: 'flex', alignItems: 'center', gap: 8, padding: '0 14px', fontFamily: mono, fontSize: 11.5, color: 'var(--mut)' }}>
                <span style={{ opacity: 0.7 }}>▾</span>
                {activeFile}
                {!editable && (
                  <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--faint)', border: '1px solid var(--bd2)', padding: '1px 6px', borderRadius: 4 }}>
                    read-only
                  </span>
                )}
              </div>

              {editable ? (
                <div style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden', background: '#141310', position: 'relative' }}>
                  <div style={{ flex: 'none', width: 46, padding: '14px 0', textAlign: 'right', fontFamily: mono, fontSize: 13, lineHeight: '21px', color: '#46423a', userSelect: 'none', background: '#141310' }}>
                    {lineNos.map((n) => (
                      <div key={n} style={{ paddingRight: 12 }}>
                        {n}
                      </div>
                    ))}
                  </div>
                  <div style={{ flex: 1, minWidth: 0, position: 'relative' }}>
                    <pre style={{ margin: 0, padding: '14px 16px', fontFamily: mono, fontSize: 13, lineHeight: '21px', whiteSpace: 'pre', pointerEvents: 'none', minHeight: '100%' }}>
                      {hl(code, false)}
                    </pre>
                    <textarea
                      spellCheck="false"
                      value={code}
                      onChange={onCode}
                      style={{
                        position: 'absolute',
                        inset: 0,
                        margin: 0,
                        padding: '14px 16px',
                        fontFamily: mono,
                        fontSize: 13,
                        lineHeight: '21px',
                        whiteSpace: 'pre',
                        overflow: 'auto',
                        border: 'none',
                        outline: 'none',
                        resize: 'none',
                        background: 'transparent',
                        color: 'transparent',
                        caretColor: 'var(--tx)',
                        tabSize: 4,
                      }}
                    />
                  </div>
                </div>
              ) : (
                <div className="lg-scroll" style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'auto', background: '#141310' }}>
                  <div style={{ flex: 'none', width: 46, padding: '14px 0', textAlign: 'right', fontFamily: mono, fontSize: 13, lineHeight: '21px', color: '#3a362f', userSelect: 'none' }}>
                    {roLineNos.map((n) => (
                      <div key={n} style={{ paddingRight: 12 }}>
                        {n}
                      </div>
                    ))}
                  </div>
                  <pre style={{ margin: 0, padding: '14px 16px', fontFamily: mono, fontSize: 13, lineHeight: '21px', whiteSpace: 'pre', color: 'var(--mut)' }}>
                    {hl(roContent, true)}
                  </pre>
                </div>
              )}

              {/* run bar */}
              <div style={{ flex: 'none', borderTop: '1px solid var(--bd)', background: 'var(--panel)', padding: '11px 16px', display: 'flex', alignItems: 'center', gap: 14 }}>
                <button onClick={runChecks} style={runBtnStyle}>
                  {running && (
                    <span style={{ width: 11, height: 11, border: '2px solid rgba(28,20,15,0.35)', borderTopColor: '#1c140f', borderRadius: '50%', display: 'inline-block', animation: 'spin 0.7s linear infinite' }} />
                  )}
                  {running ? 'Running…' : 'Run checks'}
                </button>
                <div style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--faint)' }}>exit code is the oracle · pytest -q</div>
              </div>

              {/* output */}
              <div className="lg-scroll" style={{ flex: 'none', height: 200, borderTop: '1px solid var(--bd)', background: '#121110', overflow: 'auto' }}>
                <div style={b.css}>{b.label}</div>
                <pre style={{ margin: 0, padding: '12px 16px', fontFamily: mono, fontSize: 11.5, lineHeight: 1.65, color: 'var(--mut)', whiteSpace: 'pre-wrap' }}>
                  {b.out}
                </pre>
              </div>
            </div>
          </div>
        </div>

        {/* COACH */}
        <div className="lg-resize" onMouseDown={dragCoach} title="Drag to resize" style={resizeStyle} />
        <div style={{ flex: 'none', width: coachW, borderLeft: '1px solid var(--bd)', background: 'var(--bg)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ flex: 'none', padding: '14px 16px', borderBottom: '1px solid var(--bd)', background: 'var(--panel)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)' }} />
              <div style={{ fontSize: 13, fontWeight: 600 }}>Coach</div>
              <span style={{ marginLeft: 'auto', fontFamily: mono, fontSize: 10, color: 'var(--faint)', border: '1px solid var(--bd2)', padding: '2px 7px', borderRadius: 5 }}>
                claude -p · tools denied
              </span>
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--mut)', marginTop: 6 }}>
              Conceptual help only. The coach can't see your code or the fix — by design.
            </div>
          </div>

          <div className="lg-scroll" style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
            {thread.map((m, i) => {
              if (m.role === 'user')
                return (
                  <div key={i} style={{ alignSelf: 'flex-end', maxWidth: '88%', background: 'var(--panel2)', border: '1px solid var(--bd2)', borderRadius: '11px 11px 3px 11px', padding: '9px 13px', fontSize: 13, color: 'var(--tx)', lineHeight: 1.5 }}>
                    {m.text}
                  </div>
                )
              if (m.role === 'thinking')
                return (
                  <div key={i} style={{ alignSelf: 'flex-start', display: 'flex', gap: 5, padding: '10px 4px' }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--mut)', animation: 'blink 1.2s infinite 0s' }} />
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--mut)', animation: 'blink 1.2s infinite 0.2s' }} />
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--mut)', animation: 'blink 1.2s infinite 0.4s' }} />
                  </div>
                )
              const refusal = !!m.refusal
              return (
                <div
                  key={i}
                  style={{
                    alignSelf: 'flex-start',
                    maxWidth: '94%',
                    background: 'var(--panel)',
                    border: `1px solid ${refusal ? 'rgba(200,116,77,0.4)' : 'var(--bd2)'}`,
                    borderLeft: `3px solid ${refusal ? 'var(--accent)' : 'var(--bd2)'}`,
                    borderRadius: '4px 11px 11px 11px',
                    padding: 14,
                  }}
                >
                  {refusal && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 10 }}>
                      <span style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--accent)', border: '1px solid rgba(200,116,77,0.35)', padding: '2px 7px', borderRadius: 5 }}>
                        Patch withheld
                      </span>
                    </div>
                  )}
                  {refusal && m.lead && <div style={{ fontSize: 13, color: 'var(--tx)', lineHeight: 1.55, marginBottom: 13 }}>{m.lead}</div>}
                  {m.concept && (
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 5 }}>
                        {m.conceptLabel || 'Concept'}
                      </div>
                      <div style={{ fontSize: 13, color: 'var(--tx)', lineHeight: 1.55 }}>{m.concept}</div>
                    </div>
                  )}
                  {m.diagnostic && (
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--cool)', marginBottom: 5 }}>
                        Diagnostic question
                      </div>
                      <div style={{ fontSize: 13, color: 'var(--tx)', lineHeight: 1.55 }}>{m.diagnostic}</div>
                    </div>
                  )}
                  {m.observation && (
                    <div>
                      <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--mut)', marginBottom: 5 }}>
                        Suggested observation
                      </div>
                      <div style={{ fontSize: 13, color: 'var(--mut)', lineHeight: 1.55 }}>{m.observation}</div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          <div style={{ flex: 'none', borderTop: '1px solid var(--bd)', background: 'var(--panel)', padding: 12 }}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
              {COACH_CHIPS.map((ch, i) => (
                <div
                  key={i}
                  className="lg-hover-chip"
                  onClick={() => askChip(ch.q)}
                  style={{ fontSize: 11.5, color: 'var(--mut)', border: '1px solid var(--bd2)', background: 'var(--panel2)', padding: '5px 10px', borderRadius: 14, cursor: 'pointer' }}
                >
                  {ch.label}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <textarea
                className="lg-textarea"
                spellCheck="false"
                value={coachInput}
                onChange={onCoachInput}
                onKeyDown={onCoachKey}
                placeholder="Ask a conceptual question…"
                rows={1}
                style={{ flex: 1, resize: 'none', background: 'var(--bg)', border: '1px solid var(--bd2)', borderRadius: 9, padding: '9px 12px', fontFamily: "'Geist', sans-serif", fontSize: 13, color: 'var(--tx)', outline: 'none', lineHeight: 1.4, maxHeight: 90 }}
              />
              <button onClick={sendCoach} style={{ flex: 'none', background: 'var(--accent)', color: '#1c140f', border: 'none', borderRadius: 9, width: 38, height: 38, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M2.5 8h10M8 3.5 12.5 8 8 12.5" stroke="#1c140f" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* completion bar */}
      {canComplete && (
        <div style={{ flex: 'none', borderTop: '1px solid var(--bd)', background: 'linear-gradient(0deg, rgba(95,176,126,0.08), transparent)', padding: '13px 22px', display: 'flex', alignItems: 'center', gap: 14, animation: 'fadeUp 220ms ease both' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <div style={{ width: 18, height: 18, borderRadius: '50%', background: 'rgba(95,176,126,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                <path d="M3.5 8.5 6.5 11.5 12.5 5" stroke="var(--green)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <span style={{ fontSize: 13.5, color: 'var(--tx)' }}>Behavior restored. Ledger captured your struggle, not just the pass.</span>
          </div>
          <button onClick={completeCheck} style={{ marginLeft: 'auto', background: 'var(--green)', color: '#10231a', border: 'none', borderRadius: 9, padding: '10px 18px', fontFamily: "'Geist', sans-serif", fontSize: 13.5, fontWeight: 600, cursor: 'pointer' }}>
            Finish &amp; save to ledger →
          </button>
        </div>
      )}
    </div>
  )
}
