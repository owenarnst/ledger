// Backend API client. All paths are relative ('/api/...'): in dev the Vite
// proxy forwards them to the FastAPI server on :8000; in the packaged demo
// FastAPI serves this bundle, so the same paths are same-origin.

async function req(path, { method = 'GET', body } = {}) {
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
    err.status = res.status
    throw err
  }
  if (res.status === 204) return null
  return res.json()
}

// File paths (e.g. "retrieval/rerank.py") are intentionally NOT encoded — the
// backend route is declared as {file_path:path} and expects the slashes intact.
const cid = (id) => encodeURIComponent(id)

export const listProjects = () => req('/api/projects')
export const listTopics = () => req('/api/topics')
export const getTopic = (id) => req(`/api/topics/${cid(id)}`)
export const createCheck = (topicId) => req(`/api/topics/${cid(topicId)}/checks`, { method: 'POST' })
export const getCheck = (checkId) => req(`/api/checks/${cid(checkId)}`)
export const readFile = (checkId, filePath) => req(`/api/checks/${cid(checkId)}/files/${filePath}`)
export const writeFile = (checkId, filePath, content) =>
  req(`/api/checks/${cid(checkId)}/files/${filePath}`, { method: 'PUT', body: { content } })
export const runCheck = (checkId) => req(`/api/checks/${cid(checkId)}/run`, { method: 'POST' })
export const askCoach = (checkId, question) =>
  req(`/api/checks/${cid(checkId)}/coach`, { method: 'POST', body: { question } })
export const completeCheck = (checkId, reflection) =>
  req(`/api/checks/${cid(checkId)}/complete`, { method: 'POST', body: reflection ? { reflection } : {} })
