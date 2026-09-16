# STEMKit third-party dependency notice

This directory contains runtime dependencies used by the vendored STEMKit analytical core.

## regression.js

- Project: https://github.com/Tom-Alexander/regression-js
- Version: 2.0.1
- License: MIT (see `LICENSE.regression-js`)
- Vendored file: `regression.min.js`
- Upstream STEMKit blob SHA: `b2f8ecdac5942053bd01b5443b499b3ad6e0c039`

The bundle is kept byte-for-byte identical to the regression.js build vendored by the reviewed STEMKit commit `edb2cb6afdb25a4680d7e4f831558b00f47e6980`. `scripts/verify_stemkit_curve_golden.mjs` checks that Git blob SHA before running numerical fixtures.

No jStat, Papa Parse, or bibtexParse bundle is claimed as migrated by this slice.
