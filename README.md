# Local Media Downloader

A Docker-hosted local web console for archiving supported Udemy and YouTube media to your machine, with an integrated local-first Study Lab for working with downloaded course material.

This project is for content you own, created, or are otherwise authorized to access and archive for local personal use. It does not bypass DRM, paywalls, account restrictions, or access controls. Udemy practice-test export depends on authenticated Udemy JSON endpoints that may change or be unavailable for some courses.

## Run

```bash
docker compose up --build
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080).

Downloaded files are written to `./downloads`. Runtime data is written to `./data`.

## Study Lab

Open [http://127.0.0.1:8080/lab](http://127.0.0.1:8080/lab), or use the **Study Lab** button in the downloader.

Study Lab is a STEMKit-inspired, local-first course/research workbench integrated into this same FastAPI application. It currently includes 21 lightweight tools spanning:

- data cleaning, descriptive statistics, outlier detection, linear fitting, error bars, plotting, and manual plot digitization;
- XVG parsing, PDB inspection/coordinate translation, and starter molecular-dynamics workflows;
- BibTeX cleanup/deduplication, DOI → BibTeX, journal abbreviation, LaTeX tables, and equation snippets;
- scientific unit conversion;
- Pomodoro, decision-matrix, and first-order kinetics study helpers.

Compatible text/data files already present in the local downloads folder can be loaded into the active Study Lab tool through the existing guarded `/files/{relative_path}` route. Most Study Lab computations run entirely in browser JavaScript. DOI → BibTeX intentionally calls Crossref only after an explicit user action.

The first integration is a functional MVP, not a claim of exact scientific/numerical parity with STEMKit. See [`docs/STUDY_LAB.md`](docs/STUDY_LAB.md) for the architecture, attribution, current parity matrix, and recommended production follow-up.

## Supported URLs

- Udemy course URLs such as `https://www.udemy.com/course/example/`.
- YouTube video URLs such as `https://www.youtube.com/watch?v=...`, `https://youtu.be/...`, Shorts, live URLs, and explicit playlist URLs.

YouTube channel-wide downloads are intentionally not enabled by the URL guard to avoid accidentally starting very large downloads.

## Authentication

The app supports three authentication modes:

- No cookies: best for public YouTube videos.
- Local browser session: for the app running directly on your Mac. It asks `yt-dlp` to read cookies from Chrome, Safari, Firefox, Brave, Edge, Chromium, Vivaldi, or Opera.
- `cookies.txt` upload: best for Docker or restricted content. The app accepts a Netscape-format `cookies.txt` exported from your own signed-in browser session.

Udemy downloads require either a local browser session or `cookies.txt`. Private, age-restricted, or members-only YouTube videos may also require cookies from an authorized account.

Keep browser cookies private. The app stores a temporary cookie file only for the lifetime of the job and deletes its copy afterward.

## What It Downloads

- Media exposed to `yt-dlp` for the submitted Udemy or YouTube URL.
- Subtitles, descriptions, thumbnails, and metadata where available.
- Practice tests and quizzes as JSON, Markdown, local HTML, and PDF when Udemy exposes them to your authenticated session through normal JSON endpoints.

## Reference Notes

I checked the two linked downloader projects. Both are MIT-licensed and both include DRM/Widevine-oriented paths; this app intentionally does not implement those pieces. The useful compatible idea adopted here is the normal quiz-assessment endpoint shape and local practice-test export.

The Study Lab design/tool inventory was also informed by the MIT-licensed STEMKit project (`LD-Shell/stemkit`; the originally supplied `danielravina/stemkit` URL resolves to that project). This repository currently uses an independent implementation rather than vendoring STEMKit's source tree or dependency bundles. See `docs/STUDY_LAB.md` for details.

## Local Checks

```bash
python3 -m unittest discover -s tests
python3 -m compileall app
```
