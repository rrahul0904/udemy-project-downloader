import assert from 'node:assert/strict';

import * as Xvg from '../app/static/vendor/stemkit-core/xvg-parser.js';
import * as Structure from '../app/static/vendor/stemkit-core/structure.js';
import * as Slurm from '../app/static/vendor/stemkit-core/slurm.js';
import * as Units from '../app/static/vendor/stemkit-core/units.js';
import * as Latex from '../app/static/vendor/stemkit-core/latex.js';
import * as Digitizer from '../app/static/vendor/stemkit-core/digitizer.js';
import * as Journals from '../app/static/vendor/stemkit-core/journals.js';
import * as Iso4 from '../app/static/vendor/stemkit-core/iso4.js';
import * as Plumed from '../app/static/vendor/stemkit-core/plumed.js';
import * as Selection from '../app/static/vendor/stemkit-core/selection.js';

const xvg = Xvg.parseXvg('@ title "RMSD"\n0 0.1\n1 0.2\n');
assert.equal(xvg.rowCount, 2);
assert.equal(xvg.matrix.length, 2);
assert.equal(Xvg.extractColumn(xvg.matrix, 1).length, 2);

assert.equal(Units.convert(1, 'length', 'nm', 'angstrom'), 10);
assert.ok(Units.listAllCategories().includes('temperature'));
assert.ok(Units.listAllCategories().length >= 10);

const pdb = [
  'ATOM      1  N   ALA A   1      11.104  13.207   9.798  1.00 20.00           N',
  'ATOM      2  CA  ALA A   1      12.560  13.400   9.620  1.00 20.00           C'
].join('\n');
const structure = Structure.parsePDB(pdb);
assert.equal(structure.atoms.length, 2);
const stats = Structure.structureStats(structure.atoms);
assert.equal(stats.nAtoms, 2);
assert.equal(stats.nResidues, 1);
assert.ok(Number.isFinite(stats.totalMass));
const moved = Structure.translateAtoms(structure.atoms, 1, 0, 0);
assert.equal(moved[0].x, structure.atoms[0].x + 1);
assert.match(Structure.formatPDB(moved), /ATOM/);

const matrix = Latex.parseTableData('Group,Mean\nControl,12.3');
assert.equal(matrix.length, 2);
assert.match(Latex.generateLatexTable(matrix), /\\\\begin\{table\}/);
assert.match(Latex.generateLatexTable(matrix), /\\\\toprule/);

const calibration = {
  pxX1: 0, pxX2: 100,
  pxY1: 0, pxY2: 100,
  valX1: 0, valX2: 10,
  valY1: 10, valY2: 0
};
assert.equal(Digitizer.validateCalibration(calibration).valid, true);
const mapped = Digitizer.toDataCoordinates(50, 50, calibration);
assert.equal(mapped.x, 5);
assert.equal(mapped.y, 5);

const slurm = Slurm.generateScript({
  engine: 'gromacs',
  jobName: 'study_lab_smoke',
  partition: 'gpu',
  nodes: 1,
  gpus: 1,
  cpusPerTask: 4,
  walltime: '01:00:00',
  memory: '4G',
  modules: ['gromacs/2024'],
  tpr: 'md.tpr',
  deffnm: 'md'
});
assert.match(slurm.script, /#SBATCH/);
assert.match(slurm.script, /study_lab_smoke/);

assert.equal(typeof Journals.normKey, 'function');
assert.equal(typeof Iso4.parseLTWA, 'function');
assert.equal(Plumed.versionAtLeast('2.9', '2.8'), true);
assert.equal(Selection.distance({x:0,y:0,z:0}, {x:3,y:4,z:0}), 5);

console.log('Vendored STEMKit no-dependency core smoke: ok');
