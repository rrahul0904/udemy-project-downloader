from __future__ import annotations

from typing import Any

from .database import CourseStore
from .providers import ExtractiveGenerationProvider, GenerationProvider
from .study_store import ARTIFACT_KINDS, StudyStore


class StudyService:
    """Application service for citation-first generated study artifacts and grounded evidence."""

    def __init__(
        self,
        course_store: CourseStore,
        study_store: StudyStore,
        provider: GenerationProvider | None = None,
    ):
        self.course_store = course_store
        self.study_store = study_store
        self.provider = provider or ExtractiveGenerationProvider()

    def generate(self, lesson_id: str, kind: str, transcript_id: str | None = None) -> dict[str, Any]:
        if kind not in ARTIFACT_KINDS:
            raise ValueError("Unsupported study artifact kind.")
        lesson = self.course_store.lesson(lesson_id)
        variants = lesson.get("transcripts") or []
        if not variants:
            raise KeyError("transcript")
        selected = transcript_id or variants[0]["id"]
        if not any(item["id"] == selected for item in variants):
            raise ValueError("Transcript does not belong to this lesson.")
        transcript = self.course_store.transcript(selected)
        if kind == "summary":
            notes = self.provider.notes(transcript)
            content = {
                "title": "Source-grounded summary",
                "summary": [
                    {
                        "text": bullet["text"],
                        "citations": bullet["citations"],
                    }
                    for section in notes.get("sections", [])
                    for bullet in section.get("bullets", [])[:1]
                ],
            }
        elif kind == "notes":
            content = self.provider.notes(transcript)
        elif kind == "flashcards":
            content = self.provider.flashcards(transcript)
        elif kind == "quiz":
            content = self.provider.quiz(transcript)
        else:
            content = self.provider.concept_map(transcript)
        return self.study_store.save_artifact(
            lesson_id=lesson_id,
            course_id=lesson["course_id"],
            kind=kind,
            transcript_id=selected,
            provider=self.provider.name,
            model=self.provider.model,
            content=content,
        )

    def grounded_evidence(
        self,
        question: str,
        *,
        lesson_id: str | None = None,
        course_id: str | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        question = question.strip()
        if not question:
            return {"mode": "COURSE_GROUNDED", "query": question, "answer": "", "citations": []}
        search = self.course_store.search(question, lesson_id=lesson_id, course_id=course_id, limit=limit)
        hits = search.get("hits") or []
        if not hits:
            # Fall back to meaningful terms because raw FTS AND semantics can be too strict for natural questions.
            terms = [word.strip(".,!?()[]{}\"'").casefold() for word in question.split() if len(word.strip(".,!?()[]{}\"'")) >= 4]
            seen = set()
            hits = []
            for term in terms[:6]:
                partial = self.course_store.search(term, lesson_id=lesson_id, course_id=course_id, limit=limit)
                for hit in partial.get("hits") or []:
                    key = (hit.get("transcript_id"), hit.get("start_ms"), hit.get("snippet"))
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(hit)
                    if len(hits) >= limit:
                        break
                if len(hits) >= limit:
                    break
        citations = [
            {
                "transcript_id": hit.get("transcript_id"),
                "lesson_id": hit.get("lesson_id"),
                "course_id": hit.get("course_id"),
                "lesson_title": hit.get("lesson_title"),
                "course_title": hit.get("course_title"),
                "start_ms": hit.get("start_ms"),
                "end_ms": hit.get("end_ms"),
                "text": str(hit.get("snippet") or "").replace("<mark>", "").replace("</mark>", ""),
            }
            for hit in hits[:limit]
        ]
        if citations:
            answer = "Grounded evidence found in the course transcript. Review the cited source segments below; no uncited model knowledge was added."
        else:
            answer = "No matching transcript evidence was found. No answer was generated from outside knowledge."
        return {
            "mode": "COURSE_GROUNDED",
            "query": question,
            "scope": {"lesson_id": lesson_id, "course_id": course_id},
            "answer": answer,
            "citations": citations,
        }
