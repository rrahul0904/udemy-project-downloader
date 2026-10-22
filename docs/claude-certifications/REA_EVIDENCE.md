# Claude certification extraction: Agent Work OS / REA evidence

Run date: 2026-10-22 UTC. This is a sanitized execution record. The
course material, question banks, per-course reports, and detailed ledger
remain in the gitignored local `downloads/claude-certifications/` directory.

## Inventory and access

- The supplied manifest SHA-256 is
  `12e17f04acc5bb36b6a2eff4f9d47b82244d1feda60a874efc814af654836e3d`.
  Its 83 input positions contain 14 repeat occurrences, leaving 69 unique
  course slugs: 43 from the original batch and 26 added.
- The existing macOS host exporter read the user's authorized Chrome session
  into process memory. It did not create or upload a cookies file. A direct
  Architect quiz and one Associate course passed live acceptance gates before
  the sequential, checkpointed batch.
- Each of the 69 course records has a course ID, actual title, quiz IDs,
  observed counts, state, warning list, output paths, evidence timestamp, and
  SHA-256 of its source JSON. The independent verifier reconciled those
  records with the saved files.

## Observed results

| Group | Courses | Complete | Partial | Exported quizzes | Raw question instances | Distinct fingerprints |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CCAO-F | 25 | 23 | 2 | 157 | 8,564 | 7,798 |
| CCDV-F | 9 | 9 | 0 | 50 | 3,153 | 2,334 |
| CCAR-F | 17 | 16 | 1 | 81 | 4,912 | 4,908 |
| CCAR-P | 13 | 13 | 0 | 63 | 4,861 | 3,879 |
| ARCHITECT-VERIFY | 4 | 2 | 2 | 25 | 1,250 | 1,250 |
| OTHER-CLAUDE | 1 | 1 | 0 | 6 | 550 | 547 |
| **Total** | **69** | **64** | **5** | **382** | **23,290** | **20,716** |

`ARCHITECT-VERIFY` remains separate because the certification level was not
established for all four courses. `OTHER-CLAUDE` is a general Claude Prompt
Engineering course and remains outside the certification totals.

## Partial courses

- `CCAO-F-02`: 24 quizzes and 234 questions exported; three additional
  assessment endpoints returned 404. The same 404s appear twice in the
  source warnings because both endpoint attempts were recorded.
- `CCAO-F-15`: 5 quizzes and 120 questions exported; three assessment
  endpoints returned 404.
- `CCAR-F-10`: 2 quizzes and 114 questions exported; 60 questions have no
  source explanation, although all 114 source answer links were present.
- `ARCHITECT-VERIFY-02`: 9 quizzes and 130 questions exported; seven
  assessment endpoints returned 404.
- `ARCHITECT-VERIFY-04`: 6 quizzes and 360 questions exported; two questions
  have no source explanation.

These five records are **partial**, even though their available questions and
PDFs were saved. The endpoint failures were not bypassed and the missing
explanations were not invented.

## Deduplication and validation

The manifest deduplicates course URLs by normalized slug. Certification banks
deduplicate exact normalized question stem and option sets while retaining
every course, quiz, question, answer, and explanation source instance. Exact
duplicate clusters by group are 379, 478, 4, 501, 0, and 3 in the table's
order; 59 additional same-stem clusters are flagged for human review. No
cross-certification exact match was found, and none was merged. The source
data produced no conflicting or unlinked answer keys. Eight distinct
questions have repeated option text and remain flagged.

The independent verifier checked 69 per-course PDFs, 382 per-quiz PDFs, and
six group PDFs for readable pages, as well as question counts, source JSON
hashes, provenance totals, and 12 rendered sample pages (first and middle
page of each group PDF). The full local test suite passed 128 tests. These
checks establish faithful export and readable outputs; they do not establish
the factual correctness of third-party exam answers or completeness of the
source courses beyond what the authorized endpoints returned.

## Reproduction and private receipts

Run the commands in [README.md](README.md) on the authorized Mac host. The
local `progress.json` and `progress.md` contain all 69 course states. The
local `summary.json`, per-group `summary.json`, `duplicates.json`, and
question-bank files contain observed totals and provenance. The independent
`verification-receipt.json` records the tested repository SHA, timestamp,
course and PDF counts, and test result. All of these are gitignored because
they are either source material or detailed private extraction evidence.
