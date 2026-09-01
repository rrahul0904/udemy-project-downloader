# Product Positioning

## Local-first Course Intelligence OS

The product is not intended to be a shallow YouTube transcript clone. Its differentiated loop is:

```text
AUTHORIZED SOURCE
      ↓
ARCHIVE
      ↓
COURSE / SECTION / LESSON
      ↓
MULTI-SOURCE TRANSCRIPT
      ↓
SEARCH + SYNCHRONIZED VIEWER
      ↓
CITED NOTES / FLASHCARDS / QUIZ / GRAPH
      ↓
GROUNDED TUTOR
      ↓
ACTIVE RECALL + MASTERY
      ↓
STUDY LAB / ATTACHMENTS
      ↓
EXPORT / API / MCP
```

## Differentiators

- Udemy + YouTube + local/imported media rather than YouTube-only
- user-controlled authorized archive
- local-first persistence and offline-friendly workflows
- course/section/lesson hierarchy rather than a flat transcript list
- downloaded attachments and practice-test artifacts
- Course Intelligence and Study Lab in one application
- optional AI; local parsing/search/viewing remain useful with AI disabled
- citations back to exact transcript evidence for generated study artifacts
- API/MCP should reuse the same application services, not duplicate logic

## Product principles

1. **Source traceability first.** Generated learning material must retain transcript/segment/timestamp evidence.
2. **Local value before cloud scale.** Core study workflows must not depend on hosted billing or multi-tenancy.
3. **Authorized acquisition only.** Do not bypass DRM, paywalls or access controls.
4. **One domain model.** UI, API, exports and agents operate on the same Course/Section/Lesson/Transcript objects.
5. **Scientific humility.** Study Lab tools are only called parity-complete when independently validated.
6. **Portable knowledge.** Users must be able to export/backup study state without being trapped in one UI.

## Intentionally excluded from the current private/local product

- commercial credit ledger
- Stripe billing
- hosted anonymous multi-tenancy
- cloud sync as a requirement

Those may become optional later, but they must not block structural correctness or the local learning loop.
