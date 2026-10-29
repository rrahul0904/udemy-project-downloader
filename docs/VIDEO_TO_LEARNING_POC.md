# Video-to-Learning POC — Wave 1

## User-selected pilot

Source URL: https://www.youtube.com/watch?v=fYgggzLEIFs&list=PLL_i-2mmiz0c

The POC intentionally processes only video ID fYgggzLEIFs, not the full playlist. Playlist/course traversal requires a later, independently verified batch gate.

## Run on a local installation

Install the repository dependencies and run:

    pip install -r requirements.txt
    python scripts/video_to_learning_poc.py --url 'https://www.youtube.com/watch?v=fYgggzLEIFs&list=PLL_i-2mmiz0c'

If this video has no usable caption track, and you have normal authorized access to its audio:

    pip install -r requirements-asr.txt
    python scripts/video_to_learning_poc.py --url 'https://www.youtube.com/watch?v=fYgggzLEIFs' --asr-fallback

For a locally acquired authorized transcript, without network access:

    python scripts/video_to_learning_poc.py --input /path/to/lecture.en.vtt

Processing is caption-first: when captions are available, video download is not required. The optional ASR path uses faster-whisper on the local machine, with CPU by default. The model may be downloaded on first use. No DRM, account, paywall, or CAPTCHA bypass is supported.

## Outputs

Under downloads/VideoToLearningPOC/fYgggzLEIFs/ when the live source is available:
- Original caption track and video information JSON.
- Hidden .<transcript-stem>.learning/ folder with transcript.txt, transcript.json, transcript.srt and transcript.vtt (timed formats only where suitable).
- source-grounded-study-guide.md: timestamped verbatim excerpt outline, not AI-invented instructional content.
- quality-report.json: word/segment count, non-overlapping caption coverage, malformed cues and long-gap warnings.
- Existing Course Intelligence SQLite library ingestion and search through the existing application. Generated derivative exports are deliberately stored under a hidden folder to avoid being re-ingested as duplicate lessons.

Status transcribed_unverified means some caption text with usable timestamps exists. It **does not** mean speech was fully checked or that slides, code, formulas or demonstrations were captured. An empty transcript is a blocked result; timestamp-free transcripts require review.

## Required acceptance evidence

1. Run on the real user-selected video and capture the actual source title, duration, caption language, and metadata.
2. Confirm nonzero transcript words and a real sample of timestamps against the audio.
3. Inspect long caption gaps and test whether they are silence or missed speech; timeline coverage is NOT word error rate.
4. Validate transcript export and Course Intelligence library search using that exact source.
5. Preserve no copyrighted transcript/media in the repository.
6. Do not mark the source converted completely until visual extraction and independent fidelity review finish.

This environment did not establish live access to the sample YouTube video; no real video success is claimed by these commits.

## REA / roadmap integration

- **Wave 1 — this PR:** Single-video captions and optional local speech recognition, timestamped export, timeline checks, evidence-first notes, and library ingestion.
- **Wave 2 — next:** Extract frame changes, slides, on-screen code, diagram evidence, OCR with confidence, and frame-to-transcript alignment.
- **Wave 3:** Produce comprehensive learning modules, hands-on steps, corrected code, grounded practice questions, diagrams and instructor-reviewed learning guides.
- **Wave 4:** Course/playlist processing with durable resumable jobs, reviewer UI, multi-language outputs, full coverage reports, and regression/production acceptance.

Production is NOT certified by synthetic tests. All new features must preserve existing local-first, authorized-source, citation-first, single-repository policies.

## Wave 2 implemented: timestamped visual evidence

Use the existing Wave 1 script with the visual flag:

    python scripts/video_to_learning_poc.py --url 'https://www.youtube.com/watch?v=fYgggzLEIFs&list=PLL_i-2mmiz0c' --visuals

Or analyze an authorized local lecture and transcribe it:

    pip install -r requirements-asr.txt
    python scripts/video_to_learning_poc.py --video-file /path/to/lecture.mp4 --asr-fallback --visuals

If you already have a transcript and video as separate local files:

    python scripts/video_to_learning_poc.py --input /path/to/lecture.en.vtt --media /path/to/lecture.mp4 --visuals

Install ffmpeg / ffprobe and Tesseract OCR on the host (for macOS, `brew install ffmpeg tesseract`).
The Docker image also supplies ffmpeg and Tesseract, but the POC script runs on the host unless executed inside a configured container.

A successful visual run produces a `visuals/` subfolder within the hidden learning package. It contains
`frames/` JPEG images, `visual-manifest.json`, `visual-study-notes.md`, `code-candidates.md`,
`slide-candidates.md`, and `diagram-candidates.md`. The manifest records sampling method, frame times,
OCR text/confidence, SHA-256 image receipts and candidate classifications.

Frame extraction samples the entire movie periodically (up to a frame budget) and opportunistically samples
scene changes. It does NOT guarantee every slide, intermediate code edit, or diagram edge has been seen.
Tesseract OCR can produce invalid code characters and cannot prove architectural arrow relationships.

For optional diagram descriptions with a local-only Ollama multimodal model, first configure a local Ollama
server at `127.0.0.1:11434`, install/pull a suitable vision model, then run:

    python scripts/video_to_learning_poc.py --video-file /path/to/lecture.mp4 --asr-fallback --visuals --vision-model llava

This local-model option is explicit and never uploads video frames to an external AI provider. Model-generated
descriptions are tagged `unverified`, and failed model calls produce warnings. Reviewing the frame images
and original media remains necessary before approving teaching material.

**Proof status:** The visual extractor has local synthetic-video smoke coverage and tests for OCR, classification,
review flags, image evidence and frame count bounds. Actual user-selected YouTube media has **not** been fetched
or visually verified in this environment; real POC acceptance is still pending. All outputs should be treated
as a pilot, not a certified complete course conversion.

## Course Intelligence UI integration (Visual Evidence tab)

After an authorized downloaded video has been indexed as a lesson, open
`/learn`, choose that lesson, select **Visual Evidence**, then click **Analyze lesson video**.

The authenticated API now supports:

- `POST /api/v1/lessons/{lesson_id}/visuals` with `{"max_frames":36}` to create a bounded background job.
- `GET /api/v1/lessons/{lesson_id}/visuals` for queued/running status or the saved manifest.
- `GET /api/v1/lessons/{lesson_id}/visuals/frame/{frame_name}` for a guarded JPEG preview.

Only an already indexed local video associated with the selected lesson is accepted.
The analyzer does not fetch arbitrary URLs from API requests. Existing production authentication
and same-origin protections remain in force. A single visual analysis runs at a time.
Frames and manifest remain on the persistent download volume; the transient in-memory job state
does not survive a service restart and should not be mistaken for a fully durable queue.

The UI displays original frame evidence and marks OCR and model descriptions unverified.
Playback seeks use the closest sampled timestamps, not frame-accurate audit claims.

## Remaining acceptance requirements

- The specific provided YouTube video's visual content is not verified without running on a host that can access it.
- Classification is heuristic: some code screenshots and diagrams will be unclassified.
- OCR cannot reconstruct error-free code automatically; diagrams require source-image review.
- Production release requires browser/user acceptance and full CI. Do not automatically merge this draft.
