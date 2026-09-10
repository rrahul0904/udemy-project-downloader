# STEMKit core vendor notice

This directory contains selected source files copied from the MIT-licensed STEMKit project:

- Upstream: https://github.com/LD-Shell/stemkit
- Package: @stemkit/core
- Author: Olanrewaju M. Daramola
- License: MIT (see LICENSE in this directory)

Vendored in the first parity wave:
- xvg-parser.js
- structure.js
- slurm.js
- units.js
- latex.js
- digitizer.js

These modules were selected first because the upstream core documents them as having no third-party runtime dependency. They are kept as an attributed vendor layer so Course Intelligence can use the same tested computational behavior rather than maintaining simplified reimplementations.

Do not remove the accompanying MIT license when redistributing these files.
