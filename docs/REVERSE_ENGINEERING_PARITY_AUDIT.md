# Reverse Engineering Parity Audit

## Current release truth

Course Intelligence is a production-oriented local-first learning workspace with a downloader, durable transcript intelligence, synchronized study surfaces, and an additive Study Lab. Reverse-engineering work is tracked as explicit parity slices rather than treated as an all-or-nothing claim.

## STEMKit scientific-core slice

The active `reverse-engineering/stemkit-core-parity` branch vendors the dependency-free MIT-licensed STEMKit modules and routes selected Study Lab behavior through them.

The merge boundary for this PR is now:

- XVG parsing and sample statistics wired and golden-certified;
- PDB structure statistics/translation wired and golden-certified;
- 10-category scientific units wired and golden-certified;
- LaTeX table generation wired and golden-certified;
- calibrated plot digitizer wired through a dedicated adapter with explicit pixel endpoints, log axes, fail-closed calibration validation, resolution reporting, and browser lifecycle coverage;
- SLURM, journals, ISO-4, PLUMED, and atom-selection cores vendored but still awaiting product adapters;
- dependency-injected analytical modules deferred to a later architectural wave.

The canonical verification path recursively checks browser JavaScript and executes both module smoke tests and deterministic scientific fixtures. The browser suite separately verifies runtime module loading and the calibrated digitizer surface.

## What this does not prove

A green PR does not prove complete STEMKit parity, scientific superiority, or production equivalence to every upstream module. It establishes a tested dependency-free foundation and a repeatable certification pattern for the adapters migrated so far.

Remaining work is documented in `docs/STEMKIT_CORE_REVERSE_ENGINEERING.md` and `docs/STEMKIT_PARITY_AUDIT.md` and should land as bounded follow-up slices instead of extending this already-large PR indefinitely.
