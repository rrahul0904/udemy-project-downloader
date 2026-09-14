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
