// Issue #15 — Check workspace. 3-pane: Task (resizable) | Sandbox (file tree +
// editor overlay + run bar + output) | Coach (resizable, Claude-only). Files,
// run verdict, and coaching are all live from the backend. The verdict comes
// from the run's `passed` field — pytest's exit code is the oracle; the UI never
// parses the test text for the result.
import { useState } from 'react'
import { hl } from '../highlight'
import { renderCoach } from '../coachmd'
import * as api from '../api'

const mono = "'JetBrains Mono', monospace"

const COACH_CHIPS = [
  { label: 'Just tell me what to change', q: 'Just tell me what I need to change.' },
  { label: 'What is this code supposed to do?', q: 'What is this code supposed to do?' },
  { label: 'Where do I start?', q: 'Where do I start?' },
]

const WITHHELD = /cannot provide (?:code|a patch)|can't (?:hand|give) you the patch|cannot give you the patch/i

type Phase = 'idle' | 'creating' | 'running' | 'fail' | 'pass' | 'error'

interface WorkspaceProps {
  topic: api.TopicDetail | null
  check: api.Check | null
  taskW: number
  coachW: number
  dragTask: (e: React.MouseEvent) => void
  dragCoach: (e: React.MouseEvent) => void
  files: any[]
  activeFile: string | null
  setActiveFile: (path: string) => void
  code: string
  roContent: Record<string, string>
  onCode: (e: React.ChangeEvent<HTMLTextAreaElement>) => void
  phase: Phase
  running: boolean
  pseudocodeRunning: boolean
  pseudocodeMode: 'hints' | 'prints'
  runOutput: string
  runChecks: () => void
  addPseudocodeComments: () => void
  thread: any[]
  coachInput: string
  coachProvider: 'claude-code' | 'codex-exec'
  onCoachProvider: (provider: 'claude-code' | 'codex-exec') => void
  onCoachInput: (e: React.ChangeEvent<HTMLTextAreaElement>) => void
  onCoachKey: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void
  sendCoach: () => void
  askChip: (q: string) => void
  canComplete: boolean
  completeCheck: () => void
}

function banner(phase: Phase, runOutput: string, targetFile: string | undefined, _testCommand: string | undefined) {
  const base = { padding: '9px 16px', fontFamily: mono, fontSize: 11.5, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }
  if (phase === 'creating')
    return {
      label: '◴ Creating sandbox…',
      css: { ...base, color: 'var(--mut)', background: '#1a1813' },
      out: 'Provisioning temp dir, applying curated mutation, validating the check fails…',
    }
  if (phase === 'running') return { label: '◴ Running pytest…', css: { ...base, color: 'var(--mut)', background: '#1a1813' }, out: runOutput || '' }
  if (phase === 'fail')
    return {
      label: '✕ check failed',
      css: { ...base, color: 'var(--red)', background: 'rgba(217,106,94,0.10)', borderBottom: '1px solid rgba(217,106,94,0.25)' },
      out: runOutput,
    }
  if (phase === 'pass')
    return {
      label: '✓ check passed',
      css: { ...base, color: 'var(--green)', background: 'rgba(95,176,126,0.10)', borderBottom: '1px solid rgba(95,176,126,0.25)' },
      out: runOutput,
    }
  if (phase === 'error')
    return {
      label: '⚠ runner error',
      css: { ...base, color: 'var(--red)', background: 'rgba(217,106,94,0.10)', borderBottom: '1px solid rgba(217,106,94,0.25)' },
      out: runOutput,
    }
  return {
    label: 'No checks run yet',
    css: { ...base, color: 'var(--faint)', background: '#1a1813' },
    out: `Edit ${targetFile || 'the target file'}, then Run checks. Behavior must go green on exit code 0.`,
  }
}

