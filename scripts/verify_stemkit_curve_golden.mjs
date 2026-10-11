import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import * as Curve from '../app/static/vendor/stemkit-core/curve-fitting.js';
import { registerVendor, resetVendor } from '../app/static/vendor/stemkit-core/vendor.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const regressionPath = resolve(root, 'app/static/vendor/stemkit-dependencies/regression.min.js');
const curvePath = resolve(root, 'app/static/vendor/stemkit-core/curve-fitting.js');
const vendorPath = resolve(root, 'app/static/vendor/stemkit-core/vendor.js');
const require = createRequire(import.meta.url);

function gitBlobSha(path) {
  const bytes = readFileSync(path);
  const header = Buffer.from(`blob ${bytes.length}\0`);
  return createHash('sha1').update(header).update(bytes).digest('hex');
}

// Provenance: these must remain byte-for-byte identical to the reviewed STEMKit blobs.
assert.equal(gitBlobSha(regressionPath), 'b2f8ecdac5942053bd01b5443b499b3ad6e0c039');
assert.equal(gitBlobSha(curvePath), 'a5e6e030cd3ee9579623ce6f5cc3f19ad5ba336b');
assert.equal(gitBlobSha(vendorPath), 'a22bf1c156b87bc29159913138e5e83bce6fec68');

resetVendor();
assert.throws(
  () => Curve.fitCurve([[0, 0], [1, 1]], 'linear'),
  /regression.*not registered/
);

const regression = require(regressionPath);
registerVendor({ regression });

const parsed = Curve.parseXYData('x,y\n1,2.1\n2,4.2\n3,5.9\n4,8.1\n5,9.8');
assert.equal(parsed.nonNumeric, 1);
assert.equal(parsed.data.length, 5);

const linear = Curve.fitCurve(parsed.data, 'linear');
assert.equal(linear.error, null);
assert.ok(Math.abs(linear.equation[0] - 1.93) < 1e-9);
assert.ok(Math.abs(linear.equation[1] - 0.23) < 1e-9);
assert.ok(Math.abs(linear.r2 - 0.9984185697437546) < 1e-8);
assert.ok(Math.abs(linear.rmse - 0.10862780491200198) < 1e-8);
assert.equal(linear.linearised, false);
assert.match(Curve.formatEquation(linear.equation, 'linear'), /^y = 1\.93x \+ 0\.23$/);

const quadratic = Curve.fitCurve(parsed.data, 'polynomial2');
assert.ok(Math.abs(quadratic.equation[0] - (-0.0214285714)) < 1e-5);
assert.ok(Math.abs(quadratic.equation[1] - 2.0585714286) < 1e-5);
assert.ok(Math.abs(quadratic.equation[2] - 0.08) < 1e-5);

const exponential = Curve.fitCurve([[1, 2], [2, 4.1], [3, 8.2], [4, 16.1], [5, 32.3]], 'exponential');
assert.equal(exponential.linearised, true);
assert.ok(Math.abs(exponential.equation[1] - 0.6902163057) < 1e-6);
assert.match(Curve.generateMatplotlibCode(exponential), /fitted by linearisation/i);

const invalid = Curve.fitCurve([[1, 2], [2, 0]], 'exponential');
assert.match(invalid.error, /every y > 0/);

const samples = Curve.sampleCurve(linear.predict, 1, 5, 11);
assert.equal(samples.x.length, 11);
assert.equal(samples.y.length, 11);

console.log('STEMKit regression.js curve fitting golden verification: ok');
