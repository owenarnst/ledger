// Issue #4 — App shell. Holds the demo state machine and routes between the
// three screens. Data is live now: topics, receipts, sandbox files, runs, and
// coaching all come from the FastAPI backend (src/api.js). The persistent rail +
// breadcrumb live here. State-based navigation; react-router can replace it to
// match the SessionStart nudge URL shape (#10) later.
import { useCallback, useEffect, useRef, useState } from 'react'
import Dashboard from './screens/Dashboard'
import Topic from './screens/Topic'
import Workspace from './screens/Workspace'
import * as api from './api'
import { toCards, isActionable, testPathFor, Card } from './adapt'

const mono = "'JetBrains Mono', monospace"

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

interface RailProps {
  projectName: string
  topicCount: number
  readyCount: number
}

function Rail({ projectName, topicCount, readyCount }: RailProps) {
  const label = () => ({
    fontFamily: mono,
    fontSize: 10.5,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--faint)',
    padding: '8px 6px 6px',
  })
  const readyLabel = `${readyCount} ${readyCount === 1 ? 'check' : 'checks'} ready`
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
            <div style={{ fontWeight: 500, fontSize: 13.5 }}>{projectName || '—'}</div>
            <div style={{ fontSize: 11.5, color: 'var(--mut)', marginTop: 2 }}>
              {topicCount} topics · {readyLabel}
            </div>
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

interface TopBarProps {
  projectName: string
  crumbTopic?: string
  isWorkspace: boolean
  statsLabel: string
  onExit: () => void
}

