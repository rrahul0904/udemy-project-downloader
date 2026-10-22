# Claude certification practice export

`cleaned_courses.json` is the canonical 69-course inventory. Its SHA-256 is
`12e17f04acc5bb36b6a2eff4f9d47b82244d1feda60a874efc814af654836e3d`.
The manifest contains 25 CCAO-F, 9 CCDV-F, 17 CCAR-F, 13 CCAR-P, 4
ARCHITECT-VERIFY, and 1 OTHER-CLAUDE course. The last two groups remain
separate pending explicit classification review.

Run from this repository on the Mac host with an authorized Udemy enrollment
and a signed-in Chrome session:

```bash
.venv/bin/python scripts/claude_certification_batch.py --scan-only
.venv/bin/python scripts/claude_certification_batch.py --browser chrome --delay 2
.venv/bin/python scripts/claude_question_bank.py
```

The batch script reads browser credentials into memory through the existing
host-side exporter. It creates no `cookies.txt`, uploads no credentials, and
does not use Docker to read a browser profile. It processes courses
sequentially, checkpoints `downloads/claude-certifications/progress.json`
after each course, and skips exports whose complete evidence still validates.
`--group CCAO-F` or `--limit 1` narrows a run. A rate-limit response stops the
batch. A failed or partial course remains visible and can be retried without
repeating complete exports.

Private outputs under the gitignored `downloads/claude-certifications/` folder:

- `progress.json` and `progress.md`: every course, state, actual quiz IDs,
  counts, warnings, and paths.
- `<GROUP>/<SLUG>/_practice-tests/`: original per-course JSON, HTML,
  Markdown, consolidated PDF, one PDF per quiz, and verification report.
- `<GROUP>/question-bank.{json,html,md,pdf}`: distinct questions with every
  source instance retained. The JSON keeps source-specific answer and
  explanation variants. A conflicting or unlinked answer key is flagged;
  no answer is invented.
- `<GROUP>/duplicates.json`: exact-content and same-stem potential duplicate
  clusters. Cross-certification matches are logged separately and not merged.
- `summary.json` and `summary.md`: observed totals by group. Pending,
  inaccessible, failed, and partial courses are reported explicitly.

The distinction between a code test and a live export matters. Run unit tests
with `.venv/bin/python -m unittest discover -s tests -q`; validate the local
question-bank files, PDF page counts, and representative rendered pages before
describing an export as verified. Keep proprietary question text and all local
question-bank artifacts out of Git and public deployments.
