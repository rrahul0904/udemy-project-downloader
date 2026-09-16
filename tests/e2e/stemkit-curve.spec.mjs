import { test, expect } from '@playwright/test';

test('Curve Fitter uses the regression.js-backed STEMKit path for nonlinear models', async ({ page }) => {
  await page.goto('/lab');

  const curve = page.locator('.tool-card').filter({ hasText: 'Curve Fitter' });
  await curve.getByRole('button', { name: 'Open' }).click();

  await expect(page.locator('#curve-model')).toBeVisible();
  await expect(page.locator('[data-curve-engine-status]')).toContainText('STEMKit core + regression.js 2.0.1');

  await page.locator('#curve-model').selectOption('polynomial2');
  await page.locator('#input-data').fill('1,2.1\n2,4.2\n3,5.9\n4,8.1\n5,9.8');
  await page.getByRole('button', { name: 'Fit curve' }).click();

  await expect(page.locator('#result')).toContainText('model = polynomial2');
  await expect(page.locator('#result')).toContainText('adjusted R² =');
  await expect(page.locator('#result')).toContainText('RMSE =');
  await expect(page.locator('#plot-output svg')).toBeVisible();

  await page.locator('#curve-model').selectOption('exponential');
  await page.locator('#input-data').fill('1,2\n2,4.1\n3,8.2\n4,16.1\n5,32.3');
  await page.getByRole('button', { name: 'Fit curve' }).click();
  await expect(page.locator('#result')).toContainText('model = exponential');
  await expect(page.locator('#result')).toContainText('fit by regression.js linearisation');

  await page.locator('#input-data').fill('1,2\n2,0');
  await page.getByRole('button', { name: 'Fit curve' }).click();
  await expect(page.locator('#result')).toContainText('Error: Exponential models require every y > 0');
});
