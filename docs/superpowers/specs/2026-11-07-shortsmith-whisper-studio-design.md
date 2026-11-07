# Shortsmith Browser Studio — Whisper WASM Design

Date: 2026-11-07
Owner: Shortsmith (browser-only, installable PWA)

## Intent and why

Shortsmith today is a static recreation of the ManiClips Shorts Studio screen. Generate only toasts, the status bar loops, and there is no video upload, transcription, or clip output. The user wants the same job the desktop app did — long video in, vertical shorts out — reverse-engineered their way (Shortsmith brand), usable by anyone in a browser and installable on a computer.

Approach B was picked: real speech transcription with Whisper WASM in the browser. That is the closest to ManiClips without a server, at the cost of a large first-run model download.

## Goals

- Drop / pick a long video (file link / picker / drag), preview it in the phone frame, play and scrub it.
- Transcribe speech in-browser with Whisper WASM, show segments with timestamps, let the caption language select EN / UR / HI / UR-R / HI-R (decided: picker = spoken language, captions shown in that same native script; UR-R/HI-R behave as UR/HI with a Roman label only — no transliteration, no English translate).
- Burn captions onto exports at the draggable caption position, with multiple caption styles and fonts, editable before export.
- Honor existing settings: ratio 9:16 / 1:1 / 16:9, background blur / solid / imported image, video fit blur-fill / full-screen, length 20s / 30s / 45s / 60s (four options), captions on/off.
- Generate real vertical shorts as downloadable files via Canvas + MediaRecorder (WebM primary, with MP4 where supported). Shorts appear in a list with play and download.
- Make the status bar truthful: real progress for model load, transcription, and per-clip rendering. No fake 23% loop.
- Keep installable offline shell, manifest, icons, service worker, `v1.1.0` bump to model-aware versioning if needed.
- Works on GitHub Pages (static) and local `server.js` on `0.0.0.0:8080` for phone testing.

## Non-goals

- No backend / Python server / API keys. Browser-only.
- No background persistent server-side jobs. Processing runs while the tab is open.
- No exact ManiClips UI copy. Shortsmith brand, teal tokens, Space Grotesk + Inter, hexagon logo stay.
- No auto smart-crop face tracking / speaker detection in v1. Center crop + blur/solid fill is the default, matching current fit options.
- No cloud account / projects sync. Local `localStorage` persistence stays, plus browser IndexedDB for model + recent media is optional future.

## Anti-goals (failure if)

- Site loads but Generate still fakes it.
- Phone requires a PC server to work.
- First run downloads a model silently with no progress, size, or offline story.
- Captions only appear as overlay text, not burned into downloads.

## Constraints

- Single self-contained `index.html` plus PWA files (`manifest.webmanifest`, `sw.js`, `icon-*.png`, `icon.svg`). No bundler. Whisper via CDN ESM + WASM. Google Fonts via CDN with system fallback (existing warning).
- Service worker cache must include the app shell but not the Whisper model weights (too large, versioned separately in Cache API via model library or IndexedDB). Fonts and preview image stay network.
- Must work on desktop Chrome/Edge + Android Chrome; iOS Safari is progressive (MediaRecorder limited, Whisper slow — show clear limits, still must not break layout).
- Touch targets already 44px pass (design-taste Operate, variance 4 / motion 3 / density 6). New upload, transcript, and shorts-list controls must also be 44px, keyboard reachable, `aria-live` for progress.
- No fake scores, no placeholder transcriptions presented as real. If Whisper fails, show error + retry + “use typed transcript” fallback.
- Existing STORE_KEY `shortsmith.studio.v1`, retention of collapsed, ratio, bg, length, fit, captions, lang, caption Y.

## Approaches considered

**A. Cut + record, captions typed in — rejected for this round.** Fast and light, works offline immediately, but user explicitly chose automatic transcription. Remains the fallback if Whisper is unavailable: paste a transcript and still export.

**B. Cut + record + Whisper WASM — chosen.** `@xenova/transformers` (or current equivalent) with `whisper-tiny` / `whisper-base` pipeline, `pipeline("automatic-speech-recognition", model)`, WASM backend, WebGPU where available. Transcribes the uploaded file’s audio (extracted via `<video>` + AudioContext / `decodeAudioData` downsampled to 16kHz mono), returns timestamped segments. Words are aligned to caption band at user-drag Y. Each short is an interval [start, start + length] chosen from segments (evenly spaced candidate starts, no smart hook scoring in v1 beyond even spacing + avoid cutting mid-word where timestamps allow). Rendering draws video frame → cover/blur background → caption text → `canvas.captureStream(30)` + optional audio track (video element `captureStream`) → MediaRecorder. Lists each clip as object URL + download `<a>`.

