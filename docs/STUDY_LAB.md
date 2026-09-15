# Study Lab

Study Lab is the local-first scientific and research workbench inside Course Intelligence. It keeps compatible course files inside the application boundary and runs core calculations in browser JavaScript where practical.

## Reference project

- Upstream: https://github.com/LD-Shell/stemkit
- Package: `@stemkit/core`
- License: MIT

The original Study Lab shipped as a **functional integrated MVP**. The current parity work keeps that integrated product surface while replacing lightweight scientific approximations with the tested upstream STEMKit computational core where practical.

## Current tool catalog

The existing catalog contains 21 tools spanning descriptive data work, plotting/digitization, molecular formats/workflows, writing/citation helpers, scientific unit conversion, and study utilities.

## STEMKit migration status

The current STEMKit parity branch is replacing lightweight local approximations with a vendored MIT-licensed scientific core through thin adapters.

Certified in the current phase:

- **XVG Visualizer** — vendored parser and sample column statistics with golden fixtures.
- **Structure Inspector / Coordinate Manipulator** — vendored PDB/GRO/XYZ parsing, molecular mass/geometry/Rg statistics, format conversion, centering, rotation, scaling, translation, and unit-aware serialization. Structure Inspector also exposes vendored atom-selection expressions, named groups, residue expansion, and spatial `within:` queries.
- **Scientific Converter** — vendored 10-category unit database and CODATA/SI conversions with deterministic fixtures.
- **LaTeX Table Builder** — vendored table parsing/generation with escaping fixtures.
- **Plot Digitizer** — vendored calibrated pixel-to-data mapping with explicit pixel endpoints, linear/log axes, validation, pixel-resolution reporting, calibrated-region visualization, and CSV copy.
- **MD Workflow Generator / SLURM** — vendored SLURM generation is wired for GROMACS and LAMMPS with resource validation, job-array handling, memory/wall-time warnings, checkpoint-aware GROMACS commands, and allocation estimates.
- **MD Workflow Generator / PLUMED** — vendored PLUMED generation is wired for 2.9/2.10 targets with Distance, Torsion, Coordination, and Dihedral-correlation CVs; rational switching functions; metadynamics, OPES, restraint, moving-restraint, and wall biases; MOLINFO/UNITS/PRINT; target-version fallbacks; and warnings surfaced as comments rather than silently ignored.

The browser integration layer includes `app/static/study-lab-adapters/digitizer.js`, `slurm.js`, `plumed.js`, and `structure.js`. These adapters own interaction/rendering state while scientific parsing, geometry, selection, validation, and script-generation behavior stays in the vendored core.

## Verification

`bash scripts/verify.sh` performs the canonical repository checks and includes:

- Python unit tests and compilation;
- top-level JavaScript syntax checks plus recursive checks for nested Study Lab/vendor modules;
- no-dependency STEMKit module smoke coverage;
- deterministic STEMKit golden fixtures covering XVG, structure, selection, units, LaTeX, digitizer, SLURM, and PLUMED behavior.

Playwright verifies browser-runtime STEMKit loading, the calibrated digitizer lifecycle, PLUMED version-aware generation, XYZ selection/conversion in Structure Inspector, and coordinate transformation/GRO serialization in Coordinate Manipulator. Repository contract tests ensure the Study Lab UI is wired to vendored STEMKit modules instead of duplicate local implementations.

## Deliberately incomplete parity

Study Lab is not yet a claim of full STEMKit parity. Remaining staged work includes:

- journals/ISO-4 with an LTWA data source;
- dependency-injected statistics, outliers, curve fitting, data cleaning, BibTeX, and error-bar inference;
- course-aware persistence/provenance of reproducible scientific artifacts.

See `docs/STEMKIT_CORE_REVERSE_ENGINEERING.md` and `docs/STEMKIT_PARITY_AUDIT.md` for the detailed phase boundary and next implementation order.

## Safety and scope

Study Lab is a learning and research helper. Scientific outputs should be independently checked when used for consequential research decisions, and deferred modules should not be represented as parity-complete until their adapters and fixtures are present.
