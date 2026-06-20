// Issue #4 — App shell. Holds the demo state machine (ported from the design's
// DCLogic class) and routes between the three screens. The persistent rail +
// breadcrumb live here. State-based navigation now; react-router can replace it
// to match the SessionStart nudge URL shape (#10) when the API is wired.
import React, { useCallback, useEffect, useRef, useState } from 'react'
import Dashboard from './screens/Dashboard.jsx'
import Topic from './screens/Topic.jsx'
import Workspace from './screens/Workspace.jsx'
import { MUTATED, TOPICS_RAW, coachReply } from './fixtures.js'

const mono = "'JetBrains Mono', monospace"
const SHOW_MEMORY_BEAT = true

function Rail({ topicCount }) {
  const label = (txt) => ({
    fontFamily: mono,
    fontSize: 10.5,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--faint)',
    padding: '8px 6px 6px',
  })
  return (
    <aside style={{ width: 248, flex: 'none', borderRight: '1px solid var(--bd)', background: 'var(--panel)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '18px 18px 16px' }}>
        <div style={{ width: 26, height: 26, borderRadius: 7, background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <path d="M3 3.2h10M3 6.4h10M3 9.6h7M3 12.8h10" stroke="#1c140f" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </div>
        <div style={{ fontWeight: 600, fontSize: 15, letterSpacing: '-0.01em' }}>Ledger</div>
      </div>

      <div style={{ padding: '6px 14px 8px' }}>
        <div style={label()}>Tracked repos</div>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '9px 10px', borderRadius: 8, background: 'var(--panel2)', border: '1px solid var(--bd2)' }}>
          <div style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--accent)', marginTop: 6, flex: 'none' }} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 500, fontSize: 13.5 }}>rag-pilot</div>
            <div style={{ fontSize: 11.5, color: 'var(--mut)', marginTop: 2 }}>{topicCount} topics · 1 check ready</div>
          </div>
        </div>
      </div>

      <div style={{ padding: '2px 14px 8px' }}>
        <div style={label()}>Log sources</div>
        {[
          { name: 'Codex', path: '~/.codex/sessions' },
          { name: 'Claude Code', path: '~/.claude' },
        ].map((s) => (
          <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '7px 10px' }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', flex: 'none' }} />
            <span style={{ fontSize: 13 }}>{s.name}</span>
            <span style={{ marginLeft: 'auto', fontFamily: mono, fontSize: 10, color: 'var(--faint)' }}>{s.path}</span>
          </div>
        ))}
      </div>

      <div style={{ flex: 1 }} />

      <div style={{ margin: 14, padding: '13px', border: '1px dashed var(--bd2)', borderRadius: 9, background: 'rgba(255,255,255,0.012)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: 'var(--mut)', fontSize: 11, fontFamily: mono, marginBottom: 6 }}>
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="6.2" stroke="currentColor" strokeWidth="1.3" />
            <path d="M8 5.2v3.4M8 10.6h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
          AUTO-DISCOVERY
        </div>
        <div style={{ fontSize: 12, color: 'var(--mut)', lineHeight: 1.5 }}>
          Decisions appear here automatically from the Codex and Claude Code logs already on your machine.
        </div>
      </div>
    </aside>
  )
}

function TopBar({ crumbTopic, isWorkspace, statsLabel, onExit }) {
  return (
    <div style={{ height: 52, flex: 'none', borderBottom: '1px solid var(--bd)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 22px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 13 }}>
        <span style={{ color: 'var(--faint)' }}>Ledger</span>
        <span style={{ color: 'var(--faint)', fontSize: 11 }}>›</span>
        <span style={{ color: 'var(--tx)', fontWeight: 500 }}>rag-pilot</span>
        {crumbTopic && (
          <>
            <span style={{ color: 'var(--faint)', fontSize: 11 }}>›</span>
            <span style={{ color: 'var(--mut)' }}>{crumbTopic}</span>
          </>
        )}
      </div>
      {isWorkspace && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ fontFamily: mono, fontSize: 11.5, color: 'var(--mut)' }}>{statsLabel}</div>
          <div className="lg-hover-exit" onClick={onExit} style={{ fontSize: 12.5, color: 'var(--mut)', cursor: 'pointer', padding: '5px 10px', border: '1px solid var(--bd2)', borderRadius: 7 }}>
            Exit check
          </div>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [screen, setScreen] = useState('dashboard')
  const [heroPracticed, setHeroPracticed] = useState(false)
  const [activeFile, setActiveFile] = useState('cache.py')
  const [code, setCode] = useState('')
  const [running, setRunning] = useState(false)
  const [phase, setPhase] = useState('idle') // idle | creating | running | fail | pass
  const [runs, setRuns] = useState(0)
  const [elapsedMin, setElapsedMin] = useState(0)
  const [thread, setThread] = useState([])
  const [coachInput, setCoachInput] = useState('')
  const [histStats, setHistStats] = useState(null)
  const [showLog, setShowLog] = useState(false)
  const [taskW, setTaskW] = useState(280)
  const [coachW, setCoachW] = useState(372)

  const startTsRef = useRef(0)
  const codeRef = useRef('')

  useEffect(() => {
    codeRef.current = code
  }, [code])

  // componentDidMount: restore persisted pane widths
  useEffect(() => {
    try {
      const tw = parseInt(localStorage.getItem('lg_taskW'), 10)
      const cw = parseInt(localStorage.getItem('lg_coachW'), 10)
      if (!isNaN(tw)) setTaskW(Math.min(460, Math.max(210, tw)))
      if (!isNaN(cw)) setCoachW(Math.min(620, Math.max(300, cw)))
    } catch (_) {}
  }, [])

  // ---- navigation ----
  const openTopic = useCallback(() => setScreen('topic'), [])
  const backToWorklist = useCallback(() => setScreen('dashboard'), [])
  const toggleLog = useCallback(() => setShowLog((v) => !v), [])
  const exitCheck = useCallback(() => setScreen('topic'), [])

  const startCheck = useCallback(() => {
    startTsRef.current = Date.now()
    codeRef.current = MUTATED
    setScreen('workspace')
    setActiveFile('cache.py')
    setCode(MUTATED)
    setPhase('creating')
    setRunning(false)
    setRuns(0)
    setElapsedMin(0)
    setThread([])
    setCoachInput('')
    setTimeout(() => setPhase((p) => (p === 'creating' ? 'idle' : p)), 900)
  }, [])

  const onCode = useCallback((e) => {
    const v = e.target.value
    codeRef.current = v
    setCode(v)
    setPhase((p) => (p === 'pass' || p === 'fail' ? 'idle' : p))
  }, [])

  const isFixed = useCallback(() => {
    const m = (codeRef.current || '').match(/parts\s*=\s*\[([^\]]*)\]/)
    return !!(m && /tenant_id/.test(m[1]))
  }, [])

  const runChecks = useCallback(() => {
    setRunning((r) => {
      if (r) return r
      setPhase('running')
      setTimeout(() => {
        const pass = isFixed()
        const mins = Math.max(1, Math.round((Date.now() - startTsRef.current) / 60000))
        setRunning(false)
        setPhase(pass ? 'pass' : 'fail')
        setRuns((n) => n + 1)
        setElapsedMin(mins)
      }, 1100)
      return true
    })
  }, [isFixed])

  // ---- coach ----
  const pushCoach = useCallback((text) => {
    const t = (text || '').trim()
    if (!t) return
    setThread((th) => [...th, { role: 'user', text: t }, { role: 'thinking' }])
    setCoachInput('')
    setTimeout(() => {
      const card = coachReply(t)
      setThread((th) => {
        const copy = th.slice()
        const i = copy.findIndex((m) => m.role === 'thinking')
        if (i >= 0) copy[i] = { role: 'coach', ...card }
        return copy
      })
    }, 1200)
  }, [])

  const sendCoach = useCallback(() => pushCoach(coachInput), [pushCoach, coachInput])
  const onCoachInput = useCallback((e) => setCoachInput(e.target.value), [])
  const onCoachKey = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        pushCoach(e.target.value)
      }
    },
    [pushCoach],
  )

  const completeCheck = useCallback(() => {
    setThread((th) => {
      const conceptAsked = th.filter((m) => m.role === 'user').length
      const secs = Math.max(40, Math.round((Date.now() - startTsRef.current) / 1000))
      const mm = Math.floor(secs / 60)
      const ss = secs % 60
      setHistStats({ elapsed: (mm > 0 ? mm + 'm ' : '') + ss + 's', runs, concept: conceptAsked })
      return th
    })
    setHeroPracticed(true)
    setScreen('topic')
  }, [runs])

  // ---- drag-resize ----
  const startDrag = useCallback((which) => (e) => {
    e.preventDefault()
    const startX = e.clientX
    const start = which === 'task' ? taskW : coachW
    let latest = start
    const move = (ev) => {
      const delta = ev.clientX - startX
      latest = which === 'task' ? Math.min(460, Math.max(210, start + delta)) : Math.min(620, Math.max(300, start - delta))
      if (which === 'task') setTaskW(latest)
      else setCoachW(latest)
    }
    const up = () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      try {
        localStorage.setItem(which === 'task' ? 'lg_taskW' : 'lg_coachW', String(latest))
      } catch (_) {}
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }, [taskW, coachW])

  // ---- derive ----
  const topics = (SHOW_MEMORY_BEAT ? TOPICS_RAW : TOPICS_RAW.filter((t) => !t.memory)).map((t) => ({
    id: t.id,
    title: t.title,
    badge: t.badge,
    badgeLabel: t.badgeLabel,
    isHero: !!t.isHero,
    expanded: !!t.expanded,
    faint: !!t.faint,
    why: t.why || '',
    chips: t.chips,
  }))

  const showRail = screen !== 'workspace'
  const crumbTopic = screen === 'topic' ? 'Tenant isolation' : screen === 'workspace' ? 'Tenant isolation › check' : ''
  const statsLabel = `${runs}${runs === 1 ? ' run' : ' runs'} · ${elapsedMin}m`

  return (
    <div style={{ height: '100vh', width: '100%', display: 'flex', overflow: 'hidden', background: 'var(--bg)', color: 'var(--tx)' }}>
      {showRail && <Rail topicCount={topics.length} />}

      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <TopBar crumbTopic={crumbTopic} isWorkspace={screen === 'workspace'} statsLabel={statsLabel} onExit={exitCheck} />

        {screen === 'dashboard' && <Dashboard topics={topics} onOpen={openTopic} />}

        {screen === 'topic' && (
          <Topic
            heroPracticed={heroPracticed}
            histStats={histStats}
            showLog={showLog}
            onToggleLog={toggleLog}
            onStartCheck={startCheck}
            onBack={backToWorklist}
          />
        )}

        {screen === 'workspace' && (
          <Workspace
            taskW={taskW}
            coachW={coachW}
            dragTask={startDrag('task')}
            dragCoach={startDrag('coach')}
            activeFile={activeFile}
            setActiveFile={setActiveFile}
            code={code}
            onCode={onCode}
            phase={phase}
            running={running}
            runs={runs}
            runChecks={runChecks}
            thread={thread}
            coachInput={coachInput}
            onCoachInput={onCoachInput}
            onCoachKey={onCoachKey}
            sendCoach={sendCoach}
            askChip={pushCoach}
            canComplete={phase === 'pass'}
            completeCheck={completeCheck}
          />
        )}
      </main>
    </div>
  )
}
