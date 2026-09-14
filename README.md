# Course Intelligence

A local-first, Docker-hosted learning workspace that combines an authorized Udemy/YouTube media downloader, durable transcript intelligence, and a 21-tool Study Lab.

This project is for content you own, created, or are otherwise authorized to access and archive for personal use. It does **not** bypass DRM, paywalls, account restrictions, or access controls.

## Product surfaces

| Route | Surface | Purpose |
| --- | --- | --- |
| `/` | Downloader | Archive supported authorized Udemy/YouTube media, subtitles, metadata, thumbnails and available Udemy practice tests. |
| `/learn` | Course Intelligence | Organize archived transcripts into courses/lessons, search them, navigate timestamps, and persist notes/bookmarks. |
| `/lab` | Study Lab | Use 21 local data, scientific, citation, molecular and study utilities with compatible downloaded files. |

## Local run

```bash
cp .env.example .env
docker compose up --build
```

Open `http://127.0.0.1:8080`.

Persistent local data:

```text
./downloads  -> archived course/media material
./data       -> SQLite database + durable job history
```

## Course Intelligence

Course Intelligence uses SQLite as its durable local source of truth. On library refresh it idempotently ingests compatible downloaded transcripts and available `.info.json` metadata.

Supported transcript inputs:

- VTT
- SRT
- JSON3
- TXT
- Markdown

The data model includes courses, sections, lessons, transcripts, transcript segments, notes, bookmarks, study progress and schema migrations. Transcript segments are indexed with SQLite FTS5 for lesson-, course- and library-wide search.

Notes and bookmarks are server-side durable state; they survive browser refreshes and application restarts. Timestamped search/bookmark results link back to the relevant lesson moment when matching local media exists.

The larger product direction—cited AI notes, flashcards, quizzes, concept maps, grounded tutor, spaced repetition and MCP/API access—is documented in `docs/YOUTUBE_TRANSCRIPT_DEV_REVERSE_ENGINEERING.md` and intentionally remains outside the production-closeout wave.

## Study Lab

Study Lab remains an additive local-first workbench with 21 lightweight tools spanning:

- data cleaning, descriptive statistics, outlier detection, linear fitting, error bars, plotting and plot digitization;
- XVG parsing, PDB inspection/coordinate translation and starter molecular-dynamics workflows;
- BibTeX cleanup/deduplication, DOI → BibTeX, journal abbreviation, LaTeX tables and equation snippets;
- scientific unit conversion;
- Pomodoro, decision-matrix and first-order kinetics helpers.

Compatible files under the download store are loaded through the existing guarded `/files/{relative_path}` route. Most Study Lab computations run entirely in browser JavaScript. DOI → BibTeX reaches Crossref only after explicit user action.

Study Lab is a learning/research helper, not a claim of publication-grade numerical parity. See `docs/STUDY_LAB.md`.

## Downloader

Supported URL shapes include:

- Udemy course URLs;
- YouTube video URLs, Shorts and live URLs;
- explicit YouTube playlist URLs.

YouTube channel-wide downloads remain intentionally disabled by the URL guard to avoid accidental bulk jobs.

The downloader uses bounded concurrency, durable job history, cancellation, explicit restart semantics, a download archive, bounded log history, optional per-file size limits, disk-space checks and temporary cookie cleanup.

### Source authentication

The downloader supports:

- no source cookies for public YouTube;
- local browser cookies when the app is running directly on a compatible local machine;
- temporary Netscape-format `cookies.txt` upload for an authorized user/session.

Udemy downloads require an authorized browser session or cookies file. Private/restricted YouTube content likewise requires normal account authorization. Uploaded cookie material is temporary and is removed after the job; stale app cookie files are removed at startup.

## Production security boundary

The first production release is deliberately a **private/personal application**, not an anonymous public downloader.

When `APP_ENV=production`:

- `APP_USER` and `APP_PASSWORD` are required at startup;
- all product and sensitive API routes require HTTP Basic authentication;
- `/api/health` remains minimal and public for platform liveness;
- state-changing cross-origin requests are rejected;
- security headers/CSP are enabled;
- job creation is rate-limited;
- upload and query sizes are bounded;
- absolute storage paths are not exposed by the production download inventory.

Always terminate TLS/HTTPS in front of the container. Do not use Basic authentication over plaintext HTTP.

## Production runtime

The application requires more than a static/serverless web deployment. A complete production host must support:

- Docker or equivalent long-running Python runtime;
- FFmpeg;
- `yt-dlp` subprocesses;
- persistent `/downloads` storage;
- persistent `/app/data` storage;
- long-running download jobs;
- HTTPS and environment-secret management.

See `docs/PRODUCTION_DEPLOYMENT.md` for the exact runtime, persistence, backup, rollback and production acceptance requirements.

## Health and readiness

```text
GET /api/health
GET /api/readiness
```

`/api/health` is liveness-only. Authenticated `/api/readiness` verifies SQLite, writable persistent storage, FFmpeg and `yt-dlp` before the instance should receive traffic.

## Verification

Canonical checks:

```bash
bash scripts/verify.sh
```

Browser E2E:

```bash
RUN_E2E=1 bash scripts/verify.sh
```

Docker build:

```bash
VERIFY_DOCKER=1 bash scripts/verify.sh
```

CI runs independent verification, Playwright browser smoke and production image build jobs.

## Reference notes

The downloader work was informed by public MIT-licensed downloader references, but DRM/Widevine-oriented paths were intentionally excluded.

Study Lab's inventory was informed by the MIT-licensed STEMKit project (`LD-Shell/stemkit`) and independently implemented; see `docs/STUDY_LAB.md` for attribution and scope.

Course Intelligence was informed by public product behavior/documentation from YouTubeTranscript.dev. This repository does not copy that product's source code or claim knowledge of non-public implementation details.
