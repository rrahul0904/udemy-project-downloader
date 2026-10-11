import { test, expect } from '@playwright/test';

test('browser runtime executes vendored STEMKit scientific units core', async ({ page }) => {
  await page.goto('/lab');
  await expect(page.getByText('Scientific Converter', { exact: true })).toBeVisible();

  const values = await page.evaluate(async () => {
    const Units = await import('/static/vendor/stemkit-core/units.js');
    return {
      nmToAngstrom: Units.convert(1, 'length', 'nm', 'angstrom'),
      barToPa: Units.convert(1, 'pressure', 'bar', 'pa'),
      categories: Units.listAllCategories().length,
    };
  });

  expect(values.nmToAngstrom).toBe(10);
  expect(values.barToPa).toBe(100000);
  expect(values.categories).toBeGreaterThanOrEqual(10);
});

test('browser runtime executes vendored STEMKit XVG parser and sample statistics', async ({ page }) => {
  await page.goto('/lab');
  await expect(page.getByText('XVG Visualizer', { exact: true })).toBeVisible();

  const result = await page.evaluate(async () => {
    const Xvg = await import('/static/vendor/stemkit-core/xvg-parser.js');
    const parsed = Xvg.parseXvg([
      '@ title "Golden RMSD"',
      '0 0.10',
      '1 0.20',
      '2 0.30'
    ].join('\n'));
    const stats = Xvg.columnStats(Xvg.extractColumn(parsed.matrix, 1));
    return {
      title: parsed.title,
      rows: parsed.rowCount,
      mean: stats.mean,
      sd: stats.std,
    };
  });

  expect(result.title).toBe('Golden RMSD');
  expect(result.rows).toBe(3);
  expect(result.mean).toBeCloseTo(0.2, 12);
  expect(result.sd).toBeCloseTo(0.1, 12);
});

test('Plot Digitizer exposes calibrated axes, validation, log controls, and survives reopen', async ({ page }) => {
  await page.goto('/lab');

  const digitizer = page.locator('.tool-card').filter({ hasText: 'Plot Digitizer' });
  await digitizer.getByRole('button', { name: 'Open' }).click();
  await expect(page.locator('#stemkit-digitizer-calibration')).toBeVisible();
  await expect(page.locator('#digitizer-log-x')).toBeVisible();
  await expect(page.locator('#digitizer-log-y')).toBeVisible();
  await expect(page.locator('#result')).toContainText('Pixel resolution:');

  await page.locator('#digitizer-px-x2').fill('0');
  await expect(page.locator('#result')).toContainText('Calibration error:');

  const units = page.locator('.tool-card').filter({ hasText: 'Scientific Converter' });
  await units.getByRole('button', { name: 'Open' }).click();
  await expect(page.locator('#workspace-title')).toHaveText('Scientific Converter');

  await digitizer.getByRole('button', { name: 'Open' }).click();
  await expect(page.locator('#stemkit-digitizer-calibration')).toBeVisible();
  await expect(page.locator('#stemkit-digitizer-calibration')).toHaveCount(1);
});

test('MD Workflow Generator creates version-aware STEMKit PLUMED input in the browser', async ({ page }) => {
  await page.goto('/lab');

  const workflow = page.locator('.tool-card').filter({ hasText: 'MD Workflow Generator' });
  await workflow.getByRole('button', { name: 'Open' }).click();
  await expect(page.locator('#stemkit-plumed-config')).toHaveCount(1);

  await page.locator('#engine').selectOption('plumed');
  await expect(page.locator('#stemkit-plumed-config')).toBeVisible();
  await page.locator('#plumed-version').selectOption('2.9');
  await page.locator('#plumed-cv1-type').selectOption('DIHEDRAL_CORRELATION');
  await page.locator('#plumed-cv1-label').fill('corr');
  await page.locator('#plumed-cv1-atoms').fill('1,2,3,4,5,6,7,8');
  await page.locator('#plumed-bias').selectOption('none');

  await page.getByRole('button', { name: 'Generate workflow' }).click();
  await expect(page.locator('#result')).toContainText('Target PLUMED version: 2.9');
  await expect(page.locator('#result')).toContainText('corr: DIHCOR ATOMS=1,2,3,4,5,6,7,8');
  await expect(page.locator('#result')).toContainText('older action name');

  await page.locator('#plumed-version').selectOption('2.10');
  await page.getByRole('button', { name: 'Generate workflow' }).click();
  await expect(page.locator('#result')).toContainText('corr: DIHEDRAL_CORRELATION ATOMS=1,2,3,4,5,6,7,8');
});

