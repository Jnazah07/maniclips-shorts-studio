# Shortsmith - Shorts Studio

Paste a YouTube link, get ranked vertical shorts. Shortsmith started as a study
of a desktop shorts app and grew its own pipeline: a transcript-driven cut
planner, burned hook headlines, reusable style recipes, and an MCP server so an
agent can run the whole thing.

Single self-contained page: `index.html` with inline CSS and JS. No build
step, no dependencies except Google Fonts (Space Grotesk + Inter) loaded
from CDN, with system fallbacks if offline.

## Run locally (fast backend, recommended)

```powershell
python server.py
```

Requires Python 3.10-3.12, `yt-dlp`, `ffmpeg`, `faster-whisper`:

```powershell
pip install -r requirements.txt
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
- Paste a YouTube link and the PC engine downloads it with `yt-dlp`; upload also works
- **Smart cuts**: ranks clip windows from the transcript by speech density, hook words and clean sentence boundaries instead of slicing every N seconds; every cut shows a score and an editable headline
- **Hook titles**: an uppercase headline burned into the first seconds of each clip
- **Center on speaker**: samples the clip, finds the largest recurring face and crops around it, so a talking head that sits off to one side still fills the vertical frame. One stable crop per clip (no drifting pan), and it quietly stays centred when the face detection is unsure
- **My styles**: save the current length, ratio, captions, font, caption box and background as one named recipe, restore it in one tap, and share recipes with the MCP server
- Whisper transcription: `faster-whisper` on the PC engine (fast) or Whisper WASM in the browser fallback; segments clickable to seek, editable textarea
- Caption language = spoken language: EN / UR / HI / UR-R / HI-R (native script)
- Caption style (Teal Pill / Bold Yellow / Minimal White), font (Space Grotesk / Inter / System), size slider, draggable position; burned with libass so what you preview is what renders
- Short length: 20s / 30s / 45s / 60s, up to 12 clips per run
- Cuts are rendered by ffmpeg on the PC, not recorded in realtime, with background blur / solid and fit blur-fill / full-screen
- Clip cards show the headline, start time and planner score, plus a direct download
- Settings persist in `localStorage`; style recipes persist locally and on the engine
- Installable PWA with offline shell
- Responsive: desktop 2-column, tablet icon rail + stacked, phone bottom tab bar, 44px touch targets, reduced-motion and print support

Limits: the fast path needs Python 3.10-3.12 + `ffmpeg` + `faster-whisper` + `yt-dlp` on your PC. The browser fallback works anywhere (GitHub Pages) but export is realtime and Whisper is WASM. Up to 70 min / 2 GB per source; transcription is the slow part on CPU. Center on speaker needs `opencv-python-headless<5` and adds a few seconds of face sampling per clip.

## MCP server

`mcp_server.py` exposes the same engine to an agent over stdio. Start the engine
first, then let OpenCode launch the MCP server (this is the shape OpenCode's
config uses today - a named entry directly under `mcp`):

```jsonc
{
  "mcp": {
    "shortsmith": {
      "type": "local",
      "command": [
        "C:/Users/Hina/AppData/Local/Programs/Python/Python312/python.exe",
        "C:/Users/Hina/Documents/Default Project/shortsmith/mcp_server.py"
      ],
      "environment": { "SHORTSMITH_URL": "http://127.0.0.1:8080" }
    }
  }
}
```

Tools:

| Tool | Use |
| --- | --- |
| `shortsmith_health` | engine, ffmpeg, faster-whisper, planner, subject detection, version |
| `shortsmith_ingest` | download a YouTube link, returns `file_id` |
| `shortsmith_transcribe` | faster-whisper segments for the file |
| `shortsmith_plan` | ranked cuts with score, title, words, hooks |
| `shortsmith_generate` | cut, crop (`center`), burn captions + hooks, returns clip URLs |
| `shortsmith_make_shorts` | one shot: ingest, transcribe, plan, render |
| `shortsmith_job_status` | progress, log line, or error |
| `shortsmith_clips` | recent renders with URLs and sizes |
| `shortsmith_styles` | list or save style recipes |


## Rebrand

Name **Shortsmith**, deep teal `#0a1f1e` with accent `#2dd4bf`,
hexagon logo, Space Grotesk display / Inter body, circular chips,
top-accent option cards, pill segmented controls, teal phone bezel.

