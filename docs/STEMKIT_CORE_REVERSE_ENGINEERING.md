# STEMKit Core Reverse Engineering

## Status

Reverse engineering is active on branch `reverse-engineering/stemkit-core-parity`, created from the current `main` after the original Study Lab PR had already been merged.

The original Study Lab remains a useful product shell, but its scientific implementations were intentionally lightweight. This work replaces those local approximations with the tested upstream computational core where practical.

## Upstream architecture

Reference: `LD-Shell/stemkit`, package `@stemkit/core`, MIT license.

The upstream core is composed of ES modules with no DOM dependency. A barrel module exposes both namespaces and collision-safe flat exports. Four domains use dependency injection for vendored UMD libraries; the remaining domains are dependency-free.

### Core module inventory

| Module | Approx. lines | Runtime dependency | Main responsibility | Current Course Intelligence state |
| --- | ---: | --- | --- | --- |
| vendor | 135 | host/injection layer | jStat, PapaParse, regression, BibTeX adapter | not ported yet |
| xvg-parser | 397 | none | XVG/PLUMED parsing, series stats, Python export | vendored + wired + golden certified |
| statistics | 870 | jStat | descriptive stats, tests, ANOVA, correlation, non-parametrics, assumptions | simplified local version remains |
| outliers | 353 | jStat | z, modified-z, IQR, Grubbs | simplified local version remains |
| curve-fitting | 504 | regression.js | multiple fit models, adequacy, residuals, exports | simplified linear fit remains |
| structure | 1109 | none | PDB/GRO/XYZ, mass, COM, Rg, rotations, conversion | vendored + PDB/GRO/XYZ browser adapter + golden certified |
| slurm | 454 | none | validated GROMACS/LAMMPS SLURM scripts and resource estimates | vendored + browser adapter + golden certified |
| units | 407 | none | 64 units / 10 categories, CODATA/SI conversions | vendored + wired + golden certified |
| data-cleaning | 553 | PapaParse | typed parsing, cleaning, imputation, profiling | simplified local version remains |
| latex | 339 | none | LaTeX/Markdown tables, matrices, escaping | vendored + wired for tables + golden certified |
| bibtex | 848 | bibtex-parse-js | parsing, union-find dedupe, sanitization | simplified local version remains |
| digitizer | 338 | none | calibrated pixel-to-data mapping and exports | vendored + calibrated browser adapter + golden certified |
| error-bars | 423 | jStat | group summaries, CI, Holm pairwise comparisons | simplified local version remains |
| journals | 281 | none | journal title rule engine | vendored; UI wiring pending |
| iso4 | 675 | none | LTWA parsing and ISO-4 abbreviation | vendored; LTWA dataset/UI wiring pending |
| plumed | 529 | none | version-aware PLUMED generation and validation | vendored + browser adapter + golden certified |
| selection | 570 | none | atom-selection language and spatial queries | vendored + structure inspector adapter + golden certified |

The upstream project documents 1,077 tests across its 16 domain modules, with numerical fixtures validated against SciPy, NumPy, scipy.constants, and physical invariants.

## Important architectural findings

1. **The core is the product moat, not the static pages.** Browser pages are thin shells around reusable numerical/parsing modules.
2. **Dependency injection is deliberate.** Statistics, curve fitting, data cleaning, BibTeX, and error-bar inference need host-provided UMD libraries; they should not be pasted into the UI layer.
3. **Statistical definitions are intentionally explicit.** The upstream barrel resolves collisions such as sample vs population standard deviation rather than silently treating them as identical.
4. **Scientific precision is tested.** Tail probabilities, standardized moments, PDB element inference, CODATA factors, geometry invariants, and round-trip formats have dedicated regression coverage.
5. **Structure handling is much deeper than our first implementation.** Upstream supports PDB/GRO/XYZ, mass-aware geometry, triclinic cells, format conversion, rotation, centering, scaling, box validation, and element inference.
6. **Selection is a reusable scientific language, not a UI filter.** It supports named biochemical groups, attribute matching, ranges, negation, union, residue expansion, unit-aware spatial `within:` queries, and contact search through a spatial grid.
7. **Study Lab should become an adapter over a versioned scientific core.** UI code should collect inputs/render outputs; it should not own numerical algorithms.

