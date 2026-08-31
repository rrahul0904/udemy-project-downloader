# Production Deployment

## Production topology

Course Intelligence is a stateful Docker application. A complete deployment must support all of the following in the same trusted environment or through equivalent durable services:

- the FastAPI web process;
- Python 3.12;
- `yt-dlp` subprocesses;
- FFmpeg;
- downloads that can outlive a deployment;
- `DATA_DIR/app.db` and `DATA_DIR/jobs.json` that can outlive a deployment;
- long-running download jobs;
- HTTPS and environment-secret management.

The minimum production topology is therefore:

```text
HTTPS
  |
  v
private authenticated FastAPI container
  |-- Downloader / yt-dlp / FFmpeg
  |-- Course Intelligence / SQLite FTS5
  `-- Study Lab
       |
       +-- persistent /app/data
       `-- persistent /downloads
```

Do **not** deploy only the UI or a short-lived serverless FastAPI function and call it production. Function-local filesystems and request-lifetime subprocesses do not satisfy the downloader or persistence requirements.

## Provider status

No compatible durable-container hosting account is currently connected to the implementation environment for this repository. The connected Vercel account is intentionally not used as the final deployment target for the current monolithic runtime because the product depends on long-lived `yt-dlp`/FFmpeg work and persistent filesystem state.

A production release therefore requires one external infrastructure action: provision a Docker-capable service with a persistent volume, then provide/deploy this repository to it. Railway, Render, Fly.io, a VM, Kubernetes, or another Docker host can work **only if** the selected plan supplies the runtime and persistence guarantees above. Provider names here are examples, not claims of an existing deployment.

## Local verification

Copy the example configuration and keep real credentials out of Git:

```bash
cp .env.example .env
```

For development:

```bash
docker compose up --build
```

The service is available at `http://127.0.0.1:8080`.

Canonical non-browser verification:

```bash
bash scripts/verify.sh
```

Full browser verification:

```bash
RUN_E2E=1 bash scripts/verify.sh
```

Container build verification:

```bash
VERIFY_DOCKER=1 bash scripts/verify.sh
```

## Required production environment

Set at least:

```text
APP_ENV=production
APP_USER=<private application username>
APP_PASSWORD=<long unique secret>
PUBLIC_BASE_URL=https://your-private-domain.example
DATA_DIR=/app/data
DOWNLOAD_DIR=/downloads
MAX_CONCURRENT_JOBS=2
JOB_RATE_LIMIT_PER_MINUTE=5
MAX_DOWNLOAD_BYTES=0
```

`APP_USER` and `APP_PASSWORD` are mandatory in production; startup fails closed without them.

The first launch deliberately uses a private HTTP Basic authentication boundary instead of exposing an unrestricted public downloader. Terminate TLS at the hosting platform/load balancer and never send Basic credentials over plaintext HTTP.

## Persistent volumes

Mount durable storage at both:

```text
/app/data
/downloads
```

`/app/data` contains the SQLite Course Intelligence database and persisted job history. `/downloads` contains archived media, transcripts, metadata, thumbnails and practice-test exports.

The container runs as UID/GID `10001`. The mounted volume must be writable by that identity. On a host-managed bind mount, initialize ownership as appropriate for that platform before starting production.

Never mount a cookie export as a permanent secret. Uploaded cookies are copied to `DATA_DIR/cookies` only for the job and removed after use; stale cookie files are also removed at application startup.

## Database and migrations

SQLite initializes automatically at `DATA_DIR/app.db`. Schema migrations are recorded in `schema_migrations` and are idempotent.

Current production schema version: `1`.

Transcript content is indexed in SQLite FTS5. Course ingestion is idempotent and reindexes a transcript when its parsed content hash changes.

Before an application upgrade, back up:

```text
/app/data/app.db
/app/data/jobs.json
/downloads
```

For SQLite backup while the application is live, use the SQLite backup API or stop writes briefly and copy the database plus WAL files consistently. Do not copy only `app.db` while ignoring an active WAL.

## Build

From a clean checkout:

```bash
docker build -t course-intelligence:<git-sha> .
```

The image installs FFmpeg and all pinned Python dependencies, creates an unprivileged application user, and exposes port `8000`.

## Start

A typical platform command is already baked into the image:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*
```

Attach the two persistent volumes before starting the container.

## Health checks

Public liveness:

```text
GET /api/health
```

Expected response:

```json
{"status":"ok"}
```

Authenticated readiness:

```text
GET /api/readiness
```

Readiness verifies:

- SQLite access and migration version;
- writable data storage;
- writable download storage;
- FFmpeg availability;
- `yt-dlp` availability.

A `503` means the deployment should not receive production traffic.

## Production acceptance

After deploying the exact merged `main` SHA, verify with authenticated browser and HTTP requests:

1. `/` loads the downloader.
2. `/learn` loads Course Intelligence.
3. `/lab` loads Study Lab.
4. `/api/health` returns `200` without credentials.
5. `/api/readiness` returns `200` with credentials.
6. Anonymous access to `/`, `/learn`, `/lab` and job APIs returns `401`.
7. A legal/public YouTube fixture or other authorized media can create a job, stream status through polling, complete, and appear in `/api/downloads`.
8. Cancellation terminates an active test job.
9. A resulting transcript is ingested into Course Intelligence.
10. FTS search finds a known transcript phrase.
11. Notes and bookmarks remain after page refresh and application restart.
12. Study Lab can load a compatible file from the download inventory.
13. Browser console and server logs show no blocking errors.
14. Restart the container and verify the SQLite state and downloaded media remain.

Never use protected/unauthorized media as an acceptance test.

## Rollback

Deployments should be tagged by Git SHA.

To roll back:

1. stop new download submissions;
2. wait for or explicitly cancel running jobs;
3. back up `DATA_DIR` and `/downloads`;
4. redeploy the prior known-good image/SHA against the same persistent volumes;
5. call `/api/health` and `/api/readiness`;
6. smoke-test `/`, `/learn`, and `/lab`;
7. re-enable traffic.

Schema version 1 is backward-simple, but a future migration that is not backward-compatible must ship a documented database rollback/restore procedure before deployment.

## Known launch limitations

- The first production authentication boundary is intended for a private/personal deployment, not public multi-user SaaS.
- Job metadata is persisted, but subprocesses cannot survive a container restart. Jobs that were queued/running are marked failed with an explicit restart message and must be retried.
- SQLite is appropriate for the current single-instance deployment. Do not scale multiple writers against a shared SQLite file.
- AI study kits, vector RAG, MCP, billing and multi-tenancy are intentionally outside this production-closeout wave.
