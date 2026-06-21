// Backend API client. All paths are relative ('/api/...'): in dev the Vite
// proxy forwards them to the FastAPI server on :8000; in the packaged demo
// FastAPI serves this bundle, so the same paths are same-origin.

interface RequestOptions {
  method?: string
  body?: any
}

async function req<T>(path: string, { method = 'GET', body }: RequestOptions = {}): Promise<T> {
  const hasBody = body !== undefined
  const res = await fetch(path, {
    method,
    headers: hasBody ? { 'Content-Type': 'application/json' } : undefined,
    body: hasBody ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j.detail || detail
    } catch (_) {}
    const err = new Error(`${res.status} ${detail}`)
    ;(err as any).status = res.status
    throw err
  }
  if (res.status === 204) return null as T
  return res.json()
}

// File paths (e.g. "retrieval/rerank.py") are intentionally NOT encoded — the
// backend route is declared as {file_path:path} and expects the slashes intact.
const cid = (id: string) => encodeURIComponent(id)

export interface Project {
  name: string
  slug: string
  is_demo?: number
}

export interface Topic {
  id: string
  title: string
  state: string
  risk_class: string
  caller_count: number
  claude_authored: boolean
  provider: string
  why_now?: string
  // Derived display facts the backend computes (ADR-0002 / #22) — never analyst
  // claims. ownership_status comes from the persisted lifecycle; impact_level is
  // the analyst value or a risk-class fallback; evidence_summary is built from the
  // accepted Code-anchor / Development-trace counts (e.g. "4 code anchors · 1
  // related Claude session").
  ownership_status: string
  impact_level: string
  evidence_summary: string
}

// One addressable unit of an agent session — a user prompt or a tool call. The
// analyst-cited, server-verified "prompt + tool-call hunk" the Agent trace renders.
export interface TraceSegment {
  kind: 'prompt' | 'tool_call' | string
  text?: string
  tool?: string | null
  target?: string | null
}

// One immutable Evidence record grounding a Topic. Code anchors carry no provider;
// agent traces carry a Provider tag plus session/confidence provenance and the
// verified prompt + tool-call segments.
export interface EvidenceRecord {
  kind: string
  title?: string
  body?: string
  provider?: string
  tool_sequence?: string[]
  segments?: TraceSegment[]
  source_path?: string | null
  session_id?: string | null
  link_confidence?: string | null
  // Short analyst relevance statement and the deterministic excerpt hash, both
  // verified server-side before the record is persisted (#22).
  relevance?: string | null
  excerpt_sha?: string | null
}

export interface TopicDetail extends Topic {
  summary?: string
  // The maintenance-failure consequence behind the impact level (Topic page →
  // "Why it matters"). Not a numeric score.
  impact_consequence?: string
  evidence: EvidenceRecord[]
  // Backend-grouped Evidence for the expanded view's two provider-neutral groups.
  code_anchors: EvidenceRecord[]
  development_traces: EvidenceRecord[]
  current_revision?: {
    code_path: string
    invariant: string
    commit_sha?: string
  }
}

export type Difficulty = 'easy' | 'medium' | 'hard'

export interface ExerciseQuestion {
  id: string
  kind: 'concept' | 'debugging'
  prompt: string
  choices: string[]
}

export interface ExerciseStep {
  type: 'multiple_choice' | 'sandbox'
  question_id?: string
}

export interface ExercisePlan {
  difficulty: Difficulty
  template_id: string
  steps: ExerciseStep[]
  questions: ExerciseQuestion[]
}

export interface Check {
  id: string
  topic_id: string
  target_file: string
  test_command: string
  difficulty: Difficulty
  template_id: string
  plan: ExercisePlan
}

export interface FileContent {
  content: string
}

export interface CheckResult {
  output: string
  passed: boolean
}

// The coach is Claude-only; `model` echoes which Claude model answered (haiku |
// sonnet | opus). See ADR-0004.
export type CoachModel = 'haiku' | 'sonnet' | 'opus'

export interface CoachResponse {
  response: string
  model?: CoachModel
}

export interface PseudocodeCommentsResponse {
  content: string
  comment_count: number
  changed: boolean
}

export interface AnswerResult {
  question_id: string
  selected_index: number | null
  correct: boolean
  rationale: string
}

export interface SubmitAnswersResponse {
  passed: boolean
  results: AnswerResult[]
}

export interface Reflection {
  invariant: string
  rationale: string
  future_risk: string
}

export const listProjects = () => req<Project[]>('/api/projects')
export const listTopics = () => req<Topic[]>('/api/topics')
export const listProjectTopics = (slug: string) => req<Topic[]>(`/api/projects/${cid(slug)}/topics`)
export const getTopic = (id: string) => req<TopicDetail>(`/api/topics/${cid(id)}`)
export const createCheck = (topicId: string, difficulty: Difficulty = 'hard') =>
  req<Check>(`/api/topics/${cid(topicId)}/checks`, { method: 'POST', body: { difficulty } })
export const getCheck = (checkId: string) => req<Check>(`/api/checks/${cid(checkId)}`)
export const readFile = (checkId: string, filePath: string) => req<FileContent>(`/api/checks/${cid(checkId)}/files/${filePath}`)
export const writeFile = (checkId: string, filePath: string, content: string) =>
  req<void>(`/api/checks/${cid(checkId)}/files/${filePath}`, { method: 'PUT', body: { content } })
export const runCheck = (checkId: string) => req<CheckResult>(`/api/checks/${cid(checkId)}/run`, { method: 'POST' })
export const askCoach = (checkId: string, question: string, model?: CoachModel) =>
  req<CoachResponse>(`/api/checks/${cid(checkId)}/coach`, { method: 'POST', body: { question, model } })
export const generatePseudocodeComments = (checkId: string, filePath: string) =>
  req<PseudocodeCommentsResponse>(`/api/checks/${cid(checkId)}/pseudocode-comments`, { method: 'POST', body: { file_path: filePath } })
export const submitAnswers = (checkId: string, answers: Record<string, number>) =>
  req<SubmitAnswersResponse>(`/api/checks/${cid(checkId)}/answers`, { method: 'POST', body: { answers } })
export const completeCheck = (checkId: string, reflection?: Reflection) =>
  req<void>(`/api/checks/${cid(checkId)}/complete`, { method: 'POST', body: reflection ? { reflection } : {} })
