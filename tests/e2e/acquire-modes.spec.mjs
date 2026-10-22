import { test, expect } from '@playwright/test';

test('Acquire submits video, practice-only, and combined modes independently', async ({ page }) => {
  const submitted = [];
  await page.route('**/api/jobs', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    submitted.push(route.request().postData());
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: `ui-${submitted.length}` }) });
  });
  await page.goto('/');
  const url = page.getByLabel('Media or course URL');
  const video = page.getByRole('checkbox', { name: 'Download videos and available resources' });
  const practice = page.getByRole('checkbox', { name: 'Export authorized Udemy practice tests' });
  const authorization = page.getByRole('checkbox', { name: /I own, created, or am otherwise authorized/ });
  const submit = page.getByRole('button', { name: 'Start archive job' });
  await expect(page.locator('#browser-row')).toBeHidden();
  await expect(page.locator('#cookies-row')).toBeHidden();

  await url.fill('https://www.youtube.com/watch?v=abc123');
  await expect(practice).toBeDisabled();
  await video.uncheck();
  await authorization.check();
  await submit.click();
  await expect(page.locator('#form-message')).toContainText('Select videos, practice tests, or both');
  expect(submitted).toHaveLength(0);

  await video.check();
  await submit.click();
  await expect.poll(() => submitted.length).toBe(1);
  expect(submitted[0]).toMatch(/name="download_videos"\r?\n\r?\ntrue/);
  expect(submitted[0]).toMatch(/name="include_practice_tests"\r?\n\r?\nfalse/);

  await url.fill('https://www.udemy.com/course/authorized-course/');
  await expect(practice).toBeEnabled();
  await expect(practice).toBeChecked();
  await expect(page.getByRole('radio', { name: 'Upload cookies.txt' })).toBeChecked();
  await expect(page.locator('#cookies-row')).toBeVisible();
  await expect(page.locator('#browser-row')).toBeHidden();
  await page.getByRole('radio', { name: 'Use local browser session' }).check();
  await expect(page.locator('#browser-row')).toBeVisible();
  await expect(page.locator('#cookies-row')).toBeHidden();
  await page.getByRole('radio', { name: 'Upload cookies.txt' }).check();
  await page.getByLabel('Cookies file').setInputFiles({
    name: 'cookies.txt', mimeType: 'text/plain', buffer: Buffer.from('# Netscape HTTP Cookie File\n'),
  });
  await video.uncheck();
  await expect(page.locator('#job-mode')).toContainText('Practice tests only');
  await authorization.check();
  await submit.click();
  await expect.poll(() => submitted.length).toBe(2);
  expect(submitted[1]).toMatch(/name="download_videos"\r?\n\r?\nfalse/);
  expect(submitted[1]).toMatch(/name="include_practice_tests"\r?\n\r?\ntrue/);

  await url.fill('https://www.udemy.com/course/authorized-course/');
  await page.getByLabel('Cookies file').setInputFiles({
    name: 'cookies.txt', mimeType: 'text/plain', buffer: Buffer.from('# Netscape HTTP Cookie File\n'),
  });
  await authorization.check();
  await expect(page.locator('#job-mode')).toContainText('Videos and authorized practice tests');
  await submit.click();
  await expect.poll(() => submitted.length).toBe(3);
  expect(submitted[2]).toMatch(/name="download_videos"\r?\n\r?\ntrue/);
  expect(submitted[2]).toMatch(/name="include_practice_tests"\r?\n\r?\ntrue/);
});

