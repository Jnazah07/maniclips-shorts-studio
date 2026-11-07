# Shortsmith - Shorts Studio (web edition)

Rebranded web recreation of the desktop Shorts Studio screen, built from
runtime observation of the reference desktop app (Tauri v2 / WebView2).

Single self-contained page: `index.html` with inline CSS and JS. No build
step, no dependencies except Google Fonts (Space Grotesk + Inter) loaded
from CDN, with system fallbacks if offline.

## Run locally

```powershell
node server.js
```

Then open http://127.0.0.1:4173

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

- Shorts Studio shell: sidebar, top bar, background render status banner
- Phone preview: ratio 9:16 / 1:1 / 16:9, blur / solid / imported-image
  background, video-fit cards, draggable caption band (pointer + arrows),
  play/pause and scrubber
- Settings: short length, auto speech captions toggle, caption language
  EN / UR / HI / UR-R / HI-R
- Sidebar collapse, Home / Projects empty states
- Settings persist in `localStorage` across visits
- Installable PWA with offline shell
- Responsive: desktop 2-column, tablet icon rail + stacked, phone bottom
  tab bar, touch targets, reduced-motion and print support

## Rebrand

Name **Shortsmith**, deep teal `#0a1f1e` with accent `#2dd4bf`,
hexagon logo, Space Grotesk display / Inter body, circular chips,
top-accent option cards, pill segmented controls, teal phone bezel.

