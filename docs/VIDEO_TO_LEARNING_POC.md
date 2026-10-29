# Video-to-Learning POC — Waves 1–2

## Real failure recovery: YouTube subtitles HTTP 429 (October 29, 2026)

The user's original \`--url ... --visuals\` run failed with \`Unable to download video subtitles for 'en': HTTP Error 429\`. This is a YouTube rate limit, not a Docker build error. Do **not** repeatedly retry requests or try to circumvent YouTube controls. The converter now looks for already downloaded local media/captions before requesting YouTube. If the media exists and is captionless, it asks for local ASR rather than hitting the network. Remote 429 errors produce a structured \`status: blocked\` result instead of a traceback.

To process the existing Snowflake video using the on-demand ASR Docker worker:

    # From the root of the cloned repository on the Mac
    git pull --ff-only
    find ./downloads -type f -iname '*fYgggzLEIFs*.mp4'

    # If no file appears, copy the previously downloaded authorized MP4
    # into this repository's ./downloads/ folder before continuing.
    docker compose --profile transcribe build transcript-worker
    docker compose --profile transcribe run --rm transcript-worker \
       python scripts/video_to_learning_poc.py \
       --url 'https://www.youtube.com/watch?v=fYgggzLEIFs' \
       --asr-fallback --visuals

The existing web service stays active; the optional worker installs \`faster-whisper\` in a separate CPU-only Docker image, and stores downloaded speech model weights in \`./data/.cache/huggingface\` on the Mac via the mounted \`/app/data\` volume. First-run model retrieval requires access to its model registry; no YouTube caption requests are made when an authorized matching MP4 is already mounted.

Results go under the same \`./downloads\` tree as the original MP4: \`<original_video_stem>.en.vtt\` plus a hidden \`.<original_video_stem>.en.learning\` directory containing the transcript and source-linked visual evidence. The original MP4 is preserved. Inspect \`quality-report.json\`; this is an **unverified** draft transcript, not guaranteed accurate teaching content.

If the transcriber Docker image fails to build for the Mac's CPU architecture, the same local speech recognition command can be run on the Mac host instead:

    brew install ffmpeg tesseract
    python3 -m venv .venv
    . .venv/bin/activate
    python -m pip install -r requirements.txt -r requirements-asr.txt
    find ./downloads -type f -iname '*fYgggzLEIFs*.mp4'

    # Replace the path with one printed by find, preserving quote marks.
    python scripts/video_to_learning_poc.py \
       --video-file '/actual/path/to/video [fYgggzLEIFs].mp4' \
       --asr-fallback --visuals

The separate \`transcript-worker\` service does not run during ordinary \`docker compose up\`. No external speech-recognition provider is used. A model download is needed the first time unless a usable copy was already cached.


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

## Actual user pilot evidence — October 29, 2026

The uploaded `fYgggzLEIFs` media was independently inspected (not automatically executed in the web app): 844.161 seconds, 1920x1080 AV1 video with Opus stereo audio. Its YouTube `.info.json` advertises English automatically generated captions and five chapters; the supplied files have **no VTT/SRT/JSON3 caption files**. This is therefore downloaded media, not a proven transcript or completed course conversion.

Existing `--url ... --visuals` tries captions first; an optional local ASR must be explicitly enabled for a captionless source. The base Docker image does not install faster-whisper and therefore is not an automatic captionless-transcription runtime. Do not tell users otherwise. Passing the URL alone to the ordinary downloader does NOT automatically generate the video-to-learning package.

The CLI defaults now honor the Docker runtime mounts `DOWNLOAD_DIR=/downloads` and `DATA_DIR=/app/data`; previous hardcoded repository-relative defaults were not durable in the Docker image.

The uploaded lecture's actual sampled frames include the six-step CoCo workflow (01:35), the Snowflake Cost Management and chat interfaces, the HTML report (09:25), visible HTML code (10:25), and illustrative anomaly detection (13:20). Samples are preliminary evidence and **do not verify the audio transcript**, exact code, completeness of the presentation, or factual applicability of displayed metrics.

From the CURRENT project root on a Mac, test caption-first conversion inside the rebuilt container:

    git pull --ff-only
    docker compose up -d --build
    docker compose exec course-intelligence python scripts/video_to_learning_poc.py --url 'https://www.youtube.com/watch?v=fYgggzLEIFs' --visuals

Alternatively, for an already downloaded authorized local MP4 without captions, use the optional ASR dependencies on the Mac host:

    brew install ffmpeg tesseract
    python3 -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt -r requirements-asr.txt
    find downloads -type f -name '*fYgggzLEIFs*.mp4'
    python scripts/video_to_learning_poc.py --video-file '/path/to/actual/downloaded/fYgggzLEIFs.mp4' --asr-fallback --visuals

The local ASR route downloads an open ASR model on first run and remains unverified until its output is checked against the actual audio. Replace the example `--video-file` path with the real path printed by `find`. Report `transcribed_unverified` is only a partial success. The learning guide is a timestamped extractive outline, not a fully synthesized curriculum. All personal learning use remains subject to source authorization.