function TopBar({ projectName, crumbTopic, isWorkspace, statsLabel, onExit }: TopBarProps) {
  return (
    <div style={{ height: 52, flex: 'none', borderBottom: '1px solid var(--bd)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 22px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 13 }}>
        <span style={{ color: 'var(--faint)' }}>Ledger</span>
        <span style={{ color: 'var(--faint)', fontSize: 11 }}>›</span>
        <span style={{ color: 'var(--tx)', fontWeight: 500 }}>{projectName || '—'}</span>
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

interface CenterNoteProps {
  children: React.ReactNode
  tone?: 'error'
}

function CenterNote({ children, tone }: CenterNoteProps) {
  const color = tone === 'error' ? 'var(--red)' : 'var(--mut)'
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40 }}>
      <div style={{ maxWidth: 560, textAlign: 'center', color, fontSize: 13.5, lineHeight: 1.6, fontFamily: mono }}>{children}</div>
    </div>
  )
}

type Screen = 'dashboard' | 'topic' | 'workspace'
type Phase = 'idle' | 'creating' | 'running' | 'fail' | 'pass' | 'error'

interface FileItem {
  path: string
  name: string | undefined
  editable: boolean
  modified?: boolean
}

interface ThreadMessage {
  role: 'user' | 'coach' | 'thinking'
  text?: string
}

interface HistStats {
  elapsed: string
  runs: number
  concept: number
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('dashboard')
  const [project, setProject] = useState<api.Project | null>(null)
  const [cards, setCards] = useState<Card[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [topicDetail, setTopicDetail] = useState<api.TopicDetail | null>(null)
  const [check, setCheck] = useState<api.Check | null>(null)
  const [activeFile, setActiveFile] = useState<string | null>(null)
  const [files, setFiles] = useState<FileItem[]>([])
  const [code, setCode] = useState('')
  const [roContent, setRoContent] = useState<Record<string, string>>({})

  const [running, setRunning] = useState(false)
  const [pseudocodeRunning, setPseudocodeRunning] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [runOutput, setRunOutput] = useState('')
  const [runs, setRuns] = useState(0)
  const [elapsedMin, setElapsedMin] = useState(0)

  const [thread, setThread] = useState<ThreadMessage[]>([])
  const [coachInput, setCoachInput] = useState('')
  const [coachProvider, setCoachProvider] = useState<'claude-code' | 'codex-exec'>('claude-code')
  const [histStats, setHistStats] = useState<HistStats | null>(null)
  const [showLog, setShowLog] = useState(false)

  const [taskW, setTaskW] = useState(280)
  const [coachW, setCoachW] = useState(372)

  const startTsRef = useRef(0)
  const codeRef = useRef('')

  useEffect(() => {
    codeRef.current = code
  }, [code])

  // initial load: project + topics
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [projects, topics] = await Promise.all([api.listProjects(), api.listTopics()])
        if (!alive) return
        setProject(projects[0] || null)
        setCards(toCards(topics))
      } catch (e) {
        if (alive) setLoadError(e instanceof Error ? e.message : String(e))
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  // restore persisted pane widths
  useEffect(() => {
    try {
      const tw = parseInt(localStorage.getItem('lg_taskW') || '280', 10)
      const cw = parseInt(localStorage.getItem('lg_coachW') || '372', 10)
      if (!isNaN(tw)) setTaskW(Math.min(460, Math.max(210, tw)))
      if (!isNaN(cw)) setCoachW(Math.min(620, Math.max(300, cw)))
    } catch (_) {}
  }, [])

  // ---- navigation ----
  const openTopic = useCallback(async (card: Card) => {
    setShowLog(false)
    try {
      const detail = await api.getTopic(card.id)
      setTopicDetail(detail)
      setScreen('topic')
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  const backToWorklist = useCallback(() => setScreen('dashboard'), [])
  const toggleLog = useCallback(() => setShowLog((v) => !v), [])
  const exitCheck = useCallback(() => setScreen('topic'), [])

  // ---- check lifecycle ----
  const startCheck = useCallback(async () => {
    if (!topicDetail) return
    setScreen('workspace')
    setPhase('creating')
    setRunning(false)
    setRuns(0)
    setElapsedMin(0)
    setThread([])
    setCoachInput('')
    setRunOutput('')
    setFiles([])
    setCode('')
    setRoContent({})
    startTsRef.current = Date.now()
    try {
      const created = await api.createCheck(topicDetail.id)
      setCheck(created)
      const targetPath = created.target_file
      const targetFile = await api.readFile(created.id, targetPath)
      codeRef.current = targetFile.content
      setCode(targetFile.content)
      setActiveFile(targetPath)

      const fileList = [{ path: targetPath, name: targetPath.split('/').pop(), editable: true, modified: true }]
      const testPath = testPathFor(targetPath)
      if (testPath) {
        try {
          const testFile = await api.readFile(created.id, testPath)
          setRoContent((m) => ({ ...m, [testPath]: testFile.content }))
          fileList.push({ path: testPath, name: testPath.split('/').pop(), editable: false, modified: false })
        } catch (_) {
          /* no companion test file — editor still works with the target alone */
        }
      }
      setFiles(fileList)
      setPhase('idle')
    } catch (e) {
      setRunOutput(`Could not create sandbox: ${e instanceof Error ? e.message : String(e)}`)
      setPhase('error')
    }
  }, [topicDetail])

  const onCode = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const v = e.target.value
    codeRef.current = v
    setCode(v)
    setPhase((p) => (p === 'pass' || p === 'fail' ? 'idle' : p))
  }, [])

  const typeInsertedCommentLines = useCallback(async (target: string) => {
    const original = codeRef.current
    const originalLines = original.split('\n')
    const targetLines = target.split('\n')
    const displayLines = originalLines.slice()
    let originalIndex = 0
    let inserted = 0

    for (const targetLine of targetLines) {
      if (originalIndex < originalLines.length && targetLine === originalLines[originalIndex]) {
        originalIndex += 1
        continue
      }

      if (originalIndex < originalLines.length && targetLine.startsWith(originalLines[originalIndex])) {
        const replaceAt = originalIndex + inserted
        const base = originalLines[originalIndex]
        for (let i = base.length; i <= targetLine.length; i += 4) {
          displayLines[replaceAt] = targetLine.slice(0, i)
          const next = displayLines.join('\n')
          codeRef.current = next
          setCode(next)
          await sleep(6)
        }
        displayLines[replaceAt] = targetLine
        originalIndex += 1
        continue
      }

      const insertAt = originalIndex + inserted
      displayLines.splice(insertAt, 0, '')
      for (let i = 0; i <= targetLine.length; i += 4) {
        displayLines[insertAt] = targetLine.slice(0, i)
        const next = displayLines.join('\n')
        codeRef.current = next
        setCode(next)
        await sleep(6)
      }
      displayLines[insertAt] = targetLine
      inserted += 1
    }

    codeRef.current = target
    setCode(target)
  }, [])

  const addPseudocodeComments = useCallback(async () => {
    if (!check || !activeFile || running || pseudocodeRunning) return
    const active = files.find((f) => f.path === activeFile)
    if (!active?.editable) return
    setPseudocodeRunning(true)
    try {
      const hasHints = codeRef.current.includes('Plan:')
      if (hasHints) {
        await api.writeFile(check.id, check.target_file, codeRef.current)
        const run = await api.runCheck(check.id)
        const mins = Math.max(1, Math.round((Date.now() - startTsRef.current) / 60000))
        setRunOutput(run.output || '')
        setPhase(run.passed ? 'pass' : 'fail')
        setRuns((n) => n + 1)
        setElapsedMin(mins)
        const question = 'Use the latest test output, especially any printed values, to explain what the print output reveals about the bug. Be concise and do not provide code or a patch.'
        setThread((th) => [...th, { role: 'user', text: 'What does the print output show?' }, { role: 'thinking' }])
        const res = await api.askCoach(check.id, question, coachProvider)
        setThread((th) => {
          const copy = th.slice()
          const i = copy.findIndex((m) => m.role === 'thinking')
          if (i >= 0) copy[i] = { role: 'coach', text: res.response || '' }
          return copy
        })
        return
      } else {
        const result = await api.generatePseudocodeComments(check.id, activeFile)
        if (result.changed) {
          await typeInsertedCommentLines(result.content)
          setFiles((items) => items.map((item) => (item.path === activeFile ? { ...item, modified: true } : item)))
          setPhase((p) => (p === 'pass' || p === 'fail' ? 'idle' : p))
        }
      }
    } catch (e) {
      setRunOutput(`Could not add hints: ${e instanceof Error ? e.message : String(e)}`)
      setPhase('error')
    } finally {
      setPseudocodeRunning(false)
    }
  }, [activeFile, check, coachProvider, files, pseudocodeRunning, running, typeInsertedCommentLines])

  const runChecks = useCallback(async () => {
    if (running || !check) return
    setRunning(true)
    setPhase('running')
    try {
      await api.writeFile(check.id, check.target_file, codeRef.current)
      const result = await api.runCheck(check.id)
      const mins = Math.max(1, Math.round((Date.now() - startTsRef.current) / 60000))
      setRunOutput(result.output || '')
      setPhase(result.passed ? 'pass' : 'fail')
      setRuns((n) => n + 1)
      setElapsedMin(mins)
    } catch (e) {
      setRunOutput(`Check runner error: ${e instanceof Error ? e.message : String(e)}`)
      setPhase('error')
    } finally {
      setRunning(false)
    }
  }, [running, check])

  // ---- coach ----
  const pushCoach = useCallback(
    async (text: string) => {
      const t = (text || '').trim()
      if (!t || !check) return
      setThread((th) => [...th, { role: 'user', text: t }, { role: 'thinking' }])
      setCoachInput('')
      try {
        const res = await api.askCoach(check.id, t, coachProvider)
        setThread((th) => {
          const copy = th.slice()
          const i = copy.findIndex((m) => m.role === 'thinking')
          if (i >= 0) copy[i] = { role: 'coach', text: res.response || '' }
          return copy
        })
      } catch (e) {
        setThread((th) => {
          const copy = th.slice()
          const i = copy.findIndex((m) => m.role === 'thinking')
          if (i >= 0) copy[i] = { role: 'coach', text: `Coach unavailable: ${e instanceof Error ? e.message : String(e)}` }
          return copy
        })
      }
    },
    [check, coachProvider],
  )

  const sendCoach = useCallback(() => pushCoach(coachInput), [pushCoach, coachInput])
  const onCoachInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => setCoachInput(e.target.value), [])
  const onCoachKey = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        pushCoach(e.currentTarget.value)
      }
    },
    [pushCoach],
  )

  const completeCheck = useCallback(async () => {
    if (!check) return
    const conceptAsked = thread.filter((m) => m.role === 'user').length
    const secs = Math.max(40, Math.round((Date.now() - startTsRef.current) / 1000))
    const mm = Math.floor(secs / 60)
    const ss = secs % 60
    setHistStats({ elapsed: (mm > 0 ? mm + 'm ' : '') + ss + 's', runs, concept: conceptAsked })
    try {
      await api.completeCheck(check.id)
      const detail = await api.getTopic(check.topic_id)
      setTopicDetail(detail)
      setCards((cs) => cs.map((c) => (c.id === detail.id ? { ...c, badge: 'practiced', badgeLabel: 'Practiced', faint: true } : c)))
    } catch (_) {
      /* keep the local practiced view even if the persist call fails */
    }
    setScreen('topic')
  }, [check, thread, runs])

  // ---- drag-resize ----
  const startDrag = useCallback(
    (which: 'task' | 'coach') => (e: React.MouseEvent) => {
      e.preventDefault()
      const startX = e.clientX
      const start = which === 'task' ? taskW : coachW
      let latest = start
      const move = (ev: MouseEvent) => {
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
    },
    [taskW, coachW],
  )

  // ---- derive ----
  const readyCount = cards.filter((c) => isActionable(c.raw.state)).length
  const projectName = project?.name || ''
  const heroPracticed = topicDetail?.state === 'practiced'
  const showRail = screen !== 'workspace'
  const crumbTopic =
    screen === 'topic' && topicDetail
      ? topicDetail.title
      : screen === 'workspace' && topicDetail
        ? `${topicDetail.title} › check`
        : ''
  const statsLabel = `${runs}${runs === 1 ? ' run' : ' runs'} · ${elapsedMin}m`

  return (
    <div style={{ height: '100vh', width: '100%', display: 'flex', overflow: 'hidden', background: 'var(--bg)', color: 'var(--tx)' }}>
      {showRail && <Rail projectName={projectName} topicCount={cards.length} readyCount={readyCount} />}

      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <TopBar projectName={projectName} crumbTopic={crumbTopic} isWorkspace={screen === 'workspace'} statsLabel={statsLabel} onExit={exitCheck} />

        {loadError && screen === 'dashboard' && (
          <CenterNote tone="error">
            Couldn’t reach the Ledger backend.
            <br />
            <span style={{ color: 'var(--faint)' }}>{loadError}</span>
            <br />
            <br />
            Start it with <span style={{ color: 'var(--tx)' }}>uvicorn backend.api:app --port 8000</span>.
          </CenterNote>
        )}

        {!loadError && loading && screen === 'dashboard' && <CenterNote>Loading worklist…</CenterNote>}

        {!loadError && !loading && screen === 'dashboard' && <Dashboard topics={cards} onOpen={openTopic} />}

        {screen === 'topic' && topicDetail && (
          <Topic
            detail={topicDetail}
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
            topic={topicDetail}
            check={check}
            taskW={taskW}
            coachW={coachW}
            dragTask={startDrag('task')}
            dragCoach={startDrag('coach')}
            files={files}
            activeFile={activeFile}
            setActiveFile={setActiveFile}
            code={code}
            roContent={roContent}
            onCode={onCode}
            phase={phase}
            running={running}
            pseudocodeRunning={pseudocodeRunning}
            pseudocodeMode={code.includes('Plan:') ? 'prints' : 'hints'}
            runOutput={runOutput}
            runChecks={runChecks}
            addPseudocodeComments={addPseudocodeComments}
            thread={thread}
            coachInput={coachInput}
            coachProvider={coachProvider}
            onCoachProvider={setCoachProvider}
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
