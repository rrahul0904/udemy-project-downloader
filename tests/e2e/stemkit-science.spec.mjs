import { test, expect } from '@playwright/test';

test('Study Lab scientific converter uses vendored STEMKit units core', async ({ page }) => {
  await page.goto('/lab');

  const card = page.locator('.tool-card').filter({ hasText: 'Scientific Converter' });
  await card.getByRole('button', { name: 'Open' }).click();
  await expect(page.locator('#workspace-title')).toHaveText('Scientific Converter');

  await page.locator('#unit-category').selectOption('length');
  await page.locator('#unit-value').fill('1');
  await page.locator('#unit-from').selectOption('nm');
  await page.locator('#unit-to').selectOption('angstrom');
  await page.getByRole('button', { name: 'Convert' }).click();

  await expect(page.locator('#result')).toContainText('1 nm = 10 Å');
});

test('Study Lab XVG visualizer reports deterministic sample statistics from vendored core', async ({ page }) => {
  await page.goto('/lab');

  const card = page.locator('.tool-card').filter({ hasText: 'XVG Visualizer' });
  await card.getByRole('button', { name: 'Open' }).click();
  await expect(page.locator('#workspace-title')).toHaveText('XVG Visualizer');

  await page.locator('#input-data').fill([
    '@ title "Golden RMSD"',
    '0 0.10',
    '1 0.20',
    '2 0.30'
  ].join('\n'));
  await page.getByRole('button', { name: 'Parse XVG' }).click();

  await expect(page.locator('#result')).toContainText('Title: Golden RMSD');
  await expect(page.locator('#result')).toContainText('Rows: 3');
  await expect(page.locator('#result')).toContainText('Mean: 0.2');
  await expect(page.locator('#result')).toContainText('Sample SD: 0.1');
  await expect(page.locator('#plot-output')).toBeVisible();
});