test('Structure Inspector parses XYZ, applies atom selection, and serializes through STEMKit', async ({ page }) => {
  await page.goto('/lab');

  const structure = page.locator('.tool-card').filter({ hasText: 'Structure Inspector' });
  await structure.getByRole('button', { name: 'Open' }).click();
  await expect(page.locator('#stemkit-structure-config')).toBeVisible();

  await page.locator('#structure-format').selectOption('xyz');
  await page.locator('#structure-output-format').selectOption('pdb');
  await page.locator('#structure-selection').fill('elem:C');
  await page.locator('#structure-include-output').check();
  await page.locator('#input-data').fill([
    '3',
    'browser fixture',
    'C 0.0 0.0 0.0',
    'H 1.0 0.0 0.0',
    'O 4.0 0.0 0.0',
  ].join('\n'));

  await page.getByRole('button', { name: 'Inspect structure' }).click();
  await expect(page.locator('#result')).toContainText('Format: XYZ');
  await expect(page.locator('#result')).toContainText('Selected atoms: 1 / 3');
  await expect(page.locator('#result')).toContainText('# Converted PDB');
  await expect(page.locator('#result')).toContainText('ATOM');
});

test('Coordinate Manipulator handles XYZ transforms and GRO serialization', async ({ page }) => {
  await page.goto('/lab');

  const manipulator = page.locator('.tool-card').filter({ hasText: 'Coordinate Manipulator' });
  await manipulator.getByRole('button', { name: 'Open' }).click();
  await expect(page.locator('#stemkit-structure-config')).toBeVisible();

  await page.locator('#structure-format').selectOption('xyz');
  await page.locator('#structure-output-format').selectOption('gro');
  await page.locator('#structure-center').selectOption('geometric');
  await page.locator('#structure-rz').fill('90');
  await page.locator('#structure-scale').fill('2');
  await page.locator('#dx').fill('1');
  await page.locator('#input-data').fill([
    '2',
    'transform fixture',
    'C 0.0 0.0 0.0',
    'H 1.0 0.0 0.0',
  ].join('\n'));

  await page.getByRole('button', { name: 'Translate coordinates' }).click();
  await expect(page.locator('#result')).toContainText('STEMKit structure transform: XYZ → GRO');
  await expect(page.locator('#result')).toContainText('Transformed by Course Intelligence Study Lab');
});

test('Journal Abbreviator uses STEMKit exact rules and local-only ISO-4 LTWA upload', async ({ page }) => {
  await page.goto('/lab');

  const journal = page.locator('.tool-card').filter({ hasText: 'Journal Abbreviator' });
  await journal.getByRole('button', { name: 'Open' }).click();
  await expect(page.locator('#stemkit-journal-config')).toBeVisible();

  await page.locator('#journal-title').fill('Journal of Molecular Biology');
  await page.locator('#journal-mode').selectOption('rules');
  await page.getByRole('button', { name: 'Abbreviate' }).click();
  await expect(page.locator('#result')).toContainText('J. Mol. Biol.');
  await expect(page.locator('#result')).toContainText('Recognized exact/custom title: yes');

  await page.locator('#journal-mode').selectOption('iso4');
  await expect(page.locator('#journal-iso4-section')).toBeVisible();
  const syntheticLtwa = [
    'Word\tAbbreviation\tLanguage',
    'journal\tJ.\tEnglish',
    'molecular\tMol.\tEnglish',
    'biology\tBiol.\tEnglish',
  ].join('\n');
  await page.locator('#journal-ltwa-file').setInputFiles({
    name: 'synthetic-ltwa.tsv',
    mimeType: 'text/tab-separated-values',
    buffer: Buffer.from(syntheticLtwa),
  });
  await expect(page.locator('#journal-ltwa-status')).toContainText('3 rows parsed');

  await page.getByRole('button', { name: 'Abbreviate' }).click();
  await expect(page.locator('#result')).toContainText('J. Mol. Biol.');
  await expect(page.locator('#result')).toContainText('LTWA entries indexed: 3');
});
