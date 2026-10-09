# Pluck donor → Course Intelligence media workbench

Research snapshot: 2026-10-09

## Status

- SOURCE / EVIDENCE: complete for the supplied Reddit launch, same-author public crossposts discovered during research, upstream public repository surface and current release head.
- DEDUPE: complete. This is a capability donor to Course Intelligence, not a new standalone clone.
- RECONSTRUCTION / PRODUCT BOUNDARY: complete at public-behavior level.
- BUILDING: Phase A contract slice in progress on `reverse/pluck-media-processing-contracts`.
- RUNNABLE / UAT / PRODUCTION VERIFIED / SHIPPED: not claimed.

## Source ledger

Primary supplied source:
- Reddit: `https://www.reddit.com/r/coolgithubprojects/comments/1x1rtq5/i_made_pluck_a_free_native_mac_app_for_ytdlp_with/`

Same-author public launch/crosspost evidence reviewed:
- `r/foss` launch for v1.10.0 local processing capabilities.
- `r/SwiftUI` crosspost, including a membership-video question and creator guidance to use an authorized browser session.
- earlier `r/sideprojects` launch emphasizing a simple one-field native workflow; visible feedback notes that CLI remains preferable for some power users.
- `r/MacStack` crosspost includes a positive working report; this is anecdotal feedback, not our runtime proof.

Upstream reference:
- repository: `https://github.com/Astrofrogger/pluck`
- reviewed release head: `e7c8d30d885e27e0fec0b791973cfa7caed3c4de` (`Release 1.10.0`)
- feature commit immediately before release: `72d3cbd0e69ff8b44216784360dc8f2825c633a7`

## Evidence boundary

Directly observed in public material:
- native macOS acquisition front end around yt-dlp/FFmpeg;
- local file import/conversion and batch operations;
- transcript/subtitle/translation and speaker-label workflows;
- silence/filler removal, audio cleanup, upscaling/interpolation, person/background processing and privacy blur;
- summaries, chapters, shorts/caption rendering, transcript export and a media library;
- capability gating by OS/hardware and on-demand third-party model/tool installation.

Not independently verified by us:
- quality or accuracy of the advanced media transforms;
- actual network-zero behavior of every local-AI path;
- model/runtime performance across supported Macs;
- security claims from upstream scanning;
- parity on every source supported by yt-dlp;
- the exact behavior of browser-cookie handling on real accounts.

A root/general project license was not identified in the reviewed repository root snapshot. Third-party components have separate notices. Therefore upstream Pluck source, UI, branding and assets are reference-only for this work unless rights are clarified. This project implements original contracts and code from public behavior and existing owned architecture.

## Dedupe / canonical ownership

Primary canonical owner: `rrahul0904/udemy-project-downloader` (Course Intelligence).

Existing work reused rather than rebuilt:
- RE-382 AnySaver line: source detection, bounded public/authorized source support, fetch-safety primitives, one-box acquisition UX and exact-head CI evidence.
- Issue #20 LetScribe line: safe local media intake, FFmpeg normalization, ASR seam, diarization/translation, non-destructive transcript editing and rich exports.

Secondary capability destinations, not owners of this donor:
- AnyDub: speech/dubbing/model capability abstractions.
- Open Music Studio: stems/music processing.
- Faceless Content Creator: downstream caption/short rendering consumer.

## Competitive / alternative audit

The acquisition shell itself is not a unique moat. Current public alternatives include native SwiftUI/macOS yt-dlp front ends, long-running MacYTDL, and cross-platform wrappers such as Tauri/Electron/Python GUIs. Commercial Mac products such as Downie also compete on a polished paste-and-download workflow.

The useful differentiation for our roadmap is therefore **not** "another yt-dlp GUI". It is the combination of:
- one normalized acquisition contract across our already-owned source adapters;
- a local/user-supplied `MediaAsset` identity;
- restartable processing jobs with deterministic provenance receipts;
- transcript/search/course intelligence already present in our platform;
- a capability registry that makes hardware/dependency/policy limits truthful;
- a durable media library and derived-asset lineage;
- optional downstream AI/media transforms that can be independently certified.

This avoids competing on visual wrapper parity and instead turns acquisition into one entry point for a broader evidence-backed media workbench.

