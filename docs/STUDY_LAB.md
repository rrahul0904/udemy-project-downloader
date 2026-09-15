# Study Lab

Study Lab is the local-first scientific and research workbench inside Course Intelligence. It keeps compatible course files inside the application boundary and runs core calculations in browser JavaScript where practical.

## Current tool catalog

The existing catalog contains 21 tools spanning descriptive data work, plotting/digitization, molecular formats/workflows, writing/citation helpers, scientific unit conversion, and study utilities.

The original Study Lab shipped as a **functional integrated MVP**. The current parity work keeps that integrated product surface while replacing lightweight scientific approximations with the tested upstream STEMKit computational core where practical.

## STEMKit migration status

The current STEMKit parity branch is replacing lightweight local approximations with a vendored MIT-licensed scientific core through thin adapters.

Certified in the current phase:

- **XVG Visualizer** — vendored parser and sample column statistics with golden fixtures.
- **Structure Inspector / Coordinate Manipulator** — vendored PDB parsing, molecular mass/geometry/Rg statistics, translation, formatting, and round-trip certification.
- **Scientific Converter** — vendored 10-category unit database and CODATA/SI conversions with deterministic fixtures.
- **LaTeX Table Builder** — vendored table parsing/generation with escaping fixtures.
- **Plot Digitizer** — vendored calibrated pixel-to-data mapping with explicit pixel endpoints, linear/log axes, validation, pixel-resolution reporting, calibrated-region visualization, and CSV copy.

The browser integration layer now includes `app/static/study-lab-adapters/digitizer.js`. The adapter owns interaction/rendering state while numerical calibration behavior stays in the vendored core.

## Verification

`bash scripts/verify.sh` performs the canonical repository checks and now includes:

- Python unit tests and compilation;
- top-level JavaScript syntax checks plus recursive checks for nested Study Lab/vendor modules;
- no-dependency STEMKit module smoke coverage;
- deterministic STEMKit golden fixtures covering XVG, structure, units, LaTeX, and digitizer behavior.

Playwright additionally verifies browser-runtime STEMKit loading and the calibrated digitizer lifecycle, including fail-closed invalid calibration and reopening the tool after switching workspaces.

## Deliberately incomplete parity

Study Lab is not yet a claim of full STEMKit parity. Remaining staged work includes:

- full PDB/GRO/XYZ structure editing and conversion;
- SLURM and PLUMED workflow adapters;
- atom selection and spatial queries;
- journals/ISO-4 with an LTWA data source;
- dependency-injected statistics, outliers, curve fitting, data cleaning, BibTeX, and error-bar inference;
- course-aware persistence/provenance of reproducible scientific artifacts.

See `docs/STEMKIT_CORE_REVERSE_ENGINEERING.md` and `docs/STEMKIT_PARITY_AUDIT.md` for the detailed phase boundary and next implementation order.

## Safety and scope

Study Lab is a learning and research helper. Scientific outputs should be independently checked when used for consequential research decisions, and deferred modules should not be represented as parity-complete until their adapters and fixtures are present.
