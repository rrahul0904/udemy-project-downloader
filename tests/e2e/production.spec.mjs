import { test, expect } from '@playwright/test';

test('Course Intelligence OS navigation connects Library Acquire Learn Work Files and Settings', async ({ page }) => {
  await page.goto('/home');
  await expect(page.getByRole('heading', { name: /Pick up where you left off/i })).toBeVisible();
  let primary = page.getByRole('navigation', { name: 'Primary' });
  for (const name of ['Library', 'Acquire', 'Learn', 'Work', 'Files']) {
    await expect(primary.getByRole('link', { name, exact: true })).toBeVisible();
  }

  await primary.getByRole('link', { name: 'Acquire', exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: /Archive course material/i })).toBeVisible();
  await expect(page.getByText('I am authorized to archive this content for local personal use.')).toBeVisible();

  primary = page.getByRole('navigation', { name: 'Primary' });
  await primary.getByRole('link', { name: 'Learn', exact: true }).click();
  await expect(page).toHaveURL(/\/learn/);
  await expect(page.getByRole('heading', { name: 'Course Intelligence', exact: true })).toBeVisible();

  primary = page.getByRole('navigation', { name: 'Primary' });
  await primary.getByRole('link', { name: 'Work', exact: true }).click();
  await expect(page).toHaveURL(/\/lab$/);
  await expect(page.getByText('Statistics Calculator', { exact: true })).toBeVisible();

  primary = page.getByRole('navigation', { name: 'Primary' });
  await primary.getByRole('link', { name: 'Files', exact: true }).click();
  await expect(page).toHaveURL(/\/files-ui$/);
  await expect(page.getByRole('heading', { name: 'Downloaded files' })).toBeVisible();

  await page.getByRole('link', { name: 'Settings' }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
});

test('course intelligence persists personal notes and bookmarks and keeps grounded artifacts separate', async ({ page }) => {
  await page.goto('/learn');
  const lesson = page.getByRole('button', { name: /Introduction/ }).first();
  await expect(lesson).toBeVisible();
  await lesson.click();

  await page.getByRole('tab', { name: 'Transcript', exact: true }).click();
  await expect(page.locator('#transcript').getByText(/durable transcript search with SQLite FTS5/i)).toBeVisible();
  await page.locator('#transcript-search').fill('SQLite FTS5');
  await expect(page.locator('#search-count')).toContainText('1 match');

  const bookmarkButton = page.locator('.segment').nth(1).locator('.bookmark');
  const bookmarkClass = await bookmarkButton.getAttribute('class');
  if (!bookmarkClass?.split(/\s+/).includes('saved')) await bookmarkButton.click();

  await page.getByRole('tab', { name: 'My Notes', exact: true }).click();
  await expect(page.getByText(/Generated study material will never overwrite your personal notes/i)).toBeVisible();
  await page.locator('#lesson-notes').fill('Persistent browser smoke note');
  await page.getByRole('button', { name: 'Save notes' }).click();
  await expect(page.locator('#note-status')).toContainText('Saved');

  await page.getByRole('tab', { name: 'AI Notes', exact: true }).click();
  await page.getByRole('button', { name: /Generate notes|Regenerate/ }).click();
  await expect(page.locator('#ai-notes-content')).toContainText('SQLite FTS5');
  await expect(page.locator('#ai-notes-content').locator('.source-citation').first()).toBeVisible();

  await page.getByRole('tab', { name: 'Ask Course', exact: true }).click();
  await page.locator('#ask-course-input').fill('SQLite FTS5');
  await page.getByRole('button', { name: 'Find evidence' }).click();
  await expect(page.locator('#ask-course-result')).toContainText('COURSE_GROUNDED');
  await expect(page.locator('#ask-course-result')).toContainText('SQLite FTS5');

  await page.reload();
  await page.getByRole('button', { name: /Introduction/ }).first().click();
  await page.getByRole('tab', { name: 'My Notes', exact: true }).click();
  await expect(page.locator('#lesson-notes')).toHaveValue('Persistent browser smoke note');
  await page.getByRole('tab', { name: 'Bookmarks', exact: true }).click();
  await expect(page.locator('#bookmark-list')).toContainText('SQLite FTS5');
});

test('synchronized viewer exposes sources exports bookmarks deep links and durable progress', async ({ page }) => {
  const response = await page.request.get('/api/v1/courses');
  expect(response.ok()).toBeTruthy();
  const library = await response.json();
  const lesson = library.courses[0].lessons[0];
  expect(lesson.transcripts.length).toBeGreaterThan(0);

  await page.goto(`/viewer?lesson=${encodeURIComponent(lesson.id)}&t=4000`);
  await expect(page.getByRole('heading', { name: /Introduction/i })).toBeVisible();
  await expect(page.locator('#transcript-source')).toHaveValue(lesson.transcripts[0].id);
  await expect(page.locator('#transcript')).toContainText('SQLite FTS5');
  await page.locator('#transcript-search').fill('SQLite FTS5');
  await expect(page.locator('#search-count')).toContainText('1 match');
  await expect(page.locator('#export-txt')).toHaveAttribute('href', /\/api\/v1\/transcripts\/.+\/export\?format=txt/);

  const matching = page.locator('.segment').filter({ hasText: 'SQLite FTS5' }).first();
  await expect(matching).toBeVisible();
  const bookmark = matching.locator('.segment-bookmark');
  if ((await bookmark.textContent())?.trim() !== '★') await bookmark.click();
  await expect(bookmark).toHaveText('★');

  await page.getByRole('button', { name: 'Mark lesson complete' }).click();
  await expect(page.getByRole('button', { name: /Completed/ })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: /Completed/ })).toBeVisible();
});

test('Study Lab filters the 21-tool catalog and loads compatible course files', async ({ page }) => {
  await page.goto('/lab');
  await expect(page.getByText('Statistics Calculator', { exact: true })).toBeVisible();
  await expect(page.locator('#course-file')).toContainText('data.txt');

  await page.getByRole('button', { name: 'Molecular', exact: true }).click();
  await expect(page.getByText('XVG Visualizer', { exact: true })).toBeVisible();
  await expect(page.getByText('Statistics Calculator', { exact: true })).toBeHidden();

  await page.getByRole('button', { name: /All 21/ }).click();
  await page.getByRole('button', { name: 'Open' }).first().click();
  await expect(page.locator('#workspace-title')).toContainText('Statistics Calculator');
  await expect(page.locator('#recent-tools')).toContainText('Statistics Calculator');
});

test('key learning surfaces avoid horizontal overflow on a phone viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ['/home', '/', '/learn', '/lab']) {
    await page.goto(path);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  }

  const response = await page.request.get('/api/v1/courses');
  const library = await response.json();
  const lesson = library.courses[0].lessons[0];
  await page.goto(`/viewer?lesson=${encodeURIComponent(lesson.id)}`);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});
