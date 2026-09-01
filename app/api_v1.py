from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .database import CourseStore
from .transcript_export import SUPPORTED_EXPORT_FORMATS, export_transcript


class ProgressPayload(BaseModel):
    last_position_ms: int = Field(default=0, ge=0)
    completed: bool = False


def build_api_v1(store: CourseStore, download_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["course-intelligence-v1"])

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
        # API callers receive relative media/attachment paths only. The guarded /files route remains the file boundary.
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
