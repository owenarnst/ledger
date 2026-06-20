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
}

export interface TopicDetail extends Topic {
  summary?: string
  evidence: Array<{
    kind: string
    title?: string
    body?: string
    provider?: string
    tool_sequence?: string[]
    source_path?: string | null
    session_id?: string | null
    link_confidence?: string | null
  }>
  current_revision?: {
    code_path: string
    invariant: string
    commit_sha?: string
  }
}

export interface Check {
  id: string
  topic_id: string
  target_file: string
  test_command: string
}

export interface FileContent {
  content: string
}

export interface CheckResult {
  output: string
  passed: boolean
}

export interface CoachResponse {
  response: string
}

export interface Reflection {
  invariant: string
  rationale: string
  future_risk: string
}

export const listProjects = () => req<Project[]>('/api/projects')
export const listTopics = () => req<Topic[]>('/api/topics')
export const getTopic = (id: string) => req<TopicDetail>(`/api/topics/${cid(id)}`)
export const createCheck = (topicId: string) => req<Check>(`/api/topics/${cid(topicId)}/checks`, { method: 'POST' })
export const getCheck = (checkId: string) => req<Check>(`/api/checks/${cid(checkId)}`)
export const readFile = (checkId: string, filePath: string) => req<FileContent>(`/api/checks/${cid(checkId)}/files/${filePath}`)
export const writeFile = (checkId: string, filePath: string, content: string) =>
  req<void>(`/api/checks/${cid(checkId)}/files/${filePath}`, { method: 'PUT', body: { content } })
export const runCheck = (checkId: string) => req<CheckResult>(`/api/checks/${cid(checkId)}/run`, { method: 'POST' })
export const askCoach = (checkId: string, question: string) =>
  req<CoachResponse>(`/api/checks/${cid(checkId)}/coach`, { method: 'POST', body: { question } })
export const completeCheck = (checkId: string, reflection?: Reflection) =>
  req<void>(`/api/checks/${cid(checkId)}/complete`, { method: 'POST', body: reflection ? { reflection } : {} })
