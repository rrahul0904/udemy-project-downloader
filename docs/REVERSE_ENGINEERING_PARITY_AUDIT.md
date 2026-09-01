# Reverse Engineering Parity Audit

Date: 2026-09-01

This document is the current source of truth for product-parity work. `docs/YOUTUBE_TRANSCRIPT_DEV_REVERSE_ENGINEERING.md` remains historical context.

## References re-reviewed

### YouTubeTranscript.dev

Public surfaces reviewed on 2026-09-01:

- home and product navigation
- V2 API documentation / OpenAPI surface
- interactive viewer
- Study notes
- Study flashcards
- Study quiz
- public SDK/MCP/integration descriptions

The current public V2 API exposes single-video transcription, caption/ASR source selection, ASR fallback, uploaded-media transcription, word/paragraph/timestamp formatting, ASR intelligence options, async jobs, batch transcription, transcript listing/filtering, transcript language/source variants, translation, deletion, playlist resolution/history, channel resolution/history, OpenAPI, SDKs, MCP, Make and n8n integrations.

The viewer publicly describes source switching, synced transcript auto-scroll, click-to-seek playback and subtitle customization.

The Study product publicly describes structured timestamp-cited editable notes, flashcards with citations and spaced repetition/mastery, and mixed MCQ/short-answer quizzes with cited explanations and score tracking.

### STEMKit

The current public `LD-Shell/stemkit` repository documents 18 research tools plus 3 workflow helpers. Its `@stemkit/core` layer contains 16 DOM-free computational modules and the upstream README currently reports 1,077 tests with independent numerical/reference validation.

## Current product state

### Strong / production foundation

- authorized Udemy/YouTube downloader
- explicit authorization boundary and URL guard
- persistent downloader job history and cancellation
- practice-test extraction path
- Docker + FFmpeg + yt-dlp runtime
- production Basic Auth and security boundary
- SQLite Course Intelligence store
- VTT/SRT/JSON3/TXT/Markdown parsing
- FTS5 transcript search
- local-media association
- durable personal notes and bookmarks
- 21 Study Lab surfaces
- Render Blueprint and live acceptance automation

### Structural P0 gaps

1. `sections` exists but current ingestion does not normalize a real Course → Section → Lesson hierarchy.
2. The v1 transcript schema allows only one transcript row per lesson, so manual/auto/ASR/imported/translated variants cannot coexist.
3. Transcript provenance/source kind/version is not first-class.
4. Attachments are not first-class Course Intelligence objects.
5. `study_progress` exists but is not yet a complete active-learning workflow.
6. The local media experience is open-in-new-tab rather than a synchronized embedded player + transcript sidebar.
7. Normalized transcript export does not yet expose TXT/JSON/SRT/VTT through a stable API.

### Learning P1 gaps

- provider abstraction for optional generation/transcription/embeddings
- cited generated notes and summaries
- flashcards and editing
- spaced repetition / mastery
- mixed-format quizzes, attempts, explanations and score history
- concept graph
- grounded tutor
- hybrid retrieval
- study dashboard / weak-topic workflow

### Developer P2 gaps

- versioned `/api/v1`
- explicit OpenAPI production surface
- MCP server
- backup/import format
- richer export formats
- automation examples

### STEMKit fidelity gaps

All reference tool categories are represented, but the current Study Lab is intentionally an MVP rather than scientific-equivalence. Highest-value gaps include a DOM-free reusable computational core, deeper statistics/outlier/fitting coverage, richer PDB/GRO/XYZ structural operations, SLURM/PLUMED validation, broader unit coverage, robust BibTeX/ISO-4 handling, calibrated digitization and independent numerical fixtures.

## Product decisions

The product remains a local-first Course Intelligence OS, not a shallow hosted clone.

Commercial credits, Stripe billing and hosted multi-tenancy remain `INTENTIONALLY_EXCLUDED` for the private/local release. They must not block structural correctness or the learning loop.

Channel-wide acquisition remains constrained until a preview/select/limit workflow exists; accidental unlimited channel scraping is not an acceptable parity shortcut.

AI remains optional. Local parsing, FTS, transcript viewing and personal study state must work without an AI provider.

## Execution order

### P0 — structural correctness

- normalized section hierarchy
- transcript variants/provenance + migration
- attachments
- synchronized viewer
- transcript exports
- real progress state

### P1 — learning loop

- provider abstraction
- cited notes/summaries
- flashcards
- quiz
- concept map
- tutor
- spaced repetition/mastery
- optional hybrid search

### P1 — scientific fidelity

- Study Lab core extraction
- substantive numerical fixtures
- highest-value STEMKit parity gaps

### P2 — portability and integrations

- API v1/OpenAPI
- backup/import
- exports
- MCP
- automation examples

### P3 — intentionally deferred scale/commercial work

- hosted multi-tenancy
- credits/billing
- cloud sync
- large hosted worker architecture

## Traceability rule

`docs/parity-matrix.json` is machine-readable. Every parity claim must identify implementation and test evidence. Every `MISSING` item must have a tracking plan. CI validates this contract through `tests/test_parity_matrix.py`.

A feature name in the UI is not proof of parity. A capability is only `EXACT` or `FUNCTIONAL_EQUIVALENT` when behavior exists and a test demonstrates it.
