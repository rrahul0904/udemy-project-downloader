# STEMKit Parity Audit

## Current boundary

Course Intelligence Study Lab is migrating from lightweight local scientific implementations to the MIT-licensed STEMKit core through thin browser adapters. This audit tracks what is safe to claim at the current PR head and what remains deferred.

## Certified in this PR

| Surface | Core status | Browser status | Certification |
| --- | --- | --- | --- |
| XVG | vendored | wired | deterministic parser/sample-statistics golden fixture + browser runtime |
| Structure | vendored | PDB stats + translation wired | mass/geometry/translation/PDB round-trip golden fixture |
| Units | vendored | wired | exact scale + CODATA-backed golden fixture + browser runtime |
| LaTeX | vendored | table builder wired | escaping/table golden fixture |
| Digitizer | vendored | calibrated adapter wired | linear/log calibration, validation, resolution golden fixture + browser lifecycle |
| SLURM | vendored | GROMACS/LAMMPS adapter wired | resource-shape/script golden fixture + adapter contract test |
| PLUMED | vendored | version-aware adapter wired | CV/bias/version-fallback golden fixture + browser generation lifecycle |
| Journals | vendored | pending | module smoke only |
| ISO-4 | vendored | pending | module smoke only; LTWA data/UI pending |
| Selection | vendored | pending | module smoke only |

Canonical verification keeps the historical top-level frontend syntax gate, recursively syntax-checks nested JavaScript below `app/static`, runs the no-dependency STEMKit smoke suite, and runs deterministic scientific golden fixtures. Playwright covers browser-runtime core loading, the calibrated digitizer adapter lifecycle, and PLUMED target-version generation.

## Explicitly deferred

The following are not merge blockers for the dependency-free foundation and must not be described as complete:

- full PDB/GRO/XYZ structure editing, rotation, centering, scaling, and conversion UI;
- selection/spatial-query Study Lab adapter;
- journals and ISO-4/LTWA Study Lab adapters and LTWA data source;
- dependency-injected statistics, outliers, curve fitting, data cleaning, BibTeX, and error bars;
- course-aware persistence/provenance workflows for scientific artifacts;
- removal of simplified algorithms that have not yet been replaced and certified.

## Next implementation order

1. Structure + selection vertical: expose PDB/GRO/XYZ parsing/conversion and selection/spatial queries together.
2. Journals + ISO-4: add the LTWA data source and title-abbreviation UI.
3. Dependency-injected analytical core: introduce the vendor injection boundary before replacing statistical/data-cleaning/BibTeX/error-bar implementations.
4. Course-aware scientific artifacts: persist reproducible inputs/outputs with source course/lesson provenance.

## Merge claim

A green exact-head CI run makes this PR suitable to merge as the **dependency-free STEMKit scientific-core foundation with calibrated digitizer, validated SLURM and PLUMED generation, and golden certification**. It does not establish full STEMKit feature parity or publication-grade equivalence for the deferred modules.
