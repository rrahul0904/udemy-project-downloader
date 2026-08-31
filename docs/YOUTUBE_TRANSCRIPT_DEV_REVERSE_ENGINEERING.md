# YouTubeTranscript.dev Reverse Engineering → Course Intelligence Platform

Date: 2026-08-31

## Objective

Use the public product behavior of YouTubeTranscript.dev as a reference for extending this repository from a local downloader + Study Lab into a transcript-backed learning platform. This is a product/architecture analysis, not a source-code copy. The implementation remains independent and keeps the existing authorization boundaries: only content the user owns or is authorized to archive is handled by the downloader.

## Public product decomposition

YouTubeTranscript.dev is best understood as several products sharing one transcript object and one account/credit system:

1. Transcript acquisition
   - YouTube URL/video ID ingestion.
   - Native/manual/automatic caption extraction.
   - ASR fallback when captions are unavailable.
   - Uploaded audio/video ASR.
   - Language selection and translation.
   - TXT / JSON / SRT / VTT outputs.

2. Durable transcript library
   - User-owned transcript history.
   - Search/filter by title, text, language, status and date.
   - Cached re-fetches.
   - Transcript deletion and language variants.

3. Bulk ingestion
   - Batch transcription.
   - Playlist resolution.
   - Channel resolution.
   - Per-video jobs plus aggregate batch state.
   - Async processing, polling and webhooks.

4. Learning layer
   - Structured timestamp-cited notes.
   - Flashcards tied to source timestamps.
   - Multiple-choice and short-answer quizzes with cited explanations.
   - Concept maps.
   - Transcript-grounded tutor/chat.
   - Spaced repetition and progress.
   - Markdown/PDF/Notion/Anki-style exports.

5. Transcript viewer
   - Video + synchronized transcript sidebar.
   - Click transcript segment to seek playback.
   - Search transcript.
   - Subtitle display controls.
   - Switch between caption/ASR sources.

6. Developer/distribution layer
   - REST API.
   - OpenAPI.
   - Node and Python SDKs.
   - MCP server.
   - Custom GPT integration.
   - Make/n8n templates.
   - Webhook verification and pagination helpers.

7. Commercial layer
   - Shared credit balance across transcript and learning features.
   - Free acquisition funnel.
   - Paid usage tiers based on credits, rate limits and bulk limits.

## Confirmed public technology signals

The public About page identifies the stack as Next.js, React, TypeScript, Vercel, Supabase, AI/ML, REST API and webhooks. The public API reveals a job-oriented architecture with synchronous fast paths, asynchronous ASR, batches, persistent transcript ownership, uploads via signed URLs, plan-level rate limits and webhook delivery.

This strongly suggests a separation similar to:

```text
Web client
  ↓
API / auth / billing
  ↓
Transcript service ── cache/database
  ├─ caption fast path
  ├─ upload path
  └─ ASR job path ── queue/worker ── object storage
  ↓
Transcript record
  ↓
AI transformations
  ├─ notes
  ├─ flashcards
  ├─ quiz
  ├─ concept graph
  └─ grounded tutor
```

The exact internal providers, queues, schemas and algorithms are not public and should not be claimed as known.

## What is strategically important

The transcript extractor itself is useful but relatively commoditized. The stronger product loop is:

```text
SOURCE
  ↓
TRANSCRIPT
  ↓
DURABLE COURSE/LIBRARY OBJECT
  ↓
MANY LEARNING ARTIFACTS
  ↓
ACTIVE RECALL + PROGRESS
  ↓
RETURN TO SOURCE WITH CITATIONS
```

A transcript therefore should not be represented as a disposable text file. It should be a first-class object with stable identity, segments, timestamps, language, provenance, source media and derived artifacts.

## Our stronger product position

We should not clone YouTubeTranscript.dev as a YouTube-only hosted transcript service.

Our differentiator is broader:

- Udemy + YouTube + local media + downloaded attachments.
- Offline/local-first ownership.
- Existing practice-test export.
- Existing Study Lab and scientific/research tools.
- Course/section/lesson hierarchy instead of a flat transcript history.
- Optional AI rather than mandatory cloud processing.
- Ability to connect transcript moments directly to downloaded course files and Study Lab tools.

Target product:

> A local-first Course Intelligence OS: archive authorized learning material, convert every lesson into searchable structured knowledge, study it with cited AI tools, and use the same knowledge through browser UI, API and agents.

## Domain model

