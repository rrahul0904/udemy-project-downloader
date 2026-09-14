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
| SLURM | vendored | pending | module smoke only |
| Journals | vendored | pending | module smoke only |
| ISO-4 | vendored | pending | module smoke only; LTWA data/UI pending |
| PLUMED | vendored | pending | module smoke only |
| Selection | vendored | pending | module smoke only |

Canonical verification recursively syntax-checks JavaScript below `app/static`, runs the no-dependency STEMKit smoke suite, and runs the deterministic scientific golden suite. Playwright covers browser-runtime core loading and the calibrated digitizer adapter lifecycle.

## Explicitly deferred

The following are not merge blockers for the dependency-free foundation and must not be described as complete:

- full PDB/GRO/XYZ structure editing, rotation, centering, scaling, and conversion UI;
- SLURM, PLUMED, selection, journals, and ISO-4/LTWA Study Lab adapters;
- dependency-injected statistics, outliers, curve fitting, data cleaning, BibTeX, and error bars;
- course-aware persistence/provenance workflows for scientific artifacts;
- removal of simplified algorithms that have not yet been replaced and certified.

## Next implementation order

1. SLURM adapter: replace starter MD workflow text with validated resource estimates and generated GROMACS/LAMMPS scripts.
2. PLUMED adapter: version-aware generation and validation, sharing the molecular workflow surface where practical.
3. Structure + selection vertical: expose GRO/XYZ parsing/conversion and selection/spatial queries together.
4. Journals + ISO-4: add the LTWA data source and title-abbreviation UI.
5. Dependency-injected analytical core: introduce the vendor injection boundary before replacing statistical/data-cleaning/BibTeX/error-bar implementations.

## Merge claim

A green exact-head CI run makes this PR suitable to merge as the **dependency-free STEMKit scientific-core foundation with calibrated digitizer and golden certification**. It does not establish full STEMKit feature parity or publication-grade equivalence for the deferred modules.
