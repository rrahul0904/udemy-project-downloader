import { test, expect } from '@playwright/test';

test('primary product surfaces load and navigate in every direction', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Jobs' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Course Intelligence' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Study Lab' })).toBeVisible();

  await page.getByRole('link', { name: 'Course Intelligence' }).click();
  await expect(page).toHaveURL(/\/learn$/);
  await expect(page.getByRole('heading', { name: /searchable study workspace/i })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Downloader' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Study Lab' })).toBeVisible();

  await page.getByRole('link', { name: 'Downloader' }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole('link', { name: 'Study Lab' }).click();
  await expect(page).toHaveURL(/\/lab$/);
  await expect(page.getByText('Statistics Calculator', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Downloader' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Course Intelligence' })).toBeVisible();

  await page.getByRole('link', { name: 'Course Intelligence' }).click();
  await expect(page).toHaveURL(/\/learn$/);
  await page.getByRole('link', { name: 'Study Lab' }).click();
  await expect(page).toHaveURL(/\/lab$/);
  await page.getByRole('link', { name: 'Downloader' }).click();
  await expect(page).toHaveURL(/\/$/);
});

test('course intelligence persists notes and bookmarks and searches FTS', async ({ page }) => {
  await page.goto('/learn');
  const lesson = page.getByRole('button', { name: /Introduction/ }).first();
  await expect(lesson).toBeVisible();
  await lesson.click();
  await expect(page.getByText(/durable transcript search with SQLite FTS5/i)).toBeVisible();

  await page.locator('#transcript-search').fill('SQLite FTS5');
  await expect(page.locator('#search-count')).toContainText('1 match');

  await page.locator('.segment').nth(1).locator('.bookmark').click();
  await page.getByRole('button', { name: 'Notes', exact: true }).click();
  await page.locator('#lesson-notes').fill('Persistent browser smoke note');
  await page.getByRole('button', { name: 'Save notes' }).click();
  await expect(page.locator('#note-status')).toContainText('Saved');

  await page.reload();
  await page.getByRole('button', { name: /Introduction/ }).first().click();
  await page.getByRole('button', { name: 'Notes', exact: true }).click();
  await expect(page.locator('#lesson-notes')).toHaveValue('Persistent browser smoke note');
  await page.getByRole('button', { name: 'Bookmarks', exact: true }).click();
  await expect(page.locator('#bookmark-list')).toContainText('SQLite FTS5');

  await page.locator('#library-search').fill('SQLite FTS5');
  await expect(page.locator('#library-search-results')).toContainText('Production Test Course');
});

test('study lab loads and discovers compatible course fixture', async ({ page }) => {
  await page.goto('/lab');
  await expect(page.getByText('Statistics Calculator', { exact: true })).toBeVisible();
  await expect(page.locator('#course-file')).toContainText('data.txt');
  await page.getByRole('button', { name: 'Open' }).first().click();
  await expect(page.locator('#workspace-title')).toContainText('Statistics Calculator');
});
