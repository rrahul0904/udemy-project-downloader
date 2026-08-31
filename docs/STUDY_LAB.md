# Study Lab — STEMKit-Inspired Integration

## Purpose

Study Lab extends the existing Local Media Downloader into a local course-and-research workspace. It is designed to let a user archive authorized Udemy/YouTube course material and then open compatible downloaded text/data files directly inside lightweight analysis and study tools.

The integration deliberately preserves the downloader's existing authorization, URL validation, cookie handling, job management, and download storage behavior. Study Lab is an additive feature served at `/lab`.

## Reference project

The design and tool inventory were informed by the public STEMKit project:

- Reference repository: `https://github.com/LD-Shell/stemkit`
- User-provided legacy/redirecting URL: `https://github.com/danielravina/stemkit`
- License: MIT (see the upstream repository's `LICENSE`)

This integration does **not** vendor STEMKit's source tree, generated site, fonts, large dependency bundles, or third-party libraries. The current Study Lab code is an independent implementation of selected workflows and interaction patterns. If upstream source code is copied in a future wave, its MIT copyright/license notice must be preserved with the copied material.

## Architecture

```text
FastAPI app
├── /                       existing downloader UI
├── /lab                    Study Lab UI
├── /api/downloads          existing local download inventory
└── /files/{relative_path}  existing guarded local-file serving route

Browser
├── lab.html                catalog + active-tool workspace
├── lab.css                 responsive Study Lab design
└── lab.js                  local computations and course-file bridge
```

Study Lab's computational tools run in the browser. The only Study Lab operation that intentionally reaches an external service is DOI → BibTeX, which calls Crossref after an explicit user action.

## Course-material bridge

Study Lab reads the existing `/api/downloads` inventory and offers compatible local files for loading into an active text-based tool. The first implementation recognizes:

- `.txt`
- `.csv`
- `.tsv`
- `.md`
- `.json`
- `.xvg`
- `.pdb`
- `.gro`
- `.bib`
- `.dat`
- `.log`

Files continue to be served through the downloader's existing guarded `/files/{relative_path}` endpoint; Study Lab does not introduce a second filesystem API.

## Implemented tool inventory

### Data and statistics

1. Statistics Calculator
2. Data Cleaner
3. Outlier Detector
4. Curve Fitter
5. Error-Bar Generator
6. Plot Builder
7. Plot Digitizer

### Molecular / simulation helpers

8. XVG Visualizer
9. Structure Inspector
10. Coordinate Manipulator
11. MD Workflow Generator

### Writing / citations

12. BibTeX Sanitizer
13. BibTeX Deduplicator
14. DOI → BibTeX
15. Journal Abbreviator
16. LaTeX Table Builder
17. Equation Builder

### Scientific units

18. Scientific Converter

### Study helpers

19. Pomodoro Timer
20. Decision Matrix
21. Kinetics Sandbox

## Parity status

The current wave is a functional integrated MVP, not a scientific-equivalence claim.

| Capability | Current status | Follow-up for high-fidelity parity |
| --- | --- | --- |
| Descriptive statistics | Functional local implementation | Add richer hypothesis tests/distributions and golden numerical fixtures |
| Data cleaning | Functional basic implementation | Add typed CSV parsing, column-aware transformations, larger-file handling |
| Outlier detection | IQR and z-score | Add upstream method coverage and validation fixtures |
| Curve fitting | Linear OLS | Add nonlinear models, uncertainty, residual diagnostics |
| Error bars | Mean/SD/SEM/approx. 95% CI | Add configurable confidence intervals and statistical assumptions |
| Plot builder | Lightweight SVG | Add richer axes, labels, exports, series, and publication controls |
| Plot digitizer | Manual full-image coordinate mapping | Add calibrated axes, crop/axis anchors, log axes, automated extraction |
| XVG | First numeric series parser/plot | Add metadata, multiple datasets, legends, Grace semantics |
| PDB inspection | Atom/residue/chain/bounds summary | Add rich molecular visualization and selection language |
| Coordinate editing | Translation | Add rotation, centering, alignment, selections, format breadth |
| MD workflow | Starter GROMACS/LAMMPS/PLUMED text | Add validated templates, parameter schemas, Slurm/HPC generation |
| BibTeX sanitizer | Basic normalization | Port/independently reproduce full field parsing and validation behavior |
| BibTeX dedupe | DOI/title heuristic | Add robust parser, fuzzy matching, merge strategies |
| DOI lookup | Crossref transform endpoint | Add metadata fallback, retries, rate-limit/user-agent handling |
| Journal abbreviation | Small heuristic dictionary | Add authoritative LTWA/ISO-4 data and complete journal dataset |
| LaTeX table | Basic CSV/tabular conversion | Add alignment, escaping breadth, booktabs, merged cells |
| Equation builder | Snippet wrapper | Add live math rendering/editor controls |
| Unit conversion | Common length/energy/pressure/temp | Add full STEMKit unit catalog and dimensional metadata |
| Pomodoro | Functional | Add notifications/audio/preferences if desired |
| Decision matrix | Unweighted numeric sum/mean | Add criteria weights, benefit/cost directions, sensitivity |
| Kinetics | First-order decay | Add reaction-order/models and parameter sweeps |

## Product direction

The useful product is broader than a downloader clone: an offline-first **course workspace** where imported lessons, subtitles, practice-test exports, notes, data files, and scientific utilities are connected.

Recommended next waves:

1. **Course Library** — model each archived course, section, lecture, transcript, attachment, and practice set as browsable local content.
2. **Study Workspace** — transcript search, bookmarks, notes, flashcards, practice mode, progress, and tool deep-links.
3. **STEM tool parity** — replace simplified implementations with thoroughly tested core modules and upstream-compatible fixtures where valuable.
4. **AI-assisted learning (optional)** — local/configurable model provider for transcript Q&A, explanations, quiz generation, and course-grounded study plans, with explicit privacy controls.
5. **Production hardening** — CSP, browser tests, larger-file handling, import/export schema, structured local persistence, accessibility and performance budgets.

## Scientific-use warning

The Study Lab utilities are learning/research helpers. Simplified numerical, molecular, citation, and simulation tools must be independently validated before they are used for publication-critical, safety-critical, clinical, engineering, or production scientific decisions.
