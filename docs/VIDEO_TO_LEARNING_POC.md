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