The next architecture should converge on these stable objects:

```text
Course
  id
  source_type            udemy | youtube | local | import
  source_url
  title
  metadata
  sections[]

Section
  id
  course_id
  ordinal
  title
  lessons[]

Lesson
  id
  section_id
  source_id
  title
  media_path / media_url
  attachments[]
  transcript_versions[]

Transcript
  id
  lesson_id
  language
  source_kind            manual | auto | asr | imported
  text
  segments[]
  provenance
  created_at

TranscriptSegment
  id
  transcript_id
  ordinal
  start_ms
  end_ms
  text

StudyArtifact
  id
  lesson_id / course_id
  kind                   notes | flashcards | quiz | concept_map | summary
  source_transcript_id
  model/provider/version
  content
  citations[]

Citation
  transcript_id
  segment_start
  segment_end
  start_ms
  end_ms

StudyProgress
  artifact/card/question id
  status
  ease / mastery
  due_at
  attempt history
```

## Local-first architecture

Do not require Supabase/Stripe/cloud infrastructure for the local application.

Recommended local architecture:

```text
FastAPI
├─ downloader jobs
├─ course library API
├─ transcript parser/search
├─ study artifact API
├─ provider adapter API
└─ optional MCP/API surface

Local persistence
├─ downloads/                 media + source files
├─ data/app.db                SQLite
├─ SQLite FTS5                transcript lexical search
├─ optional local embeddings  semantic search
└─ exports/                   Markdown/PDF/Anki/etc.

Browser
├─ Downloader
├─ Course Intelligence
├─ Study Lab
└─ Settings / provider controls
```

SQLite should become authoritative for normalized course/lesson/transcript/artifact metadata while media remains on disk. Filesystem scanning remains an import/reconciliation path, not the final database model.

## Optional cloud scale architecture

Cloud sync should be an optional deployment mode, not a rewrite of local mode.

Suggested scalable path:

```text
Web / desktop client
  ↓
API gateway / auth
  ↓
Postgres / Supabase
  ├─ tenants/users
  ├─ course graph
  ├─ transcript metadata
  ├─ study artifacts
  └─ usage/billing ledger

Object storage
  ├─ uploaded media
  ├─ transcript exports
  └─ derived files

Job queue
  ├─ ASR
  ├─ embeddings
  ├─ notes
  ├─ flashcards
  ├─ quiz
  ├─ concept map
  └─ exports

Workers
  ├─ caption/import worker
  ├─ ASR worker
  ├─ AI transformation worker
  └─ indexing worker

Realtime/webhooks
  └─ job status + integrations
```

Vercel is suitable for the web surface and lightweight APIs, but long-running yt-dlp/ASR/media work must stay in durable workers outside short-lived serverless functions.

## AI/provider strategy

The product should not hard-code one model vendor.

Define interfaces:

```text
TranscriptionProvider
  transcribe(media, options) -> Transcript

GenerationProvider
  structured_notes(transcript) -> Notes
  flashcards(transcript) -> Deck
  quiz(transcript) -> Quiz
  concept_map(transcript) -> Graph
  answer(question, context) -> GroundedAnswer

EmbeddingProvider
  embed(chunks) -> vectors
```

Provider modes:

1. local-only / no AI
2. local model (e.g. user-configured Ollama-compatible endpoint)
3. user-supplied cloud API key
4. hosted managed provider in a future SaaS edition

Every generated learning artifact must preserve source citations to transcript segment IDs/timestamps.

## Search strategy

Phase 1: lexical search
- SQLite FTS5 over segment text.
- Filters by course, section, lesson, language and source.

Phase 2: hybrid search
- chunk transcripts by semantic boundaries.
- store embeddings.
- combine lexical + vector retrieval.
- rerank within selected course or all-course scope.

Grounded tutor retrieval should return exact segment IDs and timestamps, not just free-form text chunks.

## Learning system

### Notes
- detect topic shifts / chunk boundaries.
- produce heading + bullets.
- each bullet stores one or more segment citations.
- editable user overlay is separate from regenerated AI content.

### Flashcards
- fact/concept/procedure cards.
- each card stores source timestamp(s).
- SM-2/FSRS-style scheduling can be layered behind a stable review API.

### Quiz
- multiple-choice + short-answer.
- ensure topic coverage across the lesson rather than sampling only the beginning.
- explanation includes source citations.
- attempts feed mastery state.

