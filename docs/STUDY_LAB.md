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

The dependency-free STEMKit phase now has browser adapters and deterministic certification for the scientific/HPC surfaces we selected:

- **XVG Visualizer** — vendored parser and sample column statistics with golden fixtures.
- **Structure Inspector / Coordinate Manipulator** — vendored PDB/GRO/XYZ parsing, molecular mass/geometry/Rg statistics, format conversion, centering, rotation, scaling, translation, and unit-aware serialization. Structure Inspector also exposes vendored atom-selection expressions, named groups, residue expansion, and spatial `within:` queries.
- **Scientific Converter** — vendored 10-category unit database and CODATA/SI conversions with deterministic fixtures.
- **LaTeX Table Builder** — vendored table parsing/generation with escaping fixtures.
- **Plot Digitizer** — vendored calibrated pixel-to-data mapping with explicit pixel endpoints, linear/log axes, validation, pixel-resolution reporting, calibrated-region visualization, and CSV copy.
- **MD Workflow Generator / SLURM** — vendored SLURM generation is wired for GROMACS and LAMMPS with resource validation, job-array handling, memory/wall-time warnings, checkpoint-aware GROMACS commands, and allocation estimates.
- **MD Workflow Generator / PLUMED** — vendored PLUMED generation is wired for 2.9/2.10 targets with Distance, Torsion, Coordination, and Dihedral-correlation CVs; rational switching functions; metadynamics, OPES, restraint, moving-restraint, and wall biases; MOLINFO/UNITS/PRINT; target-version fallbacks; and warnings surfaced as comments rather than silently ignored.
- **Journal Abbreviator / ISO-4** — whole-title abbreviation now runs through the vendored journal normalization/matching core. ISO-4 word-level abbreviation uses the vendored LTWA parser/matcher but requires a local LTWA CSV/TSV file that the user is permitted to use. The ISSN LTWA dataset is intentionally not bundled because its distribution terms are separate from STEMKit's MIT license.

The browser integration layer includes thin adapters under `app/static/study-lab-adapters/` for digitizer, SLURM, PLUMED, structure/selection, and journals/ISO-4. These adapters own interaction/rendering state while scientific parsing, geometry, selection, validation, abbreviation, and script-generation behavior stays in the vendored core.

## Verification

`bash scripts/verify.sh` performs the canonical repository checks and includes:

- Python unit tests and compilation;
- top-level JavaScript syntax checks plus recursive checks for nested Study Lab/vendor modules;
- no-dependency STEMKit module smoke coverage;
- deterministic STEMKit golden fixtures covering XVG, structure, selection, units, LaTeX, digitizer, SLURM, PLUMED, journals, and ISO-4 behavior.

Playwright verifies browser-runtime STEMKit loading, calibrated digitization, PLUMED version-aware generation, XYZ selection/conversion, coordinate transformation/GRO serialization, editable whole-title journal rules, and local-only LTWA upload for ISO-4. Repository contract tests ensure the Study Lab UI is wired to vendored STEMKit modules rather than duplicate local implementations.

## Deliberately incomplete parity

Study Lab is not yet a claim of full STEMKit parity. Remaining staged work is now concentrated in modules that require dependency injection:

- statistics and outlier inference through jStat;
- curve fitting through regression.js;
- data cleaning through Papa Parse;
- BibTeX parsing/deduplication through bibtexParse;
- error-bar inference through jStat;
- course-aware persistence/provenance of reproducible scientific artifacts.

See `docs/STEMKIT_CORE_REVERSE_ENGINEERING.md` and `docs/STEMKIT_PARITY_AUDIT.md` for the detailed phase boundary and next implementation order.

## Safety and scope

Study Lab is a learning and research helper. Scientific outputs should be independently checked when used for consequential research decisions, and deferred modules should not be represented as parity-complete until their adapters and fixtures are present.
