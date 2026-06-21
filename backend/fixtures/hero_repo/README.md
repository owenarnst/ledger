# Docs Search API

A small multi-tenant document search service. It searches a shared, in-memory
corpus and returns results scoped to a single tenant, with deterministic ranking
and a bounded result window.

## What it does

Each search request runs through a fixed pipeline:

1. **Retrieve** candidate documents from a shared in-memory store by term overlap.
2. **Scope** candidates to the requesting tenant.
3. **Rerank** deterministically by score (ties broken by id).
4. **Cut off** matches below a minimum confidence score.
5. **Deduplicate** repeated chunks.
6. **Pack** the survivors into a bounded context window, preserving rank order.

The tenant is supplied per request via the `X-Tenant-ID` header. A request for
one tenant never returns another tenant's documents.

## Requirements

- Python 3.11+

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the tests

```bash
python -m pytest tests
```

## Run the service

```bash
uvicorn app:app --reload
```

The service starts with a fixed in-memory corpus seeded for tenants `alpha` and
`beta`.

### Health check

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

### Example search

```bash
curl -X POST http://127.0.0.1:8000/search \
  -H "X-Tenant-ID: alpha" \
  -H "Content-Type: application/json" \
  -d '{"query": "refund"}'
```

```json
{
  "tenant_id": "alpha",
  "query": "refund",
  "results": [
    {
      "id": "alpha-billing",
      "score": 0.92,
      "excerpt": "Alpha billing: a refund is issued to the original payment method within five business days."
    }
  ]
}
```

The seeded corpus also has a `beta` document that matches `refund` with a higher
score, but it is never returned to `alpha`. Omitting the `X-Tenant-ID` header
returns `400`.

## Scope and limitations

- Behavior is fully deterministic and local: no LLM calls, embeddings, vector
  database, network access, or persistence. The corpus lives in memory and
  resets on restart.
- Ranking uses each document's precomputed `score`; retrieval is lexical
  (token-overlap) matching, not semantic search.
- Tenant scoping demonstrates tenant-isolated retrieval. It is not a complete
  authorization system — the `X-Tenant-ID` header is trusted as supplied.
