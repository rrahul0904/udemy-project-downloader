from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any


class TranscriptionProvider(ABC):
    @abstractmethod
    def transcribe(self, media_path: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError


class GenerationProvider(ABC):
    name = "disabled"
    model = "none"

    @abstractmethod
    def notes(self, transcript: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def flashcards(self, transcript: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def quiz(self, transcript: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def concept_map(self, transcript: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class DisabledGenerationProvider(GenerationProvider):
    def _disabled(self) -> dict[str, Any]:
        raise RuntimeError("Generation provider is disabled.")

    notes = lambda self, transcript: self._disabled()
    flashcards = lambda self, transcript: self._disabled()
    quiz = lambda self, transcript: self._disabled()
    concept_map = lambda self, transcript: self._disabled()


class ExtractiveGenerationProvider(GenerationProvider):
    """Deterministic, local, citation-first baseline requiring no external AI service."""

    name = "local-extractive"
    model = "deterministic-v1"

    def notes(self, transcript: dict[str, Any]) -> dict[str, Any]:
        segments = self._segments(transcript)
        if not segments:
            return {"title": "Study notes", "sections": []}
        chunk = max(1, min(6, (len(segments) + 3) // 4))
        sections = []
        for group_index, start in enumerate(range(0, len(segments), chunk), start=1):
            group = segments[start : start + chunk]
            bullets = []
            for segment in group[:4]:
                bullets.append(
                    {
                        "text": self._trim(segment["text"], 260),
                        "citations": [self._citation(transcript, segment)],
                    }
                )
            sections.append({"heading": f"Topic {group_index}", "bullets": bullets})
        return {"title": "Cited study notes", "sections": sections}

    def flashcards(self, transcript: dict[str, Any]) -> dict[str, Any]:
        segments = self._sample(self._segments(transcript), 12)
        cards = []
        for index, segment in enumerate(segments, start=1):
            answer = self._trim(segment["text"], 320)
            cards.append(
                {
                    "id": f"card-{index}",
                    "kind": "qa",
                    "question": f"What key point is stated around {self._time(segment.get('start_ms'))}?",
                    "answer": answer,
                    "citations": [self._citation(transcript, segment)],
                }
            )
        return {"title": "Source-grounded flashcards", "cards": cards}

    def quiz(self, transcript: dict[str, Any]) -> dict[str, Any]:
        segments = self._sample(self._segments(transcript), 10)
        questions = []
        answers = [self._trim(item["text"], 180) for item in segments]
        for index, segment in enumerate(segments[:8]):
            correct = answers[index]
            citation = self._citation(transcript, segment)
            if index % 2 == 0 and len(answers) >= 3:
                distractors = []
                for offset in range(1, len(answers)):
                    candidate = answers[(index + offset) % len(answers)]
                    if candidate != correct and candidate not in distractors:
                        distractors.append(candidate)
                    if len(distractors) == 3:
                        break
                options = [correct, *distractors]
                questions.append(
                    {
                        "id": f"question-{index + 1}",
                        "kind": "multiple_choice",
                        "prompt": f"Which statement is supported by the source around {self._time(segment.get('start_ms'))}?",
                        "options": options,
                        "correct_index": 0,
                        "explanation": correct,
                        "citations": [citation],
                    }
                )
            else:
                questions.append(
                    {
                        "id": f"question-{index + 1}",
                        "kind": "short_answer",
                        "prompt": f"Summarize the source point around {self._time(segment.get('start_ms'))}.",
                        "answer": correct,
                        "explanation": correct,
                        "citations": [citation],
                    }
                )
        return {"title": "Source-grounded quiz", "questions": questions}

    def concept_map(self, transcript: dict[str, Any]) -> dict[str, Any]:
        segments = self._segments(transcript)
        tokens = []
        evidence: dict[str, list[dict[str, Any]]] = {}
        stop = {
            "this", "that", "with", "from", "have", "will", "your", "into", "about", "there", "their",
            "then", "than", "when", "what", "which", "where", "were", "been", "being", "also", "using",
            "the", "and", "for", "are", "you", "but", "not", "can", "all", "our", "has", "was", "its",
        }
        for segment in segments:
            words = {word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", segment["text"])}
            for word in words - stop:
                tokens.append(word)
                evidence.setdefault(word, []).append(self._citation(transcript, segment))
        concepts = [word for word, _ in Counter(tokens).most_common(10)]
        nodes = [
            {"id": word, "label": word.replace("_", " ").title(), "citations": evidence[word][:3]}
            for word in concepts
        ]
        edges = []
        for segment in segments:
            present = [word for word in concepts if re.search(rf"\b{re.escape(word)}\b", segment["text"], re.I)]
            for left, right in zip(present, present[1:]):
                key = tuple(sorted((left, right)))
                if any(edge["key"] == key for edge in edges):
                    continue
                edges.append(
                    {"key": key, "source": key[0], "target": key[1], "relation": "co-occurs", "citations": [self._citation(transcript, segment)]}
                )
        for edge in edges:
            edge.pop("key", None)
        return {"title": "Source concept map", "nodes": nodes, "edges": edges[:20]}

    @staticmethod
    def _segments(transcript: dict[str, Any]) -> list[dict[str, Any]]:
        return [segment for segment in transcript.get("segments") or [] if str(segment.get("text") or "").strip()]

    @staticmethod
    def _sample(segments: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
        if len(segments) <= maximum:
            return segments
        indexes = sorted({round(i * (len(segments) - 1) / (maximum - 1)) for i in range(maximum)})
        return [segments[index] for index in indexes]

    @staticmethod
    def _trim(value: str, limit: int) -> str:
        value = re.sub(r"\s+", " ", str(value)).strip()
        return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"

    @staticmethod
    def _time(value: int | None) -> str:
        if value is None:
            return "the cited segment"
        total = max(0, int(value)) // 1000
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"

    @staticmethod
    def _citation(transcript: dict[str, Any], segment: dict[str, Any]) -> dict[str, Any]:
        return {
            "transcript_id": transcript["id"],
            "segment_index": int(segment.get("segment_index", 0)),
            "start_ms": segment.get("start_ms"),
            "end_ms": segment.get("end_ms"),
            "text": segment.get("text") or "",
        }
