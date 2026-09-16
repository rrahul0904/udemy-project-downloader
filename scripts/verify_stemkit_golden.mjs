import assert from 'node:assert/strict';

import * as Xvg from '../app/static/vendor/stemkit-core/xvg-parser.js';
import * as Structure from '../app/static/vendor/stemkit-core/structure.js';
import * as Units from '../app/static/vendor/stemkit-core/units.js';
import * as Latex from '../app/static/vendor/stemkit-core/latex.js';
import * as Digitizer from '../app/static/vendor/stemkit-core/digitizer.js';
import * as Slurm from '../app/static/vendor/stemkit-core/slurm.js';
import * as Plumed from '../app/static/vendor/stemkit-core/plumed.js';

function close(actual, expected, tolerance = 1e-10, message = '') {
  assert.ok(Number.isFinite(actual), `${message || 'value'} should be finite`);
  assert.ok(
    Math.abs(actual - expected) <= tolerance,
    `${message || 'value'}: expected ${expected} ± ${tolerance}, got ${actual}`
  );
}

// XVG: deterministic parser/statistics fixture.
const xvgText = [
  '@ title "Golden RMSD"',
  '@ xaxis label "Time (ps)"',
  '@ yaxis label "RMSD (nm)"',
  '0 0.10',
  '1 0.20',
  '2 0.30'
].join('\n');
const xvg = Xvg.parseXvg(xvgText);
assert.equal(xvg.title, 'Golden RMSD');
assert.equal(xvg.rowCount, 3);
assert.deepEqual(Xvg.extractColumn(xvg.matrix, 0), [0, 1, 2]);
assert.deepEqual(Xvg.extractColumn(xvg.matrix, 1), [0.1, 0.2, 0.3]);
const xvgStats = Xvg.columnStats(Xvg.extractColumn(xvg.matrix, 1));
close(xvgStats.mean, 0.2, 1e-12, 'XVG mean');
close(xvgStats.std, 0.1, 1e-12, 'XVG sample SD');

// Structure: known masses, geometry invariants, translation, and PDB round trip.
const pdb = [
  'ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00           N',
  'ATOM      2  CA  ALA A   1       2.000   0.000   0.000  1.00 20.00           C'
].join('\n');
const parsed = Structure.parsePDB(pdb);
assert.equal(parsed.atoms.length, 2);
const stats = Structure.structureStats(parsed.atoms);
assert.equal(stats.nAtoms, 2);
assert.equal(stats.nResidues, 1);
close(stats.totalMass, 14.007 + 12.011, 1e-12, 'molecular mass');
close(stats.geometricCentre.x, 1, 1e-12, 'geometric centre X');
close(stats.geometricCentre.y, 0, 1e-12, 'geometric centre Y');
close(stats.geometricCentre.z, 0, 1e-12, 'geometric centre Z');

const moved = Structure.translateAtoms(parsed.atoms, 3, -2, 5);
close(moved[0].x, 3, 1e-12, 'translated X');
close(moved[0].y, -2, 1e-12, 'translated Y');
close(moved[0].z, 5, 1e-12, 'translated Z');
const roundTrip = Structure.parsePDB(Structure.formatPDB(moved));
assert.equal(roundTrip.atoms.length, 2);
close(roundTrip.atoms[1].x, 5, 1e-3, 'round-trip X');
close(roundTrip.atoms[1].y, -2, 1e-3, 'round-trip Y');
close(roundTrip.atoms[1].z, 5, 1e-3, 'round-trip Z');

// Units: exact scale factors and a CODATA-backed conversion.
assert.equal(Units.convert(1, 'length', 'nm', 'angstrom'), 10);
assert.equal(Units.convert(10, 'length', 'angstrom', 'nm'), 1);
assert.equal(Units.convert(1, 'pressure', 'bar', 'pa'), 100000);
close(Units.convert(1, 'energy', 'hartree', 'ev'), 27.211386245988, 1e-12, 'Hartree to eV');

