import { defineConfig } from '@playwright/test';

const appPort = process.env.APP_PORT || '8080';
const baseURL = process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${appPort}`;
const python = process.env.PYTHON || 'python';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 1,
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `rm -rf .tmp-e2e && mkdir -p .tmp-e2e/downloads/TestCourse .tmp-e2e/data && cp -R tests/fixtures/test-course/. .tmp-e2e/downloads/TestCourse/ && DATA_DIR=$PWD/.tmp-e2e/data DOWNLOAD_DIR=$PWD/.tmp-e2e/downloads APP_ENV=development ${python} -m uvicorn app.main:app --host 127.0.0.1 --port ${appPort}`,
    url: `${baseURL}/api/health`,
    reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER === '1',
    timeout: 30000,
  },
});
