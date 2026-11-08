# Shortsmith - Shorts Studio (web edition)

Rebranded web recreation of the desktop Shorts Studio screen, built from
runtime observation of the reference desktop app (Tauri v2 / WebView2).

Single self-contained page: `index.html` with inline CSS and JS. No build
step, no dependencies except Google Fonts (Space Grotesk + Inter) loaded
from CDN, with system fallbacks if offline.

## Run locally (fast backend, recommended)

```powershell
python server.py
```

Requires Python 3.10-3.12, `yt-dlp`, `ffmpeg`, `faster-whisper`:

```powershell
pip install faster-whisper
yt-dlp --version
ffmpeg -version
```

Then open http://0.0.0.0:8080 (PC) or http://192.168.0.132:8080 on a phone on the same Wi-Fi (replace IP with your PC's).

Fallback (browser-only, slower realtime export):

```powershell
node server.js
```

Opening `index.html` directly from disk also works, but a server is
recommended so `localStorage` settings persistence and service-worker
registration are consistent.

## Installable (PWA)

Shortsmith is installable on desktop and mobile:

- Chrome / Edge: click **Install app** in the sidebar footer, or use the
  browser install icon
- Android: **Install app** button or Add to Home screen
- iPhone / iPad (Safari): Share > Add to Home Screen (the Install button
  shows this hint on iOS)

Files that make it installable:

- `manifest.webmanifest` - name, icons, theme colors, display mode
- `sw.js` - offline app shell cache (same origin only; fonts and preview
  image still load from the network)
- `icon-192.png` / `icon-512.png` / `icon-maskable-512.png` - app icons
- `icon.svg` - source logo

Install prompts require HTTPS (or `localhost` / `127.0.0.1`) and the
registration served over HTTP. Use the server above for `127.0.0.1`.


## Features

- Shorts Studio shell: sidebar, top bar, status bar with real progress
- Upload long video (picker or drop), preview in phone, play + scrub real video
- Whisper WASM transcription (Tiny ~75 MB, Base ~500 MB) with progress + cancel; segments clickable to seek, editable textarea fallback when Whisper fails
- Caption language = spoken language: EN / UR / HI / UR-R / HI-R (native script, UR-R/HI-R same as UR/HI)
- Caption style (Teal Pill / Bold Yellow / Minimal White), font (Space Grotesk / Inter / System Bold), size slider, draggable position
- Short length: 20s / 30s / 45s / 60s (up to 12 clips, realtime export)
- Generate real vertical shorts via Canvas + MediaRecorder (WebM, MP4 where supported) with background blur / solid / image and fit blur-fill / full-screen, downloadable list
- Captions Off: Generate works immediately, no Whisper download, clean cuts
- Settings persist in `localStorage`
- Installable PWA with offline shell (Whisper weights network on first run)
- Responsive: desktop 2-column, tablet icon rail + stacked, phone bottom tab bar, 44px touch targets, reduced-motion and print support

Limits: Fast backend needs Python + ffmpeg + faster-whisper on your PC. Browser fallback works anywhere (GitHub Pages) but export is realtime and Whisper is WASM. Short talks ~5 min transcribe fastest; up to 70 min is allowed with chunking.

## Rebrand

Name **Shortsmith**, deep teal `#0a1f1e` with accent `#2dd4bf`,
hexagon logo, Space Grotesk display / Inter body, circular chips,
top-accent option cards, pill segmented controls, teal phone bezel.

