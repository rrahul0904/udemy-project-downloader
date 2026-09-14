# Course Intelligence OS

A local-first course archiving, transcript intelligence, synchronized study, and scientific workbench application.

## STEMKit scientific core status

The active STEMKit parity work vendors the MIT-licensed dependency-free scientific core and is progressively moving Study Lab behavior behind tested adapters.

Current certified surfaces include:

- XVG parsing and sample statistics;
- PDB structure statistics and coordinate translation;
- scientific unit conversion;
- LaTeX table generation;
- calibrated plot digitization with explicit pixel endpoints, linear/log axes, calibration validation, pixel-resolution reporting, and CSV copy.

Scientific golden fixtures run from canonical verification via `scripts/verify_stemkit_golden.mjs`, while Playwright covers browser-runtime integration and the calibrated digitizer lifecycle. Full STEMKit parity is intentionally not claimed: SLURM, PLUMED, atom selection, journals/ISO-4, richer structure editing, and dependency-injected analytical modules remain staged follow-up work. See `docs/STEMKIT_CORE_REVERSE_ENGINEERING.md` for the detailed matrix and phase plan.

## Development

Install the Python dependencies and run the application with Uvicorn using the environment described in `.env.example`.

Canonical repository verification:

```bash
bash scripts/verify.sh
```

Browser verification:

```bash
npm install --no-audit --no-fund
npx playwright install chromium
npm run test:e2e
```

Container verification:

```bash
docker build -t course-intelligence:verify .
```

For production deployment and acceptance details, see `docs/PRODUCTION_DEPLOYMENT.md` and `docs/LIVE_PRODUCTION_ACCEPTANCE.md`.
