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
  await expect(page.locator('#transcript').getByText(/durable transcript search with SQLite FTS5/i)).toBeVisible();

  await page.locator('#transcript-search').fill('SQLite FTS5');
  await expect(page.locator('#search-count')).toContainText('1 match');

  const bookmarkButton = page.locator('.segment').nth(1).locator('.bookmark');
  const bookmarkClass = await bookmarkButton.getAttribute('class');
  if (!bookmarkClass?.split(/\s+/).includes('saved')) {
    await bookmarkButton.click();
  }

  await page.getByRole('tab', { name: 'Notes', exact: true }).click();
  await page.locator('#lesson-notes').fill('Persistent browser smoke note');
  await page.getByRole('button', { name: 'Save notes' }).click();
  await expect(page.locator('#note-status')).toContainText('Saved');

  await page.reload();
  await page.getByRole('button', { name: /Introduction/ }).first().click();
  await page.getByRole('tab', { name: 'Notes', exact: true }).click();
  await expect(page.locator('#lesson-notes')).toHaveValue('Persistent browser smoke note');
  await page.getByRole('tab', { name: 'Bookmarks', exact: true }).click();
  await expect(page.locator('#bookmark-list')).toContainText('SQLite FTS5');

  await page.locator('#library-search').fill('SQLite FTS5');
  await expect(page.locator('#library-search-results')).toContainText('Production Test Course');
});

test('synchronized viewer exposes transcript variants exports and durable progress', async ({ page }) => {
  const response = await page.request.get('/api/v1/courses');
  expect(response.ok()).toBeTruthy();
  const library = await response.json();
  const lesson = library.courses[0].lessons[0];
  expect(lesson.transcripts.length).toBeGreaterThan(0);

  await page.goto(`/viewer?lesson=${encodeURIComponent(lesson.id)}`);
  await expect(page.getByRole('heading', { name: /Introduction/i })).toBeVisible();
  await expect(page.locator('#transcript-source')).toHaveValue(lesson.transcripts[0].id);
  await expect(page.locator('#transcript')).toContainText('SQLite FTS5');
  await page.locator('#transcript-search').fill('SQLite FTS5');
  await expect(page.locator('#search-count')).toContainText('1 match');
  await expect(page.locator('#export-txt')).toHaveAttribute('href', /\/api\/v1\/transcripts\/.+\/export\?format=txt/);

  await page.getByRole('button', { name: 'Mark lesson complete' }).click();
  await expect(page.getByRole('button', { name: /Completed/ })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: /Completed/ })).toBeVisible();
});

test('study lab loads and discovers compatible course fixture', async ({ page }) => {
  await page.goto('/lab');
  await expect(page.getByText('Statistics Calculator', { exact: true })).toBeVisible();
  await expect(page.locator('#course-file')).toContainText('data.txt');
  await page.getByRole('button', { name: 'Open' }).first().click();
  await expect(page.locator('#workspace-title')).toContainText('Statistics Calculator');
});
