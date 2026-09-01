# Live Production Acceptance

This runbook is the final release gate after the Render Blueprint has been applied. It does not replace `docs/PRODUCTION_DEPLOYMENT.md`; it makes the live verification reproducible.

## Secrets

Never paste `APP_PASSWORD` into workflow inputs, issue comments, source files, or logs.

Create the GitHub Actions repository secret:

`PRODUCTION_APP_PASSWORD=<the current Render APP_PASSWORD>`

The production username is currently `admin`.

## 1. Core live smoke

From GitHub Actions, run **Production Acceptance** with:

- `production_url`: the HTTPS Render service URL
- leave `authorized_test_url` blank
- leave `cancel_test_url` blank
- `verify_persistence=false`

This verifies:

- public `/api/health`
- anonymous protection for `/`, `/learn`, `/lab`, readiness and job APIs
- authenticated `/`, `/learn`, `/lab`
- `/api/readiness`
- SQLite/data/download writability reported by readiness
- FFmpeg and yt-dlp reported by readiness
- course library API
- path traversal rejection
- unsupported downloader source rejection
- cross-origin mutation rejection
- production security headers

## 2. Full downloader + Course Intelligence acceptance

Use only an explicitly authorized/public YouTube URL with captions/transcript.

Run **Production Acceptance** again with:

- `production_url`: the production Render URL
- `authorized_test_url`: authorized transcript-bearing YouTube URL
- `verify_persistence=false`

Optionally set `cancel_test_url` to a slower authorized/public YouTube URL to verify real subprocess cancellation.

The workflow will verify a completed downloader job, persisted download inventory, Course Intelligence ingestion, transcript retrieval, lesson-scoped FTS, a durable note, and a durable bookmark.

When `authorized_test_url` is supplied, the workflow stores a non-secret artifact named:

`production-acceptance-state`

Record that workflow run ID. The artifact contains only acceptance identifiers/markers; it contains no production password.

## 3. Restart persistence gate

Restart the Render service without deleting or recreating the persistent disk.

Then run **Production Acceptance** with:

- `production_url`: the same production URL
- `verify_persistence=true`
- `persistence_source_run_id`: the run ID from step 2

The workflow downloads the prior acceptance-state artifact and verifies that the following survived the restart:

- completed job history
- downloaded output
- course/lesson discovery
- transcript association
- SQLite-backed note
- SQLite-backed bookmark
- transcript FTS hit

## 4. Redeploy persistence gate

Trigger a normal deployment from the current merged `main` SHA. Do not replace/delete the persistent disk.

After the deploy is healthy, rerun step 3 with the same source acceptance run ID.

All durable state must still be present.

## 5. SHA verification

Render exposes the deployed Git commit as `RENDER_GIT_COMMIT` in the service environment/deployment metadata. Confirm the deployed commit equals the current GitHub `main` SHA before closing Issue #4.

## 6. Close Issue #4

Only close Issue #4 after all of the following are documented as passing:

- final GitHub CI
- Render Blueprint deployment
- persistent disk attached at `/app/storage`
- `/api/health`
- authenticated `/api/readiness`
- production auth boundary
- legal/authorized real download
- progress/completion
- cancellation (using a suitable authorized test URL)
- Course Intelligence ingestion
- transcript + FTS
- notes + bookmarks
- Study Lab browser acceptance
- restart persistence
- redeploy persistence
- deployed SHA matches `main`
- backup procedure verified
- security smoke verified

If any item is not proven, production is not yet closed.
