from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .database import CourseStore
from .study_service import StudyService
from .study_store import ARTIFACT_KINDS, StudyStore
from .transcript_export import SUPPORTED_EXPORT_FORMATS, export_transcript


class ProgressPayload(BaseModel):
    last_position_ms: int = Field(default=0, ge=0)
    completed: bool = False


class ArtifactGeneratePayload(BaseModel):
    transcript_id: str | None = Field(default=None, max_length=64)


class GroundedChatPayload(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    lesson_id: str | None = Field(default=None, max_length=64)
    course_id: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=8, ge=1, le=20)


def build_api_v1(store: CourseStore, download_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["course-intelligence-v1"])
    study_store = StudyStore(store.path)
    study = StudyService(store, study_store)

    @router.get("/courses")
    async def courses() -> dict[str, Any]:
        try:
            return await asyncio.to_thread(store.sync_library, download_root)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail="Unable to refresh the course library.") from exc

    @router.get("/courses/{course_id}")
    async def course(course_id: str) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(store.course, course_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Course not found.") from exc

    @router.get("/lessons/{lesson_id}")
    async def lesson(lesson_id: str) -> dict[str, Any]:
        try:
            payload = await asyncio.to_thread(store.lesson, lesson_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Lesson not found.") from exc
        return payload

    @router.get("/lessons/{lesson_id}/progress")
    async def lesson_progress(lesson_id: str) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(store.get_progress, lesson_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Lesson not found.") from exc

    @router.put("/lessons/{lesson_id}/progress")
    async def save_lesson_progress(lesson_id: str, payload: ProgressPayload) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(store.put_progress, lesson_id, payload.last_position_ms, payload.completed)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Lesson not found.") from exc

    @router.get("/lessons/{lesson_id}/artifacts")
    async def lesson_artifacts(lesson_id: str, kind: str | None = None) -> dict[str, Any]:
        try:
            store.lesson(lesson_id)
            items = await asyncio.to_thread(study_store.artifacts, lesson_id, kind)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Lesson not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"lesson_id": lesson_id, "artifacts": items, "count": len(items)}

    @router.post("/lessons/{lesson_id}/artifacts/{kind}")
    async def generate_artifact(
        lesson_id: str,
        kind: str,
        payload: ArtifactGeneratePayload | None = None,
    ) -> dict[str, Any]:
        if kind not in ARTIFACT_KINDS:
            raise HTTPException(status_code=400, detail="Unsupported study artifact kind.")
        try:
            return await asyncio.to_thread(
                study.generate,
                lesson_id,
                kind,
                payload.transcript_id if payload else None,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Lesson or transcript not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/artifacts/{artifact_id}")
    async def artifact(artifact_id: str) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(study_store.artifact, artifact_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Study artifact not found.") from exc

    @router.post("/chat")
    async def grounded_chat(payload: GroundedChatPayload) -> dict[str, Any]:
        return await asyncio.to_thread(
            study.grounded_evidence,
            payload.question,
            lesson_id=payload.lesson_id,
            course_id=payload.course_id,
            limit=payload.limit,
        )

    @router.get("/transcripts/{transcript_id}")
    async def transcript(transcript_id: str) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(store.transcript, transcript_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Transcript not found.") from exc

    @router.get("/transcripts/{transcript_id}/search")
    async def transcript_search(
        transcript_id: str,
        q: str = Query(min_length=1, max_length=500),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            transcript_payload = await asyncio.to_thread(store.transcript, transcript_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Transcript not found.") from exc
        needle = q.casefold()
        hits = []
        for segment in transcript_payload.get("segments", []):
            if needle not in str(segment.get("text") or "").casefold():
                continue
            hits.append(segment)
            if len(hits) >= limit:
                break
        return {"query": q, "transcript_id": transcript_id, "hits": hits, "count": len(hits)}

    @router.get("/transcripts/{transcript_id}/export")
    async def transcript_export(
        transcript_id: str,
        format: str = Query(default="txt"),
    ) -> Response:
        export_format = format.strip().lower()
        if export_format not in SUPPORTED_EXPORT_FORMATS:
            raise HTTPException(status_code=400, detail="Unsupported transcript export format.")
        try:
            transcript_payload = await asyncio.to_thread(store.transcript, transcript_id)
            body, media_type, extension = export_transcript(transcript_payload, export_format)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Transcript not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", transcript_id).strip("-") or "transcript"
        return Response(
            content=body,
            media_type=media_type.split(";", 1)[0],
            headers={
                "Content-Disposition": f'attachment; filename="{safe_id}.{extension}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
