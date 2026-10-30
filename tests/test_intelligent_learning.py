"""Full learning-guide quality gates using a Snowflake CoCo-shaped transcript.

No network, no LLM weights, no YouTube requests; generator is mocked.  Verify
that an incomplete seven-point recap is NOT accepted as a finished course.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database import CourseStore
from app.intelligent_learning import (
    LearningGuideError, generate_learning_guide, load_visual_evidence,
)
from app.study_service import StudyService
from app.study_store import StudyStore


def transcript():
    sentences = [
        "We are demonstrating the Snowflake CoCo cost intelligence skill.",
        "Cost questions can be asked in natural language.",
        "The cost request triggers the skill and routes to the relevant metadata.",
        "Queries are verified and performed within guardrails.",
        "The guided workflow returns actionable results.",
        "We can ask which users and services consume the most credits.",
        "The instructor opens the CoCo interaction panel.",
        "The skill receives a natural-language request for an HTML cost report.",
        "The generated report appears in the Snowflake Workspaces section.",
        "The instructor downloads the HTML report and opens it in a browser.",
        "The cost report includes total credits and service breakdown charts.",
        "The daily usage chart shows a spike on an example date.",
        "The cost management console includes an anomalies view.",
        "Analyze Anomalies with CoCo investigates possible spike contributors.",
        "The displayed anomalies and drivers still need validation.",
    ]
    return {"id": "transcript-1", "segments": [
        {"segment_index": i, "start_ms": i * 10000, "end_ms": (i + 1) * 10000, "text": s}
        for i, s in enumerate(sentences)
    ]}


def manifest():
    return {"items": [
        {"frame_file": "frames/periodic-0001.jpg", "timestamp_ms": 30000,
         "category": "diagram_candidate", "ocr": {"text": "Trigger Route Verify Guardrails Workflow Results"}},
        {"frame_file": "frames/periodic-0002.jpg", "timestamp_ms": 85000,
         "category": "slide_candidate", "ocr": {"text": "Cost Intelligence dashboard"}},
    ]}


def model_output():
    why = "This lets a learner move from unexplained usage to evidence-backed investigation before proposing an operational change."
    explain = ("The instructor introduces this capability, demonstrates its interface, and connects the result "
               "to a concrete question about Snowflake consumption. The learner should distinguish "
               "observed data from unverified explanations and trace each step to the actual source video.")
    step = "Open the demonstrated Cost Intelligence interface and verify that the correct account context and permissions are active."
    return {
        "title": "How to investigate Snowflake costs using CoCo",
        "overview": "In this lecture, the instructor shows how to move from a natural-language cost question "
                    "through the Cost Intelligence workflow to an HTML usage report and an anomaly investigation. "
                    "You will learn how the interface is navigated, how the report is interpreted, and how to "
                    "avoid confusing a suspected spending driver with a verified root cause.",
        "learning_outcomes": [
            "Explain the stages connecting natural-language requests with guarded cost analysis.",
            "Follow the demonstrated workflow to request and open a monthly HTML consumption report.",
            "Interpret service breakdowns and investigate cost spikes without claiming unsupported savings.",
        ],
        "takeaways": [{
            "text": "Natural-language cost analysis helps users identify consumption patterns, but the observed results still require account-context and permissions checks.",
            "segment_ids": [i],
        } for i in (1, 3, 5, 7, 12)],
        "chapters": [{
            "heading": f"Understand the cost analysis task and workflow {i}",
            "explanation": explain,
            "why_it_matters": why,
            "steps": [step, "Examine the returned screen and compare what is displayed with the corresponding transcript and numerical source evidence."],
            "pitfalls": "Do not assume that the instructional demonstration verifies current software capabilities or automatically proves the root cause of an anomaly.",
            "segment_ids": [i*3, i*3+1],
            "frame_files": ["frames/periodic-0001.jpg"] if i == 0 else [],
        } for i in range(3)],
        "worked_example": {
            "scenario": "An illustrative Snowflake account exhibits increased consumption in the instructor's usage report. The learner should investigate daily changes before recommending action.",
            "steps": [step,
                      "Open the HTML cost report and compare service-level consumption across the reported interval.",
                      "Inspect anomalies in the cost-management screen and look for actual metering evidence for the spike."],
            "expected_result": "The learner can identify which service and period should be investigated further and can distinguish observed credits from explanations that remain hypotheses.",
            "limitations": "The demonstrated account figures are examples only. No total dollar savings or validated root cause can be inferred without workload evidence.",
            "segment_ids": [7, 11, 13],
        },
        "practice": [{
            "question": "How should a learner validate a suspected cause of increasing Snowflake consumption?",
            "model_answer": "First identify the time range and consuming service from the report; then compare anomalies to metering evidence and confirm the workload context before changing any configuration.",
            "segment_ids": [10, 13],
        }, {
            "question": "What is the limitation of reading an HTML usage report without inspecting the original data?",
            "model_answer": "The display can reveal trends and reported totals, but it does not alone establish that consumption is wasteful or that a particular workload caused a spike; corroboration is necessary.",
            "segment_ids": [9, 12],
        }],
        "review_flags": [
            "Verify the actual cost values and screen terminology against the captured lecture before relying on the operational example."
        ],
    }


class IntelligentLearningTests(unittest.TestCase):
    def test_substantive_guide_is_generated_with_real_source_ids(self):
        generated = generate_learning_guide(
            transcript(), manifest(), model="qwen2.5:7b",
            generator=lambda prompt, model: model_output()
        )
        self.assertEqual(len(generated["chapters"]), 3)
        self.assertEqual(len(generated["takeaways"]), 5)
        self.assertEqual(generated["status"], "ai_draft_requires_review")
        self.assertEqual(generated["chapters"][0]["citations"][0]["start_ms"], 0)
        self.assertEqual(generated["chapters"][0]["visuals"][0]["frame_file"], "frames/periodic-0001.jpg")
        self.assertEqual(generated["worked_example"]["citations"][1]["segment_index"], 11)

    def test_model_receives_actual_transcript_and_ocr(self):
        prompts = []
        def capture(prompt, model):
            prompts.append(prompt)
            return model_output()
        generate_learning_guide(transcript(), manifest(), model="qwen2.5:7b", generator=capture)
        self.assertIn("Analyze Anomalies with CoCo", prompts[0])
        self.assertIn("Trigger Route Verify Guardrails", prompts[0])
        self.assertIn("segment_ids", prompts[0])
        self.assertNotIn("seven-bullet video recap", prompts[0].split("SOURCE TRANSCRIPT")[1])

    def test_rejects_shallow_non_instructional_output(self):
        shallow = model_output()
        shallow["chapters"] = []
        with self.assertRaisesRegex(LearningGuideError, "instructional chapters"):
            generate_learning_guide(transcript(), manifest(), model="qwen2.5:7b",
                                    generator=lambda *_: shallow)
        shallow = model_output()
        shallow["chapters"][1]["explanation"] = "The video covers cost intelligence."
        with self.assertRaisesRegex(LearningGuideError, "chapter 2 explanation"):
            generate_learning_guide(transcript(), manifest(), model="qwen2.5:7b",
                                    generator=lambda *_: shallow)

    def test_rejects_fabricated_transcript_or_frame_citations(self):
        made_up = model_output()
        made_up["takeaways"][0]["segment_ids"] = [9999]
        with self.assertRaisesRegex(LearningGuideError, "unknown transcript"):
            generate_learning_guide(transcript(), manifest(), model="qwen2.5:7b",
                                    generator=lambda *_: made_up)
        made_up = model_output()
        made_up["chapters"][0]["frame_files"] = ["frames/not-real.jpg"]
        with self.assertRaisesRegex(LearningGuideError, "frame not present"):
            generate_learning_guide(transcript(), manifest(), model="qwen2.5:7b",
                                    generator=lambda *_: made_up)

    def test_long_video_requires_later_chapter_evidence(self):
        long_source = transcript()
        for i, segment in enumerate(long_source["segments"]):
            segment["start_ms"] = i * 60000
            segment["end_ms"] = (i + 1) * 60000
        with self.assertRaisesRegex(LearningGuideError, "lecture timeline"):
            generate_learning_guide(long_source, manifest(), model="qwen2.5:7b",
                                    generator=lambda *_: model_output())

    def test_retries_once_when_first_answer_is_shallow(self):
        attempts = []
        def generate(prompt, model):
            attempts.append(prompt)
            answer = model_output()
            if len(attempts) == 1:
                answer["chapters"] = []
            return answer
        result = generate_learning_guide(transcript(), manifest(), model="qwen2.5:7b",
                                         generator=generate)
        self.assertEqual(len(attempts), 2)
        self.assertIn("failed mandatory educational quality validation", attempts[1])
        self.assertEqual(len(result["chapters"]), 3)

    def test_fails_clearly_if_model_is_not_configured(self):
        with patch.dict("os.environ", {"CI_LEARNING_MODEL": ""}):
            with self.assertRaisesRegex(LearningGuideError, "not configured"):
                generate_learning_guide(transcript(), manifest(), generator=lambda *_: model_output())

    def test_worker_visual_package_is_discovered_only_for_matching_media(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "download" / "lesson"
            folder.mkdir(parents=True)
            media = folder / "Snowflake CoCo [fYgggzLEIFs].mp4"
            media.write_bytes(b"local demo")
            correct = folder / (".Snowflake CoCo [fYgggzLEIFs].en.learning") / "visuals"
            correct.mkdir(parents=True)
            (correct / "visual-manifest.json").write_text(json.dumps(manifest()), encoding="utf-8")
            lesson = {"id": "abc", "media_path": "lesson/" + media.name}
            self.assertEqual(len(load_visual_evidence(root / "download", lesson)["items"]), 2)
            self.assertIsNone(load_visual_evidence(root / "download", {**lesson, "media_path": "../../outside.mp4"}))

    def test_persists_generated_guide_as_versioned_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            download = root / "downloads"
            folder = download / "CoCo"
            folder.mkdir(parents=True)
            (folder / "example.en.vtt").write_text(
                "WEBVTT\n\n" + "\n\n".join(
                    f"00:{i:02d}:00.000 --> 00:{i:02d}:01.000\n{seg['text']}"
                    for i, seg in enumerate(transcript()["segments"])
                ), encoding="utf-8"
            )
            store = CourseStore(root / "data" / "app.db")
            lib = store.sync_library(download)
            lesson_id = lib["courses"][0]["lessons"][0]["id"]
            study_store = StudyStore(store.path)
            with patch("app.study_service.learning_model", return_value="qwen2.5:7b"), patch(
                "app.study_service.generate_learning_guide", return_value={
                    "title": "Real teaching material", "chapters": model_output()["chapters"],
                    "status": "ai_draft_requires_review",
                }
            ):
                artifact = StudyService(store, study_store, download_root=download).generate(
                    lesson_id, "learning_guide"
                )
            self.assertEqual(artifact["kind"], "learning_guide")
            self.assertEqual(artifact["provider"], "local-ollama-instructional")
            self.assertEqual(study_store.latest(lesson_id, "learning_guide")["id"], artifact["id"])


if __name__ == "__main__":
    unittest.main()
