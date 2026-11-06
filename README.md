# Mani Clips - Shorts Studio (web edition)

A web recreation of the Mani Clips desktop Shorts Studio screen, built from
runtime observation of `maniclips-desktop.exe` (Tauri v2 / WebView2).

Single self-contained page: `index.html` with inline CSS and JS. No build
step, no dependencies except Google Fonts (Inter) loaded from CDN, with a
system-ui fallback if offline.

## Run locally

```powershell
node server.js
```

Then open http://127.0.0.1:4173

Opening `index.html` directly from disk also works, but a server is
recommended so `localStorage` settings persistence is consistent.

## Deploy as a website

The `index.html` is the site. Deploy the folder as-is.

- **Netlify**: drag the `maniclips` folder onto https://app.netlify.com/drop
- **GitHub Pages**: push `index.html` to a repo, Settings > Pages > deploy
  from branch, root. The file has Open Graph + favicon meta already.
- **Vercel**: `npx vercel` in the folder, framework preset "Other".
- **Any static host**: upload `index.html` as the index file.

`server.js` is only for local preview and is not needed in production.
You can exclude it when publishing.

## Features

- Shorts Studio shell: sidebar, top bar, background render status banner
- Phone preview: ratio 9:16 / 1:1 / 16:9, blur / solid / imported-image
  background, video-fit cards, draggable caption band (pointer + arrows),
  play/pause and scrubber
- Settings: short length, auto speech captions toggle, caption language
  EN / UR / HI / UR-R / HI-R
- Sidebar collapse, Home / Projects empty states
- Settings persist in `localStorage` across visits
- Responsive: desktop 2-column, tablet icon rail + stacked, phone bottom
  tab bar, touch targets, reduced-motion and print support
