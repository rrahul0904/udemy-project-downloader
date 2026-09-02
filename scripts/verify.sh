#!/usr/bin/env bash
set -euo pipefail

python -m unittest discover -s tests -v
python -m compileall -q app
python -m py_compile scripts/live_acceptance.py
python - <<'PY'
import sqlite3
con = sqlite3.connect(':memory:')
con.execute('CREATE VIRTUAL TABLE probe USING fts5(text)')
con.execute('INSERT INTO probe(text) VALUES (?)', ('fts5 ready',))
assert con.execute("SELECT count(*) FROM probe WHERE probe MATCH 'ready'").fetchone()[0] == 1
print('SQLite FTS5: ok')
PY

if command -v node >/dev/null 2>&1; then
  for asset in app/static/*.js; do
    echo "Checking ${asset}"
    node --check "${asset}"
  done
else
  echo 'Node is unavailable; JavaScript syntax checks were not run.' >&2
  exit 1
fi

if [[ "${RUN_E2E:-0}" == "1" ]]; then
  npm install --no-audit --no-fund
  npx playwright install --with-deps chromium
  npm run test:e2e
fi

if [[ "${VERIFY_DOCKER:-0}" == "1" ]]; then
  docker build -t course-intelligence:verify .
fi
