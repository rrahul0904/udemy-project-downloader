import json
import tempfile
import unittest
from pathlib import Path

from app.database import CourseStore
from app.study_service import StudyService
from app.study_store import StudyStore


VTT = """WEBVTT

00:00:01.000 --> 00:00:04.000
SQLite FTS5 provides durable full text search across transcript segments.

00:00:05.000 --> 00:00:09.000
Vector embeddings can represent related concepts as numerical vectors.

00:00:10.000 --> 00:00:14.000
Cosine similarity compares the direction of normalized vector embeddings.

00:00:15.000 --> 00:00:19.000
Source citations should send learners back to the exact lecture evidence.
"""


class StudyArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.downloads = root / "downloads"
        self.data = root / "data"
        course = self.downloads / "StudyCourse"
        course.mkdir(parents=True)
        (course / "001 Grounded Learning.en.vtt").write_text(VTT, encoding="utf-8")
        (course / "001 Grounded Learning.info.json").write_text(
            json.dumps(
                {
                    "id": "grounded-learning",
                    "title": "Grounded Learning",
                    "playlist_title": "Study Course",
                    "playlist_index": 1,
                    "webpage_url": "https://www.youtube.com/watch?v=grounded-learning",
                    "extractor_key": "Youtube",
                    "subtitles": {"en": []},
                    "duration": 19,
                }
            ),
            encoding="utf-8",
        )
        self.course_store = CourseStore(self.data / "app.db")
        library = self.course_store.sync_library(self.downloads)
        self.lesson = library["courses"][0]["lessons"][0]
        self.study_store = StudyStore(self.course_store.path)
        self.service = StudyService(self.course_store, self.study_store)

    def tearDown(self):
        self.temp.cleanup()

    def test_generation_is_versioned_cited_and_keeps_personal_notes(self):
        lesson_id = self.lesson["id"]
        self.course_store.put_note(lesson_id, "My private note must survive generation.")

        generated = {}
        for kind in ("notes", "flashcards", "quiz", "concept_map"):
            artifact = self.service.generate(lesson_id, kind)
            generated[kind] = artifact
            self.assertEqual(artifact["kind"], kind)
            self.assertEqual(artifact["lesson_id"], lesson_id)
            self.assertEqual(artifact["provider"], "local-extractive")
            self.assertEqual(artifact["model"], "deterministic-v1")
            self.assertGreater(len(artifact["citations"]), 0, kind)
            for citation in artifact["citations"]:
                self.assertEqual(citation["transcript_id"], artifact["source_transcript_id"])
                self.assertGreaterEqual(citation["segment_index"], 0)
                self.assertTrue(citation["text"])

        second_notes = self.service.generate(lesson_id, "notes")
        self.assertEqual(second_notes["version"], generated["notes"]["version"] + 1)
        self.assertEqual(self.course_store.get_note(lesson_id)["body"], "My private note must survive generation.")

        reopened = StudyStore(self.course_store.path)
        stored = reopened.artifact(generated["quiz"]["id"])
        self.assertEqual(stored["kind"], "quiz")
        self.assertGreater(len(stored["citations"]), 0)
        health = reopened.health()
        self.assertGreaterEqual(health["study_artifacts"], 5)
        self.assertGreater(health["artifact_citations"], 0)

    def test_grounded_evidence_never_fabricates_when_transcript_has_no_match(self):
        lesson_id = self.lesson["id"]
        found = self.service.grounded_evidence("SQLite", lesson_id=lesson_id)
        self.assertEqual(found["mode"], "COURSE_GROUNDED")
        self.assertGreater(len(found["citations"]), 0)
        self.assertTrue(any("SQLite" in item["text"] for item in found["citations"]))

        missing = self.service.grounded_evidence("photosynthesis chloroplast", lesson_id=lesson_id)
        self.assertEqual(missing["mode"], "COURSE_GROUNDED")
        self.assertEqual(missing["citations"], [])
        self.assertIn("No matching transcript evidence", missing["answer"])
        self.assertIn("No answer was generated from outside knowledge", missing["answer"])

    def test_artifact_kind_validation_rejects_unknown_generation(self):
        with self.assertRaises(ValueError):
            self.service.generate(self.lesson["id"], "hallucinated_magic")


if __name__ == "__main__":
    unittest.main()
