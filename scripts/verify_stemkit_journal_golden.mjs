import assert from 'node:assert/strict';

import * as Journals from '../app/static/vendor/stemkit-core/journals.js';
import * as Iso4 from '../app/static/vendor/stemkit-core/iso4.js';

// Whole-title engine: normalization, custom override, and block replacement.
const customText = [
  'Journal of Molecular Biology = J. Mol. Biol.',
  'Journal of Chemical Physics = J. Chem. Phys.',
  'Energy and Environmental Science = Energy Environ. Sci.',
].join('\n');
const custom = Journals.parseCustomRules(customText);
assert.equal(custom.length, 3);
const engine = Journals.buildEngine([], custom);
assert.equal(Journals.abbreviate('The Journal of Molecular Biology', engine.lookup), 'J. Mol. Biol.');
assert.equal(Journals.abbreviate('Energy & Environmental Science', engine.lookup), 'Energy Environ. Sci.');
const processed = Journals.processText(
  'Results appeared in Journal of Chemical Physics and Journal of Molecular Biology.',
  engine
);
assert.match(processed.text, /J\. Chem\. Phys\./);
assert.match(processed.text, /J\. Mol\. Biol\./);
assert.equal(processed.replacements.length, 2);

// Synthetic LTWA fixture. This repository intentionally does not redistribute
// the ISSN LTWA data; tests exercise the parser/engine using independently
// authored rows with the same documented shape.
const ltwa = [
  'Word\tAbbreviation\tLanguage',
  'journal\tJ.\tEnglish',
  'molecular\tMol.\tEnglish',
  'biology\tBiol.\tEnglish',
  'chemical\tChem.\tEnglish',
  'physics\tPhys.\tEnglish',
  'international\tInt.\tEnglish',
  'research\tRes.\tEnglish',
  'nature\tn.a.\tEnglish',
].join('\n');
const parsed = Iso4.parseLTWA(ltwa);
assert.equal(parsed.stats.parsed, 8);
assert.equal(parsed.stats.skipped, 0);
assert.equal(parsed.stats.delimiter, '\t');

const iso = Iso4.buildIso4Engine(parsed.entries, { languages: ['en'] });
assert.equal(iso.entryCount, 8);
const title = Iso4.abbreviateTitle('Journal of Molecular Biology', iso);
assert.equal(title.abbreviation, 'J. Mol. Biol.');
assert.equal(title.changed, true);
assert.deepEqual(title.unmatched, []);

const stopWords = Iso4.abbreviateTitle('International Journal of Chemical Physics', iso);
assert.equal(stopWords.abbreviation, 'Int. J. Chem. Phys.');
assert.equal(stopWords.changed, true);

const noAbbreviation = Iso4.abbreviateTitle('Nature Research', iso);
assert.equal(noAbbreviation.abbreviation, 'Nature Res.');
assert.ok(noAbbreviation.words.some(word => word.reason === 'no-abbreviation'));

const single = Iso4.abbreviateTitle('Nature', iso);
assert.equal(single.abbreviation, 'Nature');
assert.equal(single.changed, false);

const unknown = Iso4.abbreviateTitle('Journal of Quantum Widgets', iso);
assert.equal(unknown.abbreviation, 'J. Quantum Widgets');
assert.deepEqual(unknown.unmatched, ['Quantum', 'Widgets']);

// Convenience loader should apply language filtering and report source stats.
const loaded = Iso4.loadIso4(ltwa, { languages: ['en'] });
assert.equal(loaded.stats.indexed, 8);
assert.equal(Iso4.abbreviateTitle('Journal of Molecular Biology', loaded.engine).abbreviation, 'J. Mol. Biol.');

console.log('STEMKit journal/ISO-4 golden fixtures: ok');