## Public capability reconstruction

### Acquisition

Input → source classification → authorization policy → bounded yt-dlp/owned adapter → normalized media metadata → durable job → persisted asset.

Key requirements carried into our product:
- explicit authorization boundary;
- bounded per-item jobs;
- resume/cancel/retry semantics;
- truthful source support status;
- no DRM/paywall/access-control bypass;
- browser-session use, if supported later, must be explicit, local and non-leaking.

### Local processing

Persisted/local media → capability preflight → processing plan → bounded worker → validation → derived asset + provenance receipt.

Independent contract surface:
- `MediaAsset`
- `MediaProcessingCapability`
- `ProcessingJob`
- `ProcessingReceipt`
- `BatchProcessingReceipt`

Every derived asset must be attributable to its input identity, operation id/version, settings and output identity. Failed or cancelled work cannot be presented as completed.

### Library

The useful abstraction is not Pluck's UI; it is a durable local media inventory:
- canonical asset identity/hash;
- source/provenance;
- derived-asset lineage;
- tags/collections;
- duplicate detection;
- missing-file state;
- size/storage accounting;
- transcript/search attachment.

## Feedback converted into requirements

1. **Simple default path:** same-author launch discussions emphasize one-field paste/search and a clean native UI. Our web product should keep a low-friction acquisition path while putting advanced operations behind progressive disclosure.
2. **Power-user path:** visible feedback says CLI users may still prefer the terminal. We should preserve an API/CLI-friendly job contract rather than forcing all capability through GUI-only flows.
3. **Authorized membership/private access:** a public crosspost asks about channel-membership media; creator points to browser-session cookies. Our policy remains fail-closed: any authenticated source path must use explicit user authorization, bounded credentials and no access-control circumvention.
4. **Trust/signing:** public Mac discussion flags the unsigned app and a repository trust bot flags no root license/security policy. For our project this becomes release hygiene: explicit license/provenance, security boundary, exact-SHA CI and deployment evidence.

## Product boundary

### Reuse
- existing downloader/adapters and source policy;
- existing FFmpeg/yt-dlp runtime;
- existing durable jobs, storage, transcript indexing and exports.

### Improve
- unified `MediaAsset` identity for acquired and user-supplied files;
- explicit dependency/hardware/policy capability states;
- deterministic processing receipts;
- batch partial-failure semantics;
- derived-asset lineage and library storage accounting.

### New, phased independently
- safe trim/remux/transcode/audio-extract adapters;
- local ASR/diarization/translation integrated with Issue #20;
- silence/filler edit plan + EDL export;
- audio cleanup/loudness adapter;
- privacy/background and upscale/interpolation adapters;
- stems and shorts as later capability adapters.

### Explicitly omitted
- Pluck branding/UI/source/assets;
- DRM/paywall/access-control bypass;
- watermark removal;
- unrestricted internet-facing downloader;
- unbounded credential/cookie ingestion;
- unsupported parity claims for Apple-only frameworks.

## Shipping contract

P0 — evidence, dedupe, clean-room boundary and current-main baseline.

P1 — contract-only slice with deterministic tests and fail-closed capability registry.

P2 — real FFmpeg transforms on authorized/local fixtures with path/size/time bounds, cancellation and restart semantics.

P3 — library/provenance model and UI/API preview.

P4 — ASR/diarization/translation through Issue #20 seams with quality/provenance receipts.

P5 — advanced optional processing adapters, each gated by model/tool license, hardware availability and measured quality.

P6 — batch workflows with bounded concurrency, partial failure and retry.

P7 — exact-head CI, browser smoke, Docker/runtime certification, persistence/restart and authorized end-to-end fixture evidence.

P8 — deployment/UAT only after exact SHA, security, provenance and rights gates pass.

## Current evidence

Canonical coordination issue: `rrahul0904/udemy-project-downloader#27`.

Implementation branch: `reverse/pluck-media-processing-contracts`, branched from main `e5fd80f72da4f29f02f68b3ca755aede4ccccef2`.

Phase-A source began with `app/media_processing.py` and `tests/test_media_processing.py`. Remote exact-head CI is required before this phase can be called verified.
