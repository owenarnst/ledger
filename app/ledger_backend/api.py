from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .repository import DEFAULT_DB_PATH, DEFAULT_SANDBOX_ROOT, LedgerRepository


class FileUpdate(BaseModel):
    content: str


class CoachRequest(BaseModel):
    question: str
    provider: str | None = None


class HookEventRequest(BaseModel):
    event_type: str
    cwd: str
    branch: str | None = None
    head_sha: str | None = None
    changed_files: list[str] = []
    source: str | None = None


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

    @app.post("/api/hooks/events")
    def record_hook_event(payload: HookEventRequest) -> dict:
        try:
            return repo.record_hook_event(
                event_type=payload.event_type,
                cwd=payload.cwd,
                branch=payload.branch,
                head_sha=payload.head_sha,
                payload={
                    "changed_files": payload.changed_files,
                    "source": payload.source,
                },
            )
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

    @app.post("/api/checks/{check_id}/complete")
    def complete_check(check_id: str) -> dict:
        try:
            return repo.complete_check(check_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="check not found") from exc

    return app


app = create_app()
