# STEMKit Phase B: regression.js curve-fitting slice

This document records the smallest dependency-injected Phase B slice implemented after the dependency-free scientific core.

## Scope implemented

- exact STEMKit `src/core/vendor.js` dependency registry
- exact STEMKit `src/core/curve-fitting.js` analytical module
- exact regression.js bundle vendored by the reviewed STEMKit commit and identified as regression.js 2.0.1
- Study Lab adapter exposing linear, quadratic, cubic, exponential, power, and logarithmic fits
- original-scale R², adjusted R², RMSE, model-adequacy warnings, domain validation, and the upstream linearisation warning for exponential/power fits
- local browser plotting of the observed data and fitted curve
- browser E2E for nonlinear selection, metrics, plot rendering, linearisation disclosure, and domain errors
- deterministic Node golden verification, including Git blob provenance checks and upstream numerical fixtures

## Provenance pins

Reviewed STEMKit commit: `edb2cb6afdb25a4680d7e4f831558b00f47e6980`

| Artifact | Expected Git blob SHA |
| --- | --- |
| `vendor.js` | `a22bf1c156b87bc29159913138e5e83bce6fec68` |
| `curve-fitting.js` | `a5e6e030cd3ee9579623ce6f5cc3f19ad5ba336b` |
| `regression.min.js` | `b2f8ecdac5942053bd01b5443b499b3ad6e0c039` |

The golden verifier fails if any of those files drift from the reviewed upstream blobs.

## Legacy fallback boundary

`lab.js` still contains the pre-existing straight-line implementation. The Phase B adapter is the primary path whenever the local regression.js bundle registers successfully. The old line fit is intentionally allowed only as a dependency-load fallback, and the UI labels that state as `Legacy linear fallback only` rather than silently claiming STEMKit parity.

Removing that fallback is optional cleanup; it is not counted as migrated analytical behavior.

## Certification gate

This slice is implemented, but it is certified only when the PR's exact current head passes the repository's canonical `verify` job (including `scripts/verify_stemkit_curve_golden.mjs`) and the browser-smoke job (including `tests/e2e/stemkit-curve.spec.mjs`). A pending or failed exact-head run must not be described as certified.

## Explicitly still incomplete

This slice does **not** implement or certify:

- jStat-backed statistics, outliers, or error bars
- Papa Parse-backed data cleaning
- bibtexParse-backed BibTeX parsing/deduplication
- course-aware persistence, saved scientific artifacts, lesson/course metadata, or provenance export

Those remain the next parity boundaries.
