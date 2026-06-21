from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .hooks import DEFAULT_SPOOL_DIR, drain_spool, reset_ledger
from .ingestion import DEFAULT_PROVIDER, adapter_for
from .repository import DEFAULT_DB_PATH, DEFAULT_SANDBOX_ROOT, LedgerRepository


class FileUpdate(BaseModel):
    content: str


class CoachRequest(BaseModel):
    question: str
    provider: str | None = None


class PseudocodeCommentsRequest(BaseModel):
    file_path: str


class CheckRequest(BaseModel):
    topic_id: str


class ReflectionRequest(BaseModel):
    invariant: str = ""
    rationale: str = ""
    future_risk: str = ""


class CompleteCheckRequest(BaseModel):
    reflection: ReflectionRequest | None = None


class CoachAliasRequest(BaseModel):
    check_id: str
    question: str
    provider: str | None = None


class HookEventRequest(BaseModel):
    provider: str = DEFAULT_PROVIDER
    event_type: str
    cwd: str
    branch: str | None = None
    head_sha: str | None = None
    changed_files: list[str] = []
    source: str | None = None
    session_id: str | None = None
    source_path: str | None = None
    tool_sequence: list[str] = []
    link_confidence: str | None = None


class ImportSessionsRequest(BaseModel):
    provider: str
    root: str


class ResetRequest(BaseModel):
    spool_dir: str | None = None


def create_app(
    db_path: Path = DEFAULT_DB_PATH,
    sandbox_root: Path = DEFAULT_SANDBOX_ROOT,
) -> FastAPI:
    repo = LedgerRepository(db_path=db_path, sandbox_root=sandbox_root)
    repo.initialize()

    app = FastAPI(title="Ledger Backend")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/projects")
    def list_projects() -> list[dict]:
        return repo.list_projects()

    @app.get("/api/topics")
    def list_all_topics() -> list[dict]:
        return repo.list_all_topics()

    @app.post("/api/hooks/events")
    def record_hook_event(payload: HookEventRequest) -> dict:
        try:
            event = adapter_for(payload.provider).normalize(payload.model_dump())
            return repo.record_hook_event(
                provider=event.provider,
                event_type=event.event_type,
                cwd=event.cwd,
                branch=event.branch,
                head_sha=event.head_sha,
                payload=event.payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/hooks/drain")
    def drain_hook_spool() -> dict:
        return drain_spool(repo, spool_dir=DEFAULT_SPOOL_DIR)

    @app.post("/api/ingestion/sessions")
    def import_sessions(payload: ImportSessionsRequest) -> dict:
        try:
            return repo.import_provider_sessions(payload.provider, payload.root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects/{project_slug}/topics")
    def list_topics(project_slug: str) -> list[dict]:
        return repo.list_topics(project_slug)

    @app.get("/api/topics/{topic_id}")
    def get_topic(topic_id: str) -> dict:
        try:
            return repo.get_topic(topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="topic not found") from exc

    @app.get("/api/topics/{topic_id}/events")
    def list_events(topic_id: str) -> list[dict]:
        return repo.list_topic_events(topic_id)

    @app.get("/api/topics/{topic_id}/reflections")
    def list_reflections(topic_id: str) -> list[dict]:
        return repo.list_reflections(topic_id)

    @app.post("/api/checks")
    def create_check_alias(payload: CheckRequest) -> dict:
        try:
            return repo.create_check(payload.topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="topic not found") from exc

    @app.post("/api/topics/{topic_id}/checks")
    def create_check(topic_id: str) -> dict:
        try:
            return repo.create_check(topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="topic not found") from exc

    @app.get("/api/checks/{check_id}")
    def get_check(check_id: str) -> dict:
        try:
            return repo.get_check(check_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="check not found") from exc

    @app.post("/api/checks/{check_id}/pseudocode-comments")
    def pseudocode_comments(check_id: str, payload: PseudocodeCommentsRequest) -> dict:
        try:
            return repo.pseudocode_comments(check_id, payload.file_path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="check not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="file not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/checks/{check_id}/files/{file_path:path}")
    def read_file(check_id: str, file_path: str) -> dict:
        try:
            return repo.read_check_file(check_id, file_path)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="file not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/checks/{check_id}/files/{file_path:path}")
    def update_file(check_id: str, file_path: str, payload: FileUpdate) -> dict:
        try:
            return repo.update_check_file(check_id, file_path, payload.content)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="file not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/checks/{check_id}/run")
    def run_check(check_id: str) -> dict:
        try:
            return repo.run_check(check_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="check not found") from exc

    @app.post("/api/checks/{check_id}/coach")
    def ask_coach(check_id: str, payload: CoachRequest) -> dict:
        try:
            return repo.ask_coach(check_id, payload.question, provider=payload.provider)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="check not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/coach")
    def ask_coach_alias(payload: CoachAliasRequest) -> dict:
        try:
            return repo.ask_coach(payload.check_id, payload.question, provider=payload.provider)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="check not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/checks/{check_id}/complete")
    def complete_check(check_id: str, payload: CompleteCheckRequest | None = None) -> dict:
        try:
            reflection = payload.reflection.model_dump() if payload and payload.reflection else None
            return repo.complete_check(check_id, reflection=reflection)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="check not found") from exc

    @app.post("/api/reset")
    def reset(payload: ResetRequest | None = None) -> dict:
        return reset_ledger(
            db_path=db_path,
            sandbox_root=sandbox_root,
            spool_dir=Path(payload.spool_dir) if payload and payload.spool_dir else DEFAULT_SPOOL_DIR,
        )

    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="static")

    return app


app = create_app()
