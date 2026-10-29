from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .database import CourseStore
from .media_sources import MediaSourceError, SOURCE_REGISTRY, detect_media_source
from .study_service import StudyService
from .study_store import ARTIFACT_KINDS, StudyStore
from .transcript_export import SUPPORTED_EXPORT_FORMATS, export_transcript
from .visual_learning import analyze_video_visuals


class ProgressPayload(BaseModel):
    last_position_ms: int = Field(default=0, ge=0)
    completed: bool = False


class ArtifactGeneratePayload(BaseModel):
    transcript_id: str | None = Field(default=None, max_length=64)


class VisualAnalysisPayload(BaseModel):
    max_frames: int = Field(default=36, ge=2, le=60)
    vision_model: str | None = Field(default=None, max_length=80)


class GroundedChatPayload(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    lesson_id: str | None = Field(default=None, max_length=64)
    course_id: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=8, ge=1, le=20)


def _source_payload(spec, *, canonical_host: str | None = None) -> dict[str, Any]:
    return {
        "key": spec.key,
        "display_name": spec.display_name,
        "canonical_host": canonical_host,
        "hosts": list(spec.hosts),
        "capabilities": {
            "video": spec.capabilities.video,
            "audio": spec.capabilities.audio,
            "photo": spec.capabilities.photo,
            "carousel": spec.capabilities.carousel,
            "gif": spec.capabilities.gif,
        },
        "policy_mode": spec.policy_mode.value,
        "implementation_state": spec.implementation_state.value,
        "archive_enabled": spec.archive_enabled,
    }


def build_api_v1(store: CourseStore, download_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["course-intelligence-v1"])
    study_store = StudyStore(store.path)
    study = StudyService(store, study_store)
    visual_jobs: dict[str, dict[str, Any]] = {}

    def visual_paths(lesson_id: str) -> tuple[Path, Path]:
        try:
            lesson = store.lesson(lesson_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Lesson not found.") from exc
        rel_path = lesson.get("media_path")
        if not rel_path:
            raise HTTPException(status_code=409, detail="No downloaded video associated with this lesson. Archive authorized video media first.")
        root = download_root.resolve()
        media = (root / rel_path).resolve()
        if not media.is_relative_to(root) or not media.is_file():
            raise HTTPException(status_code=404, detail="Local lesson video not found.")
        # Browser analyses use .visual-{lesson_id}; CLI/worker analyses write
        # beside the source transcript in .<video-stem>.<lang>.learning/visuals.
        # Discover those same-media artifacts without scanning other lessons,
        # downloading another video, or following paths outside the library.
        output = media.parent / f".visual-{lesson_id}"
        if not (output / "visual-manifest.json").is_file():
            prefix = f".{media.stem}."
            for candidate in media.parent.iterdir():
                if not candidate.name.startswith(prefix) or not candidate.name.endswith(".learning"):
                    continue
                visual_dir = candidate / "visuals"
                if visual_dir.resolve().is_relative_to(root) and (visual_dir / "visual-manifest.json").is_file():
                    output = visual_dir
                    break
        if not output.resolve().is_relative_to(root):
            raise HTTPException(status_code=400, detail="Visual output path is outside the authorized library.")
        return media, output

    async def process_visuals(job_id: str, media: Path, folder: Path, max_frames: int, model: str | None) -> None:
        visual_jobs[job_id]["status"] = "running"
        try:
            result = await asyncio.to_thread(
                analyze_video_visuals, media, folder, max_frames=max_frames, vision_model=model
            )
            visual_jobs[job_id].update(status="complete", report=result)
        except Exception as exc:
            visual_jobs[job_id].update(status="failed", error=f"{type(exc).__name__}: {exc}"[:500])

    @router.post("/lessons/{lesson_id}/visuals")
    async def start_visuals(lesson_id: str, payload: VisualAnalysisPayload) -> dict[str, Any]:
        media, folder = visual_paths(lesson_id)
        if media.suffix.lower() not in {".mp4", ".mkv", ".webm", ".mov", ".m4v"}:
            raise HTTPException(status_code=400, detail="Video visuals require a supported video file.")
        if any(job.get("status") in {"queued", "running"} for job in visual_jobs.values()):
            raise HTTPException(status_code=429, detail="A visual analysis is already running.")
        # Keep in-memory status bounded; finished artifacts remain on durable disk.
        for old_id in list(visual_jobs)[:-100]:
            if visual_jobs[old_id]["status"] not in {"queued", "running"}:
                del visual_jobs[old_id]
        job_id = uuid.uuid4().hex
        visual_jobs[job_id] = {"id": job_id, "lesson_id": lesson_id, "status": "queued"}
        asyncio.create_task(process_visuals(job_id, media, folder, payload.max_frames, payload.vision_model))
        return visual_jobs[job_id].copy()

    @router.get("/lessons/{lesson_id}/visuals")
    async def get_visuals(lesson_id: str) -> dict[str, Any]:
        _, folder = visual_paths(lesson_id)
        active = next((job for job in reversed(list(visual_jobs.values()))
                       if job["lesson_id"] == lesson_id and job["status"] in {"queued", "running"}), None)
        if active:
            return active.copy()
        report = folder / "visual-manifest.json"
        if report.is_file():
            try:
                manifest = await asyncio.to_thread(lambda: json.loads(report.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                raise HTTPException(status_code=500, detail="Saved visual manifest is unreadable.")
            return manifest
        latest = next((job for job in reversed(list(visual_jobs.values()))
                       if job["lesson_id"] == lesson_id), None)
        return latest.copy() if latest else {"status": "not_started", "items": []}

    @router.get("/lessons/{lesson_id}/visuals/frame/{frame_name}")
    async def visual_frame(lesson_id: str, frame_name: str) -> FileResponse:
        _, folder = visual_paths(lesson_id)
        if not re.fullmatch(r"(?:periodic|scene)-\d{4}\.jpg", frame_name):
            raise HTTPException(status_code=404, detail="Frame not found.")
        frame = folder / "frames" / frame_name
        if not frame.is_file():
            raise HTTPException(status_code=404, detail="Frame not found.")
        return FileResponse(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @router.get("/media-sources")
    async def media_sources() -> dict[str, Any]:
        return {
            "sources": [_source_payload(spec) for spec in SOURCE_REGISTRY.values()],
            "count": len(SOURCE_REGISTRY),
            "notice": "archive_enabled is true only for repository-specific or current yt-dlp-backed public/authorized adapters; research-only sources remain blocked.",
        }

    @router.get("/media-sources/detect")
    async def media_source_detect(url: str = Query(min_length=1, max_length=4096)) -> dict[str, Any]:
        try:
            detected = detect_media_source(url)
        except MediaSourceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _source_payload(detected.source, canonical_host=detected.canonical_host)

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
