#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python3}"
NODE_BIN="${NODE:-node}"
"${PYTHON_BIN}" -m unittest discover -s tests -v
"${PYTHON_BIN}" -m compileall -q app
"${PYTHON_BIN}" -m py_compile scripts/live_acceptance.py scripts/mac_practice_export.py scripts/mac_practice_companion.py
"${PYTHON_BIN}" - <<'PY'
import sqlite3
con = sqlite3.connect(':memory:')
con.execute('CREATE VIRTUAL TABLE probe USING fts5(text)')
con.execute('INSERT INTO probe(text) VALUES (?)', ('fts5 ready',))
assert con.execute("SELECT count(*) FROM probe WHERE probe MATCH 'ready'").fetchone()[0] == 1
print('SQLite FTS5: ok')
PY

if command -v "${NODE_BIN}" >/dev/null 2>&1; then
  for asset in app/static/*.js; do
    echo "Checking ${asset}"
    "${NODE_BIN}" --check "${asset}"
  done
else
  echo 'Node is unavailable; JavaScript syntax checks were not run.' >&2
  exit 1
fi

if [[ "${RUN_E2E:-0}" == "1" ]]; then
  if command -v npm >/dev/null 2>&1; then
    npm install --no-audit --no-fund
    npx playwright install --with-deps chromium
    npm run test:e2e
  elif [[ -x node_modules/.bin/playwright ]]; then
    node_modules/.bin/playwright test
  else
    echo 'npm and the local Playwright executable are unavailable.' >&2
    exit 1
  fi
fi

if [[ "${VERIFY_DOCKER:-0}" == "1" ]]; then
  docker build -t course-intelligence:verify .
fi