export default function Workspace({
  topic,
  check,
  taskW,
  coachW,
  dragTask,
  dragCoach,
  files,
  activeFile,
  setActiveFile,
  code,
  roContent,
  onCode,
  phase,
  running,
  pseudocodeRunning,
  pseudocodeMode,
  runOutput,
  runChecks,
  addPseudocodeComments,
  thread,
  coachInput,
  coachProvider,
  onCoachProvider,
  onCoachInput,
  onCoachKey,
  sendCoach,
  askChip,
  canComplete,
  completeCheck,
}: WorkspaceProps) {
  const targetFile = check?.target_file
  const af = (files || []).find((f) => f.path === activeFile)
  const editable = !!af?.editable
  const roText = editable ? '' : (activeFile ? roContent[activeFile] || '' : '')
  const lineNos = (code || '').split('\n').map((_: string, i: number) => i + 1)
  const roLineNos = roText.split('\n').map((_: string, i: number) => i + 1)
  const b = banner(phase, runOutput, targetFile, check?.test_command)
  const [editorScroll, setEditorScroll] = useState({ top: 0, left: 0 })

  const testFile = (files || []).find((f) => !f.editable)
  const testContent = testFile ? roContent[testFile.path] || '' : ''
  const failingTest = (testContent.match(/def\s+(test_\w+)/) || [])[1] || (testFile ? testFile.name : '—')
  const invariant = topic?.current_revision?.invariant

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
        <div className="lg-scroll" style={{ width: taskW, flex: 'none', borderRight: '1px solid var(--bd)', background: 'var(--panel)', overflow: 'auto', padding: '18px' }}>
          <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 14 }}>Task</div>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontFamily: mono,
              fontSize: 10.5,
              color: phase === 'pass' ? 'var(--green)' : 'var(--red)',
              border: `1px solid ${phase === 'pass' ? 'rgba(95,176,126,0.3)' : 'rgba(217,106,94,0.3)'}`,
              background: phase === 'pass' ? 'rgba(95,176,126,0.08)' : 'rgba(217,106,94,0.08)',
              padding: '3px 8px',
              borderRadius: 5,
              marginBottom: 14,
            }}
          >
            ● {phase === 'pass' ? 'behavior restored' : 'behavior failing'}
          </div>
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 10px', letterSpacing: '-0.01em' }}>{topic?.title || 'Ownership check'}</h2>
          <p style={{ fontSize: 13, color: 'var(--mut)', lineHeight: 1.6, margin: '0 0 16px' }}>{topic?.summary}</p>
          <div style={{ borderTop: '1px solid var(--bd)', paddingTop: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--faint)', marginBottom: 6 }}>Failing test</div>
            <div style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--tx)', wordBreak: 'break-all' }}>{failingTest}</div>
          </div>
          {invariant && (
            <div style={{ borderTop: '1px solid var(--bd)', paddingTop: 14, marginTop: 14 }}>
              <div style={{ fontSize: 11, color: 'var(--faint)', marginBottom: 6 }}>Invariant to restore</div>
              <div style={{ fontSize: 12.5, color: 'var(--mut)', lineHeight: 1.55 }}>{invariant}</div>
            </div>
          )}
        </div>
        <div className="lg-resize" onMouseDown={dragTask} title="Drag to resize" style={resizeStyle} />

        {/* SANDBOX */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg)' }}>
          <div style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
            {/* file tree */}
            <div style={{ width: 184, flex: 'none', borderRight: '1px solid var(--bd)', background: 'var(--panel)', padding: '12px 8px', overflow: 'auto' }}>
              <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--faint)', padding: '4px 8px 10px' }}>Sandbox</div>
              {(files || []).map((f) => (
                <div
                  key={f.path}
                  onClick={() => setActiveFile(f.path)}
                  title={f.path}
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
                    ...(activeFile === f.path ? { background: 'var(--panel2)', color: 'var(--tx)' } : { color: 'var(--mut)' }),
                  }}
                >
                  <span style={{ opacity: 0.7 }}>{f.editable ? '■' : '□'}</span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                  {f.modified && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', flex: 'none' }} />}
                </div>
              ))}
            </div>

            {/* editor + output */}
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div style={{ flex: 'none', height: 38, borderBottom: '1px solid var(--bd)', background: 'var(--panel)', display: 'flex', alignItems: 'center', gap: 8, padding: '0 14px', fontFamily: mono, fontSize: 11.5, color: 'var(--mut)' }}>
                <span style={{ opacity: 0.7 }}>▾</span>
                {af?.name || activeFile || '—'}
                {editable && (
                  <button
                    onClick={addPseudocodeComments}
                    disabled={pseudocodeRunning}
                    style={{
                      marginLeft: 'auto',
                      fontFamily: mono,
                      fontSize: 10.5,
                      color: pseudocodeRunning ? 'var(--faint)' : 'var(--accent)',
                      background: pseudocodeRunning ? 'rgba(255,255,255,0.03)' : 'rgba(200,116,77,0.08)',
                      border: '1px solid rgba(200,116,77,0.28)',
                      borderRadius: 6,
                      padding: '4px 8px',
                      cursor: pseudocodeRunning ? 'default' : 'pointer',
                    }}
                  >
                    {pseudocodeRunning ? (pseudocodeMode === 'prints' ? 'asking coach…' : 'typing hints…') : pseudocodeMode === 'prints' ? 'Ask coach about prints' : 'Add pseudocode hints'}
                  </button>
                )}
                {!editable && activeFile && (
                  <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--faint)', border: '1px solid var(--bd2)', padding: '1px 6px', borderRadius: 4 }}>read-only</span>
                )}
              </div>

              {editable ? (
                <div style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden', background: '#141310', position: 'relative' }}>
                  <div style={{ flex: 'none', width: 46, overflow: 'hidden', fontFamily: mono, fontSize: 13, lineHeight: '21px', color: '#46423a', userSelect: 'none', background: '#141310' }}>
                    <div style={{ padding: '14px 0', textAlign: 'right', transform: `translateY(${-editorScroll.top}px)` }}>
                      {lineNos.map((n: number) => (
                        <div key={n} style={{ paddingRight: 12 }}>
                          {n}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div style={{ flex: 1, minWidth: 0, position: 'relative', overflow: 'hidden' }}>
                    <pre
                      style={{
                        position: 'absolute',
                        inset: 0,
                        margin: 0,
                        padding: '14px 16px',
                        fontFamily: mono,
                        fontSize: 13,
                        lineHeight: '21px',
                        whiteSpace: 'pre',
                        pointerEvents: 'none',
                        minWidth: 'max-content',
                        minHeight: '100%',
                        transform: `translate(${-editorScroll.left}px, ${-editorScroll.top}px)`,
                      }}
                    >
                      {hl(code, false)}
                    </pre>
                    <textarea
                      className="lg-scroll"
                      spellCheck="false"
                      value={code}
                      onChange={onCode}
                      onScroll={(e) => setEditorScroll({ top: e.currentTarget.scrollTop, left: e.currentTarget.scrollLeft })}
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
                  <pre style={{ margin: 0, padding: '14px 16px', fontFamily: mono, fontSize: 13, lineHeight: '21px', whiteSpace: 'pre', color: 'var(--mut)' }}>{hl(roText, true)}</pre>
                </div>
              )}

              {/* run bar */}
              <div style={{ flex: 'none', borderTop: '1px solid var(--bd)', background: 'var(--panel)', padding: '11px 16px', display: 'flex', alignItems: 'center', gap: 14 }}>
                <button onClick={runChecks} disabled={running} style={runBtnStyle}>
                  {running && <span style={{ width: 11, height: 11, border: '2px solid rgba(28,20,15,0.35)', borderTopColor: '#1c140f', borderRadius: '50%', display: 'inline-block', animation: 'spin 0.7s linear infinite' }} />}
                  {running ? 'Running…' : 'Run checks'}
                </button>
                <div style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--faint)' }}>exit code is the oracle · {check?.test_command || 'pytest'}</div>
              </div>

              {/* output */}
              <div className="lg-scroll" style={{ flex: 'none', height: 200, borderTop: '1px solid var(--bd)', background: '#121110', overflow: 'auto' }}>
                <div style={b.css}>{b.label}</div>
                <pre style={{ margin: 0, padding: '12px 16px', fontFamily: mono, fontSize: 11.5, lineHeight: 1.65, color: 'var(--mut)', whiteSpace: 'pre-wrap' }}>{b.out}</pre>
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
              <span style={{ marginLeft: 'auto', fontFamily: mono, fontSize: 10, color: 'var(--faint)', border: '1px solid var(--bd2)', padding: '2px 7px', borderRadius: 5 }}>claude -p · tools denied</span>
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--mut)', marginTop: 6 }}>Conceptual help only. The coach can't see your code or the fix — by design.</div>
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
              const refusal = WITHHELD.test(m.text || '')
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
                  {renderCoach(m.text)}
                </div>
              )
            })}
          </div>

          <div style={{ flex: 'none', borderTop: '1px solid var(--bd)', background: 'var(--panel)', padding: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <select
                value={coachProvider}
                onChange={(e) => onCoachProvider(e.target.value as 'claude-code' | 'codex-exec')}
                style={{ background: 'var(--bg)', border: '1px solid var(--bd2)', color: 'var(--tx)', borderRadius: 8, padding: '7px 9px', fontFamily: "'Geist', sans-serif", fontSize: 12.5, outline: 'none' }}
              >
                <option value="claude-code">Claude</option>
                <option value="codex-exec">Codex</option>
              </select>
            </div>
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