// LaTeX: deterministic table generation and escaping.
const matrix = Latex.parseTableData('Group,Mean\nA&B,12.3');
assert.deepEqual(matrix, [['Group', 'Mean'], ['A&B', '12.3']]);
const table = Latex.generateLatexTable(matrix, {
  environment: 'table',
  style: 'booktabs',
  align: 'l',
  headerRow: true
});
assert.match(table, /\\begin\{table\}/);
assert.match(table, /\\toprule/);
assert.match(table, /A\\&B/);
assert.match(table, /12\.3/);

// Digitizer: offset calibration, inverted image Y, logarithmic axes, resolution,
// and fail-closed invalid calibration behavior.
const linear = {
  pxX1: 100, pxX2: 500,
  pxY1: 420, pxY2: 20,
  valX1: 0, valX2: 20,
  valY1: 0, valY2: 100,
  logX: false, logY: false
};
assert.equal(Digitizer.validateCalibration(linear).valid, true);
const linearPoint = Digitizer.toDataCoordinates(300, 220, linear);
close(linearPoint.x, 10, 1e-12, 'digitizer linear X');
close(linearPoint.y, 50, 1e-12, 'digitizer inverted Y');
const resolution = Digitizer.pixelResolution(linear);
close(resolution.dx, 0.05, 1e-12, 'digitizer X resolution');
close(resolution.dy, 0.25, 1e-12, 'digitizer Y resolution');

const logarithmic = {
  pxX1: 0, pxX2: 200,
  pxY1: 200, pxY2: 0,
  valX1: 1, valX2: 100,
  valY1: 1, valY2: 10000,
  logX: true, logY: true
};
assert.equal(Digitizer.validateCalibration(logarithmic).valid, true);
const logPoint = Digitizer.toDataCoordinates(100, 100, logarithmic);
close(logPoint.x, 10, 1e-10, 'digitizer log X');
close(logPoint.y, 100, 1e-9, 'digitizer log Y');

const invalid = Digitizer.validateCalibration({
  pxX1: 10, pxX2: 10,
  pxY1: 0, pxY2: 100,
  valX1: 1, valX2: 10,
  valY1: 0, valY2: 1,
  logX: false, logY: false
});
assert.equal(invalid.valid, false);
assert.ok(invalid.errors.some(error => /share a pixel column/i.test(error)));

const invalidLog = Digitizer.validateCalibration({
  pxX1: 0, pxX2: 100,
  pxY1: 0, pxY2: 100,
  valX1: 0, valX2: 10,
  valY1: 1, valY2: 100,
  logX: true, logY: true
});
assert.equal(invalidLog.valid, false);
assert.ok(invalidLog.errors.some(error => /logarithmic X axis/i.test(error)));

