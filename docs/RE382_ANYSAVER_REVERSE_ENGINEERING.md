# RE-382 — AnySaver reverse-engineering dossier

Status: Phase A implementation started 2026-10-03  
Canonical issue: https://github.com/rrahul0904/udemy-project-downloader/issues/23

## 1. Source ledger

Primary donor evidence:

- Supplied Reddit share: https://www.reddit.com/r/SideProject/s/AFZkf7KsJI
- Resolved launch post: https://www.reddit.com/r/SideProject/comments/1wwv1zc/i_got_tired_of_online_video_downloaders_with_5/
- Live product: https://anysaver.app/
- Same-day crosspost with one visible UX/watermark comment: https://www.reddit.com/r/IMadeThis/comments/1wwv6bx/i_got_tired_of_online_video_downloaders_with_5/

A public repository with a similar AnySaver name was found during research, but no verified authorship/linkage to `anysaver.app` was established. It is therefore **not** treated as source code for this donor.

## 2. What is verified from the public surface

The creator describes the target experience as: paste a public link, choose an output, download it without ads, popups, redirect loops, fake buttons, an account, or an AnySaver-added watermark.

The live site publicly claims:

- a single paste box with platform auto-detection;
- 18 supported platforms;
- video/audio/photo variants depending on source;
- HD/SD MP4 choices where available;
- MP3 preparation on the server;
- public-content-only behavior;
- no platform credentials requested;
- temporary handling/deletion of server-prepared files;
- mobile and desktop browser operation.

These are **product claims**, not evidence of AnySaver's private architecture, implementation libraries, extraction methods, storage internals, or platform-specific bypass techniques.

## 3. Feedback incorporated

The launch post itself names the existing-market pain clearly: deceptive buttons, redirects, ads, account friction and a sketchy trust model. The creator asks specifically for feedback on breakage, quality, UI confusion and missing platforms.

A same-day crosspost received a positive comment about the straightforward paste-and-grab experience and asked about TikTok watermark stripping. We adopt the UX lesson but explicitly reject watermark-removal/circumvention as a product requirement. Creator- or platform-embedded marks remain untouched.

## 4. Product thesis for our portfolio

Do **not** create a disconnected AnySaver clone.

This repository already contains the harder reusable foundation for authorized media archival: bounded download jobs, durable history, cancellation/restart semantics, FFmpeg/yt-dlp readiness checks, persistent storage, rate limiting, temporary cookie cleanup, and explicit DRM/access-control exclusions.

AnySaver is therefore a capability donor for a new **normalized multi-source media saver layer**:

1. one URL intake;
2. deterministic source detection;
3. rights/policy gate;
4. source adapter registry;
5. normalized media metadata + variants;
6. transfer/preparation job;
7. artifact delivery;
8. cleanup/expiry evidence.

## 5. Core domain contracts

Planned domain model:

- `SourceSpec`: source identity, host aliases, claimed capabilities, policy mode, implementation state.
- `MediaItem`: normalized title, source, source URL, creator metadata, thumbnail and source identifiers.
- `MediaVariant`: video/audio/photo/GIF variant with container, quality, dimensions, bitrate and provenance.
- `PolicyDecision`: allow/refuse/needs-authorization with reason and evidence.
- `TransferJob`: requested variant, lifecycle state, bounded resource policy and receipts.
- `Artifact`: local/temporary output with size, content type, digest and expiry/cleanup state.

Phase A deliberately implements only `SourceSpec`, capability metadata and network-free source detection.

## 6. Capability matrix from donor claims

| Source | Donor-claimed surface | Repository state after Phase A |
| --- | --- | --- |
| Instagram | video, audio, photos, carousels | research only |
| TikTok | video, audio, photo posts | research only |
| YouTube | video/Shorts, audio | existing authorized path; adapter wrapper not yet built |
| Facebook | video/reels, audio | research only |
| X/Twitter | video, audio, photos/GIFs | research only |
| Pinterest | video, audio, photos | research only |
| Threads | video, photos | research only |
| Snapchat | Spotlight video, audio | research only |
| LinkedIn | video, audio | research only |
| Dailymotion | video, audio | research only |
| Twitch | clips, audio | research only |
| Bluesky | video, audio | research only |
| ShareChat | video, photos | research only |
| Moj | video | research only |
| Loom | shared video, audio | research only |
| Giphy | MP4/GIF | research only |
| Tenor | MP4/GIF | research only |
| Apple Podcasts | episode audio | research only |
| Udemy | existing repository capability, outside AnySaver matrix | existing authorized-session path |

