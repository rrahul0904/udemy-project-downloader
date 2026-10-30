# Reddit video POC — r/aiagents (October 30, 2026)

User-supplied source: https://www.reddit.com/r/aiagents/s/t94FoWZPvK

STATUS: source unverified. The linked Reddit short redirect has not resolved in the
available web tools; its actual title, identity, content, duration and captions
are UNKNOWN. No unrelated r/aiagents post is substituted.

## Stage 1: read actual video metadata without downloading media

    docker compose exec course-intelligence \
      python scripts/reddit_video_to_learning_poc.py \
      --url 'https://www.reddit.com/r/aiagents/s/t94FoWZPvK' \
      --metadata-only

Successful response: status=source_validated, with video id, title, duration,
resolved URL, and video stream. Status=blocked means no verified source.

## Stage 2: evidence extraction using the optional transcription worker

    docker compose --profile transcribe build transcript-worker
    docker compose --profile transcribe run --rm transcript-worker \
      python scripts/reddit_video_to_learning_poc.py \
      --url 'https://www.reddit.com/r/aiagents/s/t94FoWZPvK' \
      --asr-fallback --visuals --max-frames 48

If Reddit blocks shortlink resolution, use the canonical accessible
/r/aiagents/comments/<post-id>/... permalink from Reddit's own Share UI,
or supply the authorized MP4 with --media /downloads/<filename>.mp4.
No authentication, DRM, paywall, CAPTCHA or rate-limit bypass is attempted.

The worker writes real timestamped VTT, transcript exports, visual OCR and
frame files, and quality-report.json to mounted ./downloads/. A matched
transcript and video become a Course Intelligence lesson.

## Learning material, cloud processing and acceptance

The existing Learn This Video tab creates explanatory chapters using an
explicitly configured Ollama model after ingesting the video.
Cloud storage and hosted AI processing have NOT been deployed; this is still
the existing transcript-worker POC, with a cloud-compatible source intake.

Do not claim video-to-learning POC completion without verifying video identity,
speech accuracy, important visual details, source citations, and quality of
instructional chapters and worked exercises.

The 'source-intake.json' manifest captures whether the initial Reddit source
was actually resolved. Metadata-only intake does not create invented notes.