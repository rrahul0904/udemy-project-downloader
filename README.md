# Udemy Project Downloader

A Docker-hosted local web console for archiving Udemy course media and best-effort practice-test or quiz data to your machine.

This project is for content you are authorized to access and archive for local personal use. It does not bypass DRM, paywalls, account restrictions, or Udemy access controls. Practice-test export depends on authenticated Udemy JSON endpoints that may change or be unavailable for some courses.

## Run

```bash
docker compose up --build
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080).

Downloaded files are written to `./downloads`. Runtime data is written to `./data`.

## Authentication

The app supports two authentication modes:

- Local browser session: for the app running directly on your Mac. It asks `yt-dlp` to read cookies from Chrome, Safari, Firefox, Brave, Edge, Chromium, Vivaldi, or Opera.
- `cookies.txt` upload: best for Docker. The app accepts a Netscape-format `cookies.txt` exported from your own signed-in browser session.

Keep browser cookies private. The app stores a temporary cookie file only for the lifetime of the job and deletes its copy afterward.

## What It Downloads

- Course videos exposed to `yt-dlp` for the submitted Udemy URL.
- Subtitles, descriptions, thumbnails, and metadata where available.
- Practice tests and quizzes as JSON, Markdown, and local HTML when Udemy exposes them to your authenticated session through normal JSON endpoints.

## Reference Notes

I checked the two linked downloader projects. Both are MIT-licensed and both include DRM/Widevine-oriented paths; this app intentionally does not implement those pieces. The useful compatible idea adopted here is the normal quiz-assessment endpoint shape and local practice-test export.

## Local Checks

```bash
python3 -m unittest discover -s tests
python3 -m compileall app
```
