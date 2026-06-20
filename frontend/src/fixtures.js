// Demo fixtures — ported verbatim from the design. These stand in for the real
// backend (seed API #5, sandbox engine #13, adapters #8/#16, coach #9). Swapping
// to live data means replacing these reads with fetches; the UI is unchanged.

export const COMMITTED = [
  'class RetrievalCache:',
  '    """Caches reranked retrieval results across requests."""',
  '',
  '    def cache_key(self, query, tenant_id, doc_ids):',
  '        parts = [query, tenant_id, *sorted(doc_ids)]',
  '        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()',
  '        return f"ret:{digest}"',
].join('\n')

export const MUTATED = [
  'import hashlib',
  '',
  '',
  'class RetrievalCache:',
  '    """Caches reranked retrieval results across requests."""',
  '',
  '    def __init__(self, store):',
  '        self._store = store',
  '',
  '    def cache_key(self, query, tenant_id, doc_ids):',
  '        parts = [query, *sorted(doc_ids)]',
  '        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()',
  '        return f"ret:{digest}"',
  '',
  '    def get(self, query, tenant_id, doc_ids):',
  '        return self._store.get(self.cache_key(query, tenant_id, doc_ids))',
  '',
  '    def put(self, query, tenant_id, doc_ids, results):',
  '        self._store.set(self.cache_key(query, tenant_id, doc_ids), results)',
].join('\n')

export const TEST = [
  'from ledger_rag.cache import RetrievalCache',
  'from tests.conftest import InMemoryStore',
  '',
  '',
  'def test_cache_key_is_stable():',
  '    cache = RetrievalCache(InMemoryStore())',
  '    k1 = cache.cache_key("q", "acme", ["d1", "d2"])',
  '    k2 = cache.cache_key("q", "acme", ["d2", "d1"])',
  '    assert k1 == k2',
  '',
  '',
  'def test_cache_isolation_between_tenants():',
  '    cache = RetrievalCache(InMemoryStore())',
  '    cache.put("quarterly numbers", "acme", ["d1"], ["ACME-DOC"])',
  '    assert cache.get("quarterly numbers", "globex", ["d1"]) is None',
].join('\n')

export const CONFTEST = [
  'class InMemoryStore:',
  '    def __init__(self):',
  '        self._data = {}',
  '',
  '    def get(self, key):',
  '        return self._data.get(key)',
  '',
  '    def set(self, key, value):',
  '        self._data[key] = value',
].join('\n')

export const OUT_FAIL = [
  'collected 2 items',
  '',
  'tests/test_cache.py::test_cache_key_is_stable PASSED              [ 50%]',
  'tests/test_cache.py::test_cache_isolation_between_tenants FAILED  [100%]',
  '',
  '=========================== FAILURES ===========================',
  '_____________ test_cache_isolation_between_tenants _____________',
  '',
  '    def test_cache_isolation_between_tenants():',
  '        cache = RetrievalCache(InMemoryStore())',
  '        cache.put("quarterly numbers", "acme", ["d1"], ["ACME-DOC"])',
  '>       assert cache.get("quarterly numbers", "globex", ["d1"]) is None',
  "E       AssertionError: assert ['ACME-DOC'] is None",
  '',
  'tests/test_cache.py:14: AssertionError',
  '=================== 1 failed, 1 passed in 0.41s ===================',
].join('\n')

export const OUT_PASS = [
  'collected 2 items',
  '',
  'tests/test_cache.py::test_cache_key_is_stable PASSED              [ 50%]',
  'tests/test_cache.py::test_cache_isolation_between_tenants PASSED  [100%]',
  '',
  '======================= 2 passed in 0.39s =======================',
].join('\n')

export const CODEX_LOG = [
  '{"type":"message","role":"user","content":"add a cache in front of',
  "  the reranker so repeat queries don't re-hit the vector store\"}",
  '{"type":"reasoning","summary":"Cache reranked results keyed by',
  '  query + tenant + document set so hits stay within a caller."}',
  '{"type":"function_call","name":"shell",',
  '  "arguments":{"command":["bash","-lc","cat ledger_rag/cache.py"]}}',
  '{"type":"function_call","name":"apply_patch","arguments":{"input":',
  '  "*** Update File: ledger_rag/cache.py',
  '   + parts = [query, tenant_id, *sorted(doc_ids)]"}}',
  '{"type":"function_call","name":"shell",',
  '  "arguments":{"command":["pytest","-q"]}}',
  '{"type":"function_call_output","output":"2 passed in 0.41s"}',
  '{"type":"token_count","info":{"total":18422}}',
].join('\n')