Trade-offs: first run ~75 MB (tiny) to ~500 MB (base) download with progress; transcription minutes-long on CPU, faster on WebGPU; 30/45/60s clips export in near real-time (not faster, since recording is realtime). Needs memory guard + cancel.

**C. Mic captions only (SpeechRecognition) — rejected.** Chrome-only, live mic only, no file transcription, no offline, no UR/HI-R reliability.

Why B is the only fit: it is the only browser-only way to deliver “like ManiClips” (file → auto captions → shorts) on static hosting for anyone + installable.

## How it works (decided parts)

**Upload:** Home empty state gets a real drop zone + file input (also in Studio top). Sets `state.videoUrl`, loads `<video>` (hidden source, proxied via `video` element feeding canvas), shows duration, size, dimensions in a “Source” chip. Replaces `picsum` preview image with the user’s first frame; `picsum` remains as empty-state placeholder only.

**Preview:** Existing phone screen shows `<video muted playsinline>` instead of `<img>`. Play/pause and scrubber drive the real element (ties to `renderPlayback` currently fake). Caption band drag still sets `--cap-y` (persisted). Ratio change resizes the phone frame and export canvas aspect.

**Transcribe:** “Transcribe” button appears after upload. Flow: status bar “Loading Whisper (X MB)… %” → “Transcribing… %” → segment list in a transcript panel (scrollable, click to seek). Language select = spoken language, `task: transcribe` only (no translate-to-English). UR-R/HI-R map to UR/HI native script, chip labeled Roman, no transliteration engine. Progress comes from Transformers progress callback and pipeline `chunk_length_s` iteration. Cancel via AbortController-equivalent flag. Model choice: Tiny by default (fast, low RAM), with a “Higher accuracy (Base)” toggle that warns ~5x size. Captions segment-level only in v1 (no karaoke word timing). Reliable for short talks ~5 min; longer files warn and may take minutes, with cancel.

**Captions editing + styles:** Transcript panel has an editable textarea (plain text, one segment per line) plus per-segment seek/edit. Caption style picker: 3 presets (Teal Pill, Bold Yellow, Minimal White) and font picker: 3 faces (Space Grotesk, Inter, System Bold) to stay within design-taste 3-family budget; size slider + position drag (existing `--cap-y`). Edits preview live in phone caption band and are what gets burned in.

**Generate:** If captions are Off: Generate is enabled right after upload, no Whisper download/transcription, clean cuts with no burn-in. If captions are On: Generate stays disabled until transcription (or pasted fallback) is ready, then creates N intervals = `floor(duration / length)` capped (e.g., max 12 clips to bound time/storage; show cap). For each clip sequentially: seek video to start, play muted while canvas draws, record length seconds (20/30/45/60 real seconds; realtime by design). Update status bar “Making short 2/5… 43%”. Append to “Shorts” section (new view below preview, desktop two-column stays, stacks on mobile) with `<video controls>` per clip + Download. Burned captions: draw segment text overlapping interval at caption Y in chosen style/font. Background blur: draw scaled blurred copy underneath; solid: tint; image: uploaded image fill + video centered. Teal bezel and hexagon brand unchanged.

**Install:** Install button stays. After install, app must still load Whisper from network on first transcribe (PWA offline note). Service worker update: bump cache name on model change, add `sw.js` comment that Whisper weights are not precached.

**Files touched:** `shortsmith/index.html` (upload UI, transcript panel, shorts list, real Generate, Whisper loader via CDN `<script type="module">` + fallback if CDN fails), `shortsmith/manifest.webmanifest` (no change except description mention of transcription), `shortsmith/sw.js` (cache bump comment), `shortsmith/README.md` (upload/transcribe/generate usage, model sizes, limits), `shortsmith/server.js` (no change; already `0.0.0.0:8080`). No new build step.

## Left to the builder

- Exact Whisper ESM URL/version pin and WASM backend flags; choose `xenova/transformers@2` stable + `whisper-tiny` default to keep first run survivable on phones.
- Audio extraction path: `<video>` → `AudioContext.decodeAudioData(arrayBuffer)` vs `captureStream` + oscillator silence to keep sync simple.
- Clip interval heuristic beyond even spacing (avoid overlapping, clamp to duration, handle <1 clip videos).
- MediaRecorder MIME pick: `video/webm;codecs=vp9`, fallback `vp8`, fallback `video/mp4` (Safari). Include audio track if `captureStream` supports it; else video-only with note.
- Performance guards: max file size warn (e.g., 500 MB), low-memory abort, tab-hidden warning.
