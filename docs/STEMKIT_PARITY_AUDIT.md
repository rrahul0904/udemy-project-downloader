# STEMKit Parity Audit

## Current boundary

Course Intelligence Study Lab is migrating from lightweight local scientific implementations to the MIT-licensed STEMKit core through thin browser adapters. This audit tracks what is safe to claim at the current PR head and what remains deferred.

## Certified in this PR

| Surface | Core status | Browser status | Certification |
| --- | --- | --- | --- |
| XVG | vendored | wired | deterministic parser/sample-statistics golden fixture + browser runtime |
| Structure | vendored | PDB/GRO/XYZ inspector + transform adapter wired | mass/geometry/selection/format-conversion golden fixture + browser lifecycle |
| Selection | vendored | wired into Structure Inspector | attribute/named-group/residue/spatial-query golden fixture + browser selection flow |
| Units | vendored | wired | exact scale + CODATA-backed golden fixture + browser runtime |
| LaTeX | vendored | table builder wired | escaping/table golden fixture |
| Digitizer | vendored | calibrated adapter wired | linear/log calibration, validation, resolution golden fixture + browser lifecycle |
| SLURM | vendored | GROMACS/LAMMPS adapter wired | resource-shape/script golden fixture + adapter contract test |
| PLUMED | vendored | version-aware adapter wired | CV/bias/version-fallback golden fixture + browser generation lifecycle |
| Journals | vendored | whole-title rule adapter wired | normalization/replacement golden fixture + browser exact-rule flow |
| ISO-4 | vendored | local LTWA-file adapter wired | synthetic-LTWA parser/abbreviation golden fixture + browser local-upload flow |

The **dependency-free upstream core phase is implemented** for the selected Study Lab surfaces. Canonical verification keeps the historical top-level frontend syntax gate, recursively syntax-checks nested JavaScript below `app/static`, runs the no-dependency STEMKit smoke suite, and runs deterministic scientific golden fixtures. Playwright covers browser-runtime core loading, digitizer calibration, PLUMED target-version generation, structure selection/conversion, coordinate transformation, and journal/ISO-4 workflows.

The ISO-4 adapter deliberately does **not** bundle the ISSN LTWA dataset. STEMKit's own third-party/data notice states that LTWA data has separate terms; users load a local CSV/TSV they are permitted to use. CI uses a synthetic independently authored fixture to certify parser/engine behavior.

## Explicitly deferred

The following remain outside the dependency-free foundation and must not be described as complete:

- dependency-injected statistics and outlier inference through jStat;
- curve fitting through regression.js;
- data cleaning through Papa Parse;
- BibTeX parsing/deduplication through bibtexParse;
- error-bar inference through jStat;
- course-aware persistence/provenance workflows for scientific artifacts;
- removal of simplified algorithms only after each injected replacement is certified.

## Next implementation order

1. Dependency-injection foundation: vendor/register the exact supported UMD dependencies with third-party notices and one browser/Node registration path.
2. Statistics + outliers + error bars: migrate the jStat-dependent family together and certify distribution tails/effect sizes/CI behavior.
3. Curve fitting: replace local linear-only fitting with the vendored regression.js-backed model set and residual/adequacy outputs.
4. Data cleaning: replace hand-rolled delimiter parsing with Papa Parse-backed typed cleaning/profiling.
5. BibTeX: replace regex-like local parsing/deduplication with the injected BibTeX parser and STEMKit union-find sanitization/deduplication core.
6. Course-aware scientific artifacts: persist reproducible inputs/outputs with source course/lesson provenance.

## Merge claim

A green exact-head CI run makes this PR suitable to merge as the **dependency-free STEMKit scientific-core foundation**, including calibrated digitizer, PDB/GRO/XYZ structure and selection workflows, validated SLURM and PLUMED generation, scientific units/XVG/LaTeX, and licensing-safe journal/ISO-4 integration. It does not establish full STEMKit parity until the injected analytical modules and course-aware reproducibility workflows are also certified.