## Target architecture

```text
Course Intelligence
├── FastAPI / SQLite / downloader / transcript intelligence
└── Browser Study Lab
    ├── lab-ui.js                 interaction + rendering only
    ├── study-lab-adapters/
    │   ├── digitizer.js
    │   ├── slurm.js
    │   ├── plumed.js
    │   ├── structure.js
    │   ├── data.js               Phase B
    │   └── writing.js            Phase A/B
    └── vendor/stemkit-core/
        ├── dependency-free upstream modules
        ├── injected dependent modules
        ├── upstream MIT license + notice
        └── parity smoke/golden tests
```

The thin-adapter pattern is implemented by digitizer, SLURM, PLUMED, and structure/selection. Interaction/rendering belongs to adapters while scientific parsing, geometry, selection, validation, units, and script generation remain in the vendored core.

## Phase plan

### Phase A — dependency-free core
Status: **in progress; scientific/HPC foundation largely certified**

Vendored: XVG, structure, SLURM, units, LaTeX, digitizer, journals, ISO-4, PLUMED, and atom selection.

Completed in the current certification slices:
- deterministic golden fixtures for XVG parsing/statistics, structure mass/geometry/round-trip behavior, selection semantics, CODATA/SI unit conversions, LaTeX escaping/tables, digitizer calibration, SLURM generation/resource estimates, and PLUMED CV/bias/version behavior;
- canonical verification runs the golden suites and recursively syntax-checks JavaScript below `app/static` while preserving the historical top-level syntax-gate contract;
- browser-runtime certification for vendored units and XVG behavior;
- calibrated digitizer adapter with explicit pixel endpoints, linear/log axes, fail-closed validation, pixel-resolution reporting, active calibration region visualization, CSV copy, and reopen lifecycle coverage;
- GROMACS/LAMMPS SLURM adapter with engine-specific resource topology, arrays, memory/wall-time warnings, checkpoint-aware GROMACS commands, and core-hour estimates;
- version-aware PLUMED adapter covering PLUMED 2.9/2.10, CV construction, rational switching functions, metadynamics/OPES/restraints/walls, MOLINFO/UNITS/PRINT, and explicit fallback warnings;
- PDB/GRO/XYZ Structure Inspector and Coordinate Manipulator adapter with selection expressions, named groups, spatial queries, residue expansion, centering, rotation, scaling, translation, and unit-aware format conversion.

Next in the same phase:
- wire journals/ISO-4 with a legally appropriate LTWA data source and clearly distinguish authoritative ISO-4 data from heuristic rules.

### Phase B — injected analytical core
Status: **not started**

Bring in the upstream vendor layer plus license-compatible dependencies and wire:
- statistics;
- outliers;
- curve fitting;
- data cleaning;
- BibTeX;
- error bars.

Do not call this complete until the upstream-style fixtures pass in our CI/runtime.

### Phase C — course-aware scientific workflows
Status: **not started**

Connect tools to Course Intelligence artifacts:
- launch a tool from a lesson attachment/transcript;
- persist reproducible tool inputs/outputs as study artifacts;
- attach source lesson/course metadata;
- export scripts/results with provenance;
- allow the grounded tutor to reference generated artifacts without inventing calculations.

## Definition of parity complete

STEMKit core parity should only be marked complete when:
- every selected upstream module is either vendored/wrapped or explicitly excluded with rationale;
- upstream license and third-party notices are preserved;
- dependent modules use a defined injection layer;
- numerical/parser golden tests run in CI;
- Study Lab no longer contains duplicate simplified implementations for migrated functions;
- browser E2E covers file loading, tool execution, copy/export, and error states;
- scientific results are reproducible from a saved artifact independent of UI clicks.