### Concept graph
- concepts become nodes.
- explicit relationships become edges.
- each node/edge stores evidence citations.
- merge graphs across lessons into a course knowledge graph.

### Tutor
- explicit scope: current lesson / current course / all library.
- retrieved segments displayed with every answer.
- timestamp opens matching local media.
- separate optional web-research mode from source-grounded mode.

## API direction

Preserve the local UI but expose stable APIs so the same capabilities can be used by agents later.

Candidate API:

```text
GET  /api/v1/courses
GET  /api/v1/courses/{id}
GET  /api/v1/lessons/{id}
GET  /api/v1/transcripts/{id}
GET  /api/v1/transcripts/{id}/search?q=
POST /api/v1/lessons/{id}/artifacts/notes
POST /api/v1/lessons/{id}/artifacts/flashcards
POST /api/v1/lessons/{id}/artifacts/quiz
POST /api/v1/lessons/{id}/artifacts/concept-map
POST /api/v1/chat
GET  /api/v1/jobs/{id}
GET  /api/v1/review/due
POST /api/v1/review/{card_id}
```

Later MCP tools:

```text
list_courses
search_course
get_lesson_transcript
ask_course
create_study_kit
get_due_flashcards
```

## Implementation phases

### Wave 0 — foundation (started on feature/course-intelligence-platform)

- Add `/learn` Course Intelligence workspace.
- Scan compatible local transcripts into a course/lesson view.
- Parse VTT, SRT, JSON3 and plain text.
- Match local media when possible.
- Search transcript client-side/API-ready.
- Local notes and bookmarks.
- Preserve guarded local file serving.

### Wave 1 — durable course graph

- Add SQLite schema + migrations.
- Import yt-dlp `.info.json` metadata.
- Normalize Udemy course/section/lecture hierarchy.
- Normalize YouTube video/playlist hierarchy.
- Stable source IDs and transcript versions.
- Incremental filesystem reconciliation.
- FTS5 segment index.

### Wave 2 — transcript intelligence

- AI provider interface.
- structured cited notes.
- cited summaries.
- chapter/topic segmentation.
- cited flashcard generation.
- cited quiz generation.
- concept graph.
- regeneration/versioning/cost metadata.

### Wave 3 — active learning

- review queue.
- spaced repetition.
- quiz attempts and explanations.
- lesson/course mastery.
- daily study plan.
- weak-topic detection.
- progress dashboards.

### Wave 4 — grounded tutor + course-wide RAG

- chunk/index pipeline.
- FTS5 + vector hybrid search.
- current lesson / course / library scopes.
- strict citation contract.
- source timestamp jump.
- user notes and attachments included in retrieval.

### Wave 5 — import/export + integrations

- Markdown/PDF.
- Anki-compatible export.
- JSON backup/import.
- Notion optional integration.
- local REST API keys.
- MCP server.
- n8n/Make examples.

### Wave 6 — optional cloud mode

- accounts/tenancy.
- sync protocol.
- Supabase/Postgres.
- object storage.
- durable jobs/workers.
- billing/credits if commercialized.
- usage ledger and quotas.
- webhooks.

## Do not copy blindly

Avoid importing several characteristics that make sense for a hosted transcript API but not for our initial local product:

- Do not require credits for local parsing/search.
- Do not upload user media by default.
- Do not make cloud auth mandatory.
- Do not build large channel scraping before the course model is reliable.
- Do not couple learning artifacts directly to provider-specific responses.
- Do not generate uncited AI study material.

## Success criterion

The project is no longer a downloader when a user can:

1. archive an authorized Udemy course or YouTube lesson;
2. open it as a structured course;
3. search and navigate the transcript;
4. jump from text to the exact local media moment;
5. create/edit cited notes, flashcards, quizzes and concept maps;
6. ask questions grounded in the course;
7. review weak concepts over time;
8. export or access the same knowledge through API/MCP;
9. keep all of this local unless they explicitly enable cloud services.

That is the product we should build toward.

## Public references reviewed

- https://www.youtubetranscript.dev/
- https://www.youtubetranscript.dev/about
- https://www.youtubetranscript.dev/api-docs
- https://www.youtubetranscript.dev/pricing
- https://www.youtubetranscript.dev/viewer
- https://www.youtubetranscript.dev/edtech/youtube-to-notes
- https://www.youtubetranscript.dev/edtech/youtube-to-flashcards
- https://www.youtubetranscript.dev/edtech/youtube-to-quiz
- https://www.youtubetranscript.dev/edtech/pricing
