# STEMKit Scientific Parity Audit

Date: 2026-09-01

Reference: `LD-Shell/stemkit` current public `main`, especially `README.md`, `src/core/README.md`, `src/core/*`, tests, CHANGELOG, LICENSE and THIRD_PARTY_LICENSES.

## Scope

The current Course Intelligence Study Lab represents the same 18 research-tool concepts plus the three workflow helpers, but this is not a claim of numerical or scientific equivalence.

The upstream project currently documents a 16-module DOM-free `@stemkit/core` and 1,077 tests. Its architecture is valuable because browser UI, headless scripts and tests all use the same computational code path.

## Current parity classification

| Area | Current implementation | Status | Next fidelity work |
| --- | --- | --- | --- |
| Statistics | descriptive statistics-focused browser implementation | PARTIAL | Welch/Student t tests, ANOVA, correlation, non-parametrics, assumptions, CIs, effect sizes |
| Outliers | z-score and IQR workflows | PARTIAL | modified z, Grubbs, stronger fixtures |
| Curve fitting | primarily linear OLS | PARTIAL | polynomial/exponential/log/power, fit diagnostics, residuals, linearization warnings |
| Error bars | mean/SD/SEM/approximate CI | PARTIAL | grouped inference, configurable CIs, multiplicity correction |
| XVG | lightweight numeric parsing/plot | PARTIAL | metadata, multiple datasets, legends, Grace/PLUMED semantics |
| Structure | lightweight PDB inspection | PARTIAL | PDB/GRO/XYZ, molecular weight, COM, Rg, rotations, conversions |
| Coordinates/selections | translation-oriented manipulation | PARTIAL | rotation, centering, alignment, selections, neighbor queries |
| MD/HPC | starter GROMACS/LAMMPS/PLUMED text | PARTIAL | SLURM generation, validation, version-aware warnings |
| BibTeX | basic sanitize/dedupe | PARTIAL | real parser, robust merge/dedupe, escaping, union-style grouping |
| ISO-4 | small heuristic dictionary | PARTIAL | reproducible comprehensive abbreviation data/algorithm where licensing permits |
| LaTeX | basic table/snippet generation | PARTIAL | broader escaping, alignment/booktabs, richer equation rendering |
| Units | common subset | PARTIAL | broader dimensional catalog with traceable constants |
| Digitizer | manual image-coordinate workflow | PARTIAL | calibrated axes, log axes, data mapping, export |
| Plotting | lightweight SVG | PARTIAL | richer series/axes/export/publication controls |
| Pomodoro/decision/kinetics | functional workflow helpers | FUNCTIONAL_EQUIVALENT for basic workflows | preferences/weights/sensitivity/reaction models are enhancements |

## Engineering gap

The most important Study Lab engineering gap is not another UI page. It is the lack of a reusable DOM-free core shared by browser code and tests.

Target shape:

```text
study-core/
  statistics.js
  outliers.js
  curve-fitting.js
  error-bars.js
  xvg.js
  structure.js
  selection.js
  coordinate.js
  md.js
  slurm.js
  plumed.js
  bibtex.js
  iso4.js
  latex.js
  units.js
  digitizer.js
```

The UI should become an adapter to the core. Tests should call the same core directly.

## Validation rule

Numerical parity tests must use independent references or invariants where practical, for example:

- known SciPy/NumPy reference outputs recorded as fixtures
- published SI/CODATA constants
- round-trip parser/serializer fixtures
- rotation distance/orthonormality invariants
- known molecular mass/center-of-mass fixtures
- known statistical examples and confidence intervals

Tests must not simply compare the implementation to itself.

## Legal boundary

STEMKit is MIT licensed. Prefer independent implementation. If upstream code is reused, preserve the required MIT copyright/license notices and any third-party license obligations. Do not copy unrelated assets or dependencies merely to increase apparent parity.
