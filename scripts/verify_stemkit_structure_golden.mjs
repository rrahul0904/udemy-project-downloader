import assert from 'node:assert/strict';

import * as Structure from '../app/static/vendor/stemkit-core/structure.js';
import * as Selection from '../app/static/vendor/stemkit-core/selection.js';

function close(actual, expected, tolerance = 1e-9, message = '') {
  assert.ok(Number.isFinite(actual), `${message || 'value'} should be finite`);
  assert.ok(Math.abs(actual - expected) <= tolerance,
    `${message || 'value'}: expected ${expected} ± ${tolerance}, got ${actual}`);
}

// XYZ parsing and attribute selection.
const xyz = [
  '4',
  'selection fixture',
  'C 0.0 0.0 0.0',
  'H 1.0 0.0 0.0',
  'O 4.0 0.0 0.0',
  'N 0.0 3.0 0.0',
].join('\n');
const parsedXyz = Structure.parseStructure(xyz, 'xyz');
assert.equal(parsedXyz.format, 'xyz');
assert.equal(parsedXyz.unit, 'A');
assert.equal(parsedXyz.atoms.length, 4);

const carbon = Selection.selectAtoms(parsedXyz.atoms, 'elem:C', {
  unit: 'A', coordinateUnit: parsedXyz.unit,
});
assert.equal(carbon.count, 1);
assert.equal(carbon.atoms[0].element, 'C');

const nearCarbon = Selection.selectAtoms(parsedXyz.atoms, 'within:1.5,elem:C', {
  unit: 'A', coordinateUnit: parsedXyz.unit,
});
assert.equal(nearCarbon.count, 2);
assert.deepEqual(new Set(nearCarbon.atoms.map(atom => atom.element)), new Set(['C', 'H']));

const summary = Selection.selectionSummary(nearCarbon.atoms);
assert.equal(summary.nAtoms, 2);
assert.equal(summary.elements.C, 1);
assert.equal(summary.elements.H, 1);

// Named groups and residue-aware expansion on a PDB fixture.
const pdb = [
  'ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00           N',
  'ATOM      2  CA  ALA A   1       1.000   0.000   0.000  1.00 20.00           C',
  'HETATM    3  O   HOH B   2       5.000   0.000   0.000  1.00 20.00           O',
].join('\n');
const parsedPdb = Structure.parseStructure(pdb, 'pdb');
const protein = Selection.selectAtoms(parsedPdb.atoms, 'protein:', {
  unit: 'A', coordinateUnit: parsedPdb.unit,
});
assert.equal(protein.count, 2);
const backboneByResidue = Selection.selectAtoms(parsedPdb.atoms, 'atom:CA', {
  unit: 'A', coordinateUnit: parsedPdb.unit, byres: true,
});
assert.equal(backboneByResidue.count, 2);

// Transform geometry: center -> rotate -> scale -> translate.
let transformed = Structure.centreAtoms(parsedXyz.atoms, 'geometric');
const center = Structure.geometricCentre(transformed);
close(center.x, 0, 1e-12, 'center X');
close(center.y, 0, 1e-12, 'center Y');
close(center.z, 0, 1e-12, 'center Z');
transformed = Structure.rotateAtoms(transformed, 0, 0, 90, { x: 0, y: 0, z: 0 });
transformed = Structure.scaleAtoms(transformed, 2);
transformed = Structure.translateAtoms(transformed, 1, -2, 3);
assert.equal(transformed.length, 4);

// Cross-format conversion preserves atom count and converts Å to nm for GRO.
const groText = Structure.formatStructure(parsedXyz.atoms, 'gro', {
  sourceUnit: parsedXyz.unit,
  box: [2, 2, 2],
  title: 'Golden GRO conversion',
});
const parsedGro = Structure.parseStructure(groText, 'gro');
assert.equal(parsedGro.format, 'gro');
assert.equal(parsedGro.unit, 'nm');
assert.equal(parsedGro.atoms.length, 4);
close(parsedGro.atoms[1].x, 0.1, 1e-3, 'Å to nm conversion');

const pdbRoundTrip = Structure.formatStructure(parsedGro.atoms, 'pdb', {
  sourceUnit: parsedGro.unit,
  box: parsedGro.box,
  boxVectors: parsedGro.boxVectors,
});
const reparsedPdb = Structure.parseStructure(pdbRoundTrip, 'pdb');
assert.equal(reparsedPdb.atoms.length, 4);
close(reparsedPdb.atoms[1].x, 1.0, 1e-3, 'nm back to Å conversion');

// Invalid selection terms fail softly with explicit errors rather than silently selecting nonsense.
const invalid = Selection.selectAtoms(parsedXyz.atoms, 'within:not-a-radius,elem:C', {
  unit: 'A', coordinateUnit: parsedXyz.unit,
});
assert.ok(invalid.errors.length > 0);

console.log('STEMKit structure/selection golden fixtures: ok');
