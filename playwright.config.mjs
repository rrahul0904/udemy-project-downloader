import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: 'http://127.0.0.1:8080',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: "rm -rf .tmp-e2e && mkdir -p .tmp-e2e/downloads/TestCourse .tmp-e2e/data && cp -R tests/fixtures/test-course/. .tmp-e2e/downloads/TestCourse/ && DATA_DIR=$PWD/.tmp-e2e/data DOWNLOAD_DIR=$PWD/.tmp-e2e/downloads APP_ENV=development uvicorn app.main:app --host 127.0.0.1 --port 8080",
    url: 'http://127.0.0.1:8080/api/health',
    reuseExistingServer: false,
    timeout: 30000,
  },
});