// Ranked ownership worklist. Order is hand-curated (no ranking engine — product.md).
export const TOPICS_RAW = [
  {
    id: 'tenant',
    title: 'Tenant isolation in document caching',
    badge: 'recommended',
    badgeLabel: 'Check recommended',
    isHero: true,
    expanded: true,
    why:
      "It's on the retrieval path (5 callers), classed tenant-isolation — an irreversible data-exposure risk — Codex authored it, and no rationale was found in ADRs, CONTEXT, or the commit message. You've never practiced it.",
    chips: [
      { label: 'retrieval path · 5 callers', k: 'plain' },
      { label: 'risk: tenant-isolation', k: 'risk' },
      { label: '⬡ Codex-authored', k: 'codex' },
    ],
  },
  {
    id: 'embed',
    title: 'Embedding cache key composition',
    badge: 'changed',
    badgeLabel: 'Code changed since practice',
    memory: true,
    chips: [
      { label: 'ingest path · 4 callers', k: 'plain' },
      { label: 'practiced 18d ago', k: 'plain' },
      { label: '✳ Claude-authored', k: 'claude' },
    ],
  },
  {
    id: 'rerank',
    title: 'Reranker score normalization threshold',
    badge: 'recommended',
    badgeLabel: 'Check recommended',
    chips: [
      { label: 'rerank path · 3 callers', k: 'plain' },
      { label: 'risk: ranking-quality', k: 'risk' },
      { label: '⬡ Codex-authored', k: 'codex' },
    ],
  },
  {
    id: 'retry',
    title: 'Vector store retry & backoff policy',
    badge: 'recommended',
    badgeLabel: 'Check recommended',
    chips: [
      { label: 'query path · 6 callers', k: 'plain' },
      { label: 'risk: availability', k: 'risk' },
    ],
  },
  {
    id: 'chunk',
    title: 'Chunk overlap window size',
    badge: 'recommended',
    badgeLabel: 'Check recommended',
    chips: [
      { label: 'ingest path · 2 callers', k: 'plain' },
      { label: '✳ Claude-authored', k: 'claude' },
    ],
  },
  {
    id: 'hybrid',
    title: 'Hybrid search weight (BM25 vs dense)',
    badge: 'practiced',
    badgeLabel: 'Practiced',
    faint: true,
    chips: [
      { label: 'query path · 4 callers', k: 'plain' },
      { label: 'risk: ranking-quality', k: 'risk' },
    ],
  },
]

// Coach keyword routing — ported verbatim. The real coach (#9) is `claude -p`
// with all tools denied; this canned router mirrors its withhold-the-patch shape.
export function coachReply(input) {
  const s = (input || '').toLowerCase()
  if (/(just tell|give me|the patch|the fix|the answer|what do i change|what should i change|fix it|solve|the solution|the code)/.test(s)) {
    return {
      refusal: true,
      lead: "I can't hand you the patch — locating it is the exercise, and it's the part that actually builds the instinct.",
      diagnostic:
        'List every value that decides whether two cached results may be safely shared. Which of those currently goes into the cache key, and which one is missing?',
    }
  }
  if (/(supposed to|meant to|what does this code|what is this code|what's this code|purpose|intent|what is it doing|high.?level)/.test(s)) {
    return {
      conceptLabel: 'Goal',
      concept:
        'RetrievalCache reuses reranked results so repeat queries skip the vector store. The rule that makes it safe: a cached entry may only ever be served back to the same caller it was computed for.',
      diagnostic: 'Given that rule, what has to be identical about two requests before they are allowed to share a cached result?',
    }
  }
  if (/(tenant|isolation|multi.?tenant|leak|customer)/.test(s)) {
    return {
      conceptLabel: 'Concept',
      concept:
        'Tenant isolation means one customer’s data can never surface in another’s session. A shared cache sits directly across that boundary: if two tenants can compute the same key, a cache hit becomes a data leak.',
      observation:
        'Compare what the test stores for the first tenant with what it reads back for the second — then look at what actually distinguishes those two calls.',
    }
  }
  if (/(cache key|the key|hashing|hash|digest|identity)/.test(s)) {
    return {
      conceptLabel: 'Concept',
      concept:
        'The cache key is the identity of a cached result. Two requests receive the same cached value exactly when they produce the same key — nothing more, nothing less.',
      diagnostic: 'Which request attributes are folded into the key right now, and which attribute is the one that separates one tenant from another?',
    }
  }
  if (/(where|start|begin|how do i|stuck|lost|first|orient)/.test(s)) {
    return {
      diagnostic: 'What is the smallest difference between the two requests in the failing test?',
      observation:
        'Print the cache key produced for each tenant’s request and compare them — if they match, you’ve found the boundary that’s missing.',
    }
  }
  return {
    diagnostic: 'What does the failing assertion expect to get back, and what is it actually getting?',
    observation: 'Trace which inputs reach the cache key for each tenant, and ask which one ought to make their keys differ.',
  }
}