The registry is intentionally evidence metadata. A row does not mean an adapter exists.

## 7. Security architecture

A public URL-ingestion product is an SSRF boundary first and a downloader second. Before any new generic fetcher is integrated, it must have:

- only `http`/`https` schemes;
- no embedded credentials;
- standard web ports only unless explicitly justified;
- DNS resolution that rejects loopback, private, link-local, multicast, reserved and internal destinations;
- address revalidation after DNS changes and on every redirect;
- redirect count limits;
- request/response timeouts;
- response byte ceilings and MIME allowlists;
- sanitized filenames and isolated temporary directories;
- FFmpeg wall-clock/output limits;
- source-scoped rate limits/circuit breakers;
- deterministic cleanup and expiry receipts.

The Phase A detector performs **no DNS lookup and no request**. Host classification alone never means a URL is safe to fetch.

## 8. Rights and anti-circumvention boundary

Supported product direction:

- media the user owns or created;
- media the user is otherwise authorized to archive;
- public/official access paths where the source permits them;
- normal user authorization for the existing private/personal flow.

Explicitly excluded:

- DRM/paywall/access-control bypass;
- private/follower-only scraping outside normal authorization;
- CAPTCHA/anti-bot bypass;
- signature/obfuscation/restriction evasion;
- automated bulk/rate-limit evasion;
- creator/platform watermark removal.

## 9. Roadmap

### Phase A — source contracts and detector

Deliverables:

- immutable source registry;
- hostname/alias classification;
- explicit implementation state (`existing` vs `research_only`);
- explicit policy mode;
- malicious-lookalike and malformed-URL tests;
- no network/download behavior.

### Phase B — fetch safety primitives

- IP/DNS/redirect validation module;
- deterministic fake resolver/client fixtures;
- private/link-local/loopback/rebinding/redirect negative tests;
- response size/time/MIME policy.

### Phase C — generic direct-media adapter

Only for explicitly authorized/public direct media URLs after Phase B gates. Produce normalized `MediaItem` and `MediaVariant` objects with no source-specific bypass logic.

### Phase D — normalized preview UI

- one-box intake;
- detected source badge;
- policy/authorization status;
- available variant cards;
- transparent processing state;
- one clear download action per variant;
- keyboard/mobile/reduced-motion coverage.

### Phase E — wrap existing adapters

Refactor current YouTube/Udemy paths behind the normalized contracts without weakening the existing URL guard, authorization behavior, bounded jobs or production security boundary.

### Phase F — evidence-gated source expansion

For each additional platform: official/public capability research, adapter-specific policy decision, synthetic fixtures, negative tests, runtime evidence and explicit capability-matrix update. Unsupported sources remain unsupported rather than falling back to risky generic extraction.

### Phase G — bounded media preparation

Optional MP3/transcode jobs for authorized inputs only, with FFmpeg limits, content hashing, temporary artifacts, TTL cleanup and durable receipts.

### Phase H — productization and verification

- source health/telemetry without storing sensitive pasted URLs unnecessarily;
- rate limits/circuit breakers;
- cleanup reconciliation;
- desktop/mobile browser tests;
- exact-head hosted verification before any production-readiness claim.

## 10. Phase A acceptance tests

- known donor sources classify deterministically;
- existing YouTube/Udemy are marked `existing`;
- donor-only sources are marked `research_only`;
- aliases such as `youtu.be`, `twitter.com`, `fb.watch` resolve to canonical sources;
- true subdomains resolve while lookalikes such as `youtube.com.evil.example` fail;
- missing scheme, unsupported scheme, embedded credentials, invalid/nonstandard ports and unknown hosts fail;
- detector performs no network activity;
- existing downloader path is unchanged.

## 11. Truthful current status

As of the start of RE-382, the reverse-engineering research, portfolio mapping, issue, Phase A branch, source-contract module and focused unit tests exist. No new social-platform adapter, public anonymous downloader, hosted Preview, or production deployment is claimed until those artifacts are implemented and independently verified.