// SLURM: deterministic resource shape, engine-specific command, warnings, and allocation math.
const gromacs = Slurm.generateScript({
  engine: 'gromacs',
  jobName: 'golden_md',
  partition: 'gpu',
  nodes: 1,
  gpus: 1,
  cpusPerTask: 8,
  walltime: '02:00:00',
  memory: '16G',
  modules: ['gromacs/2024', 'cuda/12.4'],
  tpr: 'topol.tpr',
  deffnm: 'md',
  maxh: 1.8,
  appendCheckpoint: true
});
assert.match(gromacs.script, /#SBATCH --job-name=golden_md/);
assert.match(gromacs.script, /#SBATCH --gres=gpu:1/);
assert.match(gromacs.script, /module load gromacs\/2024/);
assert.match(gromacs.script, /gmx mdrun -s topol\.tpr -deffnm md/);
assert.match(gromacs.script, /-cpi md\.cpt -append/);
assert.equal(gromacs.warnings.filter(item => item.level === 'error').length, 0);
const allocation = Slurm.estimateCoreHours({
  engine: 'gromacs', nodes: 1, cpusPerTask: 8, walltime: '02:00:00'
});
assert.deepEqual(allocation, { coreHours: 16, hours: 2, cores: 8 });

const invalidWalltime = Slurm.generateScript({
  engine: 'lammps',
  jobName: 'bad_time',
  nodes: 1,
  tasksPerNode: 4,
  cpusPerTask: 1,
  walltime: 'not-a-time',
  memory: '4G',
  input: 'in.lammps'
});
assert.match(invalidWalltime.script, /#SBATCH --time=24:00:00/);
assert.ok(invalidWalltime.warnings.some(item => /Wall time looks malformed/.test(item.message)));

// PLUMED: deterministic CV generation, version fallback, bias ordering, and warnings.
const plumedCatalogue = {
  DISTANCE: {
    fields: [
      { k: 'ATOMS', type: 'atoms', def: '1,2', required: true },
      { k: 'NOPBC', type: 'flag', def: false },
    ],
  },
  TORSION: {
    fields: [{ k: 'ATOMS', type: 'atoms', def: '1,2,3,4', required: true }],
  },
  COORDINATION: {
    fields: [
      { k: 'GROUPA', type: 'atoms', def: '1-10', required: true },
      { k: 'GROUPB', type: 'atoms', def: '11-20' },
      { k: 'SWITCH', type: 'text', def: '' },
      { k: 'NL_CUTOFF', type: 'num', def: '' },
    ],
  },
  DIHEDRAL_CORRELATION: {
    minVersion: '2.10',
    fallback: 'DIHCOR',
    fields: [{ k: 'ATOMS', type: 'atoms', def: '1,2,3,4,5,6,7,8', required: true }],
  },
};
const switchBlock = Plumed.buildSwitchBlock({ r0: 0.3, dmax: 1.0 });
assert.equal(switchBlock.block, '{RATIONAL R_0=0.3 D_MAX=1}');
assert.deepEqual(switchBlock.warnings, []);

const plumedConfig = {
  cvs: [
    { type: 'DISTANCE', label: 'd1', values: { ATOMS: '1,2' }, bias: true },
    { type: 'TORSION', label: 'phi', values: { ATOMS: '5,7,9,15' }, bias: true },
  ],
  biasMethod: 'wt_metad',
  biasParams: {
    sigma: '0.05,0.35',
    gridMin: '0,-pi',
    gridMax: '2,pi',
    gridBin: '200,200',
  },
  catalogue: plumedCatalogue,
  version: '2.9',
  units: { length: 'nm', energy: 'kj/mol', time: 'ps' },
  molinfo: { structure: 'ref.pdb', moltype: 'protein' },
  printStride: 250,
  printFile: 'COLVAR',
};
const plumed = Plumed.generatePlumedInput(plumedConfig);
assert.deepEqual(plumed.warnings, []);
assert.equal(plumed.cvLines.length, 2);
assert.ok(plumed.input.indexOf('d1: DISTANCE ATOMS=1,2') < plumed.input.indexOf('METAD'));
assert.ok(plumed.input.indexOf('METAD') < plumed.input.indexOf('PRINT'));
assert.match(plumed.input, /UNITS LENGTH=nm ENERGY=kj\/mol TIME=ps/);
assert.match(plumed.input, /MOLINFO STRUCTURE=ref\.pdb MOLTYPE=protein/);
assert.match(plumed.input, /PRINT ARG=d1,phi,metad\.bias STRIDE=250 FILE=COLVAR/);

const fallbackCv = Plumed.buildCVLine(
  { type: 'DIHEDRAL_CORRELATION', label: 'corr', values: { ATOMS: '1,2,3,4,5,6,7,8' } },
  plumedCatalogue,
  { version: '2.9' }
);
assert.match(fallbackCv.line, /corr: DIHCOR/);
assert.equal(fallbackCv.usedFallback, true);
assert.ok(fallbackCv.warnings.some(message => /older action name/.test(message)));

const malformedBias = Plumed.generatePlumedInput({
  cvs: [{ type: 'DISTANCE', label: 'd1', values: { ATOMS: '1,2' }, bias: true }],
  biasMethod: 'wt_metad',
  biasParams: {},
  catalogue: plumedCatalogue,
  version: '2.10',
});
assert.ok(malformedBias.warnings.some(message => /SIGMA/.test(message)));
assert.ok(malformedBias.warnings.some(message => /GRID_MIN/.test(message)));

console.log('STEMKit scientific golden fixtures: ok');