test('Acquire displays component results, reconciliation, and PDF download', async ({ page }) => {
  const job = {
    id: 'ui-result', status: 'partial', created_at: '2026-10-21T12:00:00Z',
    course_url: 'https://www.udemy.com/course/authorized-course/', platform: 'udemy',
    quality: 'best', auth_method: 'cookies_file', include_practice_tests: true,
    download_videos: true, logs: ['Video download completed.', 'Practice export incomplete.'],
    component_statuses: { video: 'succeeded', practice: 'partial' },
    practice_validation: {
      course_discovered: true, practice_sets_discovered: 2, questions_expected: 20, questions_retrieved: 18,
      questions_with_answer_choices: 18,
      questions_with_correct_answers: 16, questions_with_explanations: 12,
      count_reconciliation: 'PARTIAL', json_generated: true, html_generated: true,
      markdown_generated: true, pdf_generated: true,
    },
  };
  await page.route('**/api/jobs', (route) => route.fulfill({ json: { jobs: [job] } }));
  await page.route('**/api/downloads', (route) => route.fulfill({ json: {
    root: '/downloads', usage: { free: 1024 },
    files: [{ type: 'file', path: 'authorized-course/practice_set_1.pdf', size: 200 }],
  } }));
  await page.goto('/');
  await expect(page.locator('.job .status')).toHaveText('partial');
  await expect(page.locator('.job-meta')).toContainText('video: succeeded · practice: partial');
  await expect(page.locator('#job-details')).toContainText('Questions: 18 retrieved / 20 expected');
  await expect(page.locator('#job-details')).toContainText('Count reconciliation: PARTIAL');
  await expect(page.locator('#job-details')).toContainText('Course discovered: YES');
  await expect(page.locator('#job-details')).toContainText('Exports: JSON YES · HTML YES · MARKDOWN YES · PDF YES');
  await expect(page.getByRole('link', { name: /practice_set_1.pdf/ })).toHaveAttribute('href', '/files/authorized-course/practice_set_1.pdf');
  await page.reload();
  await expect(page.locator('#job-details')).toContainText('Questions: 18 retrieved / 20 expected');
});

test('Acquire form and console fit desktop and phone viewports', async ({ page }, testInfo) => {
  await page.route('**/api/jobs', (route) => route.fulfill({ json: { jobs: [] } }));
  await page.route('**/api/downloads', (route) => route.fulfill({ json: {
    root: 'persistent-storage', usage: { free: 1024 }, files: [],
  } }));
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /Save authorized media/ })).toBeVisible();
    await expect(page.getByRole('checkbox', { name: 'Export authorized Udemy practice tests' })).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`acquire-${viewport.width}.png`), fullPage: true });
  }
});

test('Mac browser export pairs locally, submits the course URL, and reports created files', async ({ page }) => {
  await page.addInitScript(() => {
    window.open = () => window;
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = String(input);
      if (url === 'http://127.0.0.1:8765/api/health') {
        return new Response(JSON.stringify({ status: 'ready' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url === 'http://127.0.0.1:8765/api/exports') {
        window.__macExportRequest = JSON.parse(init.body);
        return new Response(JSON.stringify({ id: 'synthetic-job', status: 'running' }), { status: 202, headers: { 'Content-Type': 'application/json' } });
      }
      if (url === 'http://127.0.0.1:8765/api/jobs/synthetic-job') {
        return new Response(JSON.stringify({
          id: 'synthetic-job', status: 'succeeded', exam_count: 2, question_count: 120,
          files: ['course/_practice-tests/exam.pdf', 'course/_practice-tests/export.json'], warnings: [],
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return originalFetch(input, init);
    };
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect Mac helper' }).click();
  await expect(page.locator('#mac-export-status')).toContainText('Approve the local pairing tab');
  await page.evaluate(() => window.dispatchEvent(new MessageEvent('message', {
    origin: 'http://127.0.0.1:8765', source: window,
    data: { type: 'course-practice-pair', token: 'synthetic-pairing-token' },
  })));
  await expect(page.locator('#mac-export-status')).toContainText('Mac helper connected');
  await page.getByLabel('Media or course URL').fill('https://www.udemy.com/course/authorized-course/');
  await page.getByRole('button', { name: 'Export Practice Exams' }).click();
  await expect(page.locator('#mac-export-status')).toContainText('SUCCEEDED: 2 exam(s), 120 question(s)');
  await expect(page.locator('#mac-export-status')).toContainText('course/_practice-tests/export.json');
  expect(await page.evaluate(() => window.__macExportRequest)).toEqual({
    url: 'https://www.udemy.com/course/authorized-course/', browser: 'chrome',
  });
  expect(await page.evaluate(() => sessionStorage.getItem('course-intelligence-mac-companion-token'))).toBe('synthetic-pairing-token');
});
