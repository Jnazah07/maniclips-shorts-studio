# Whisper Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Shortsmith generate real downloadable vertical shorts in the browser with Whisper WASM transcription, editable captions, and truthful progress.

**Architecture:** Keep the single-file `index.html` shell. Add an in-page ES module that lazy-loads Whisper, drives the existing `<video>` preview, renders canvas exports with MediaRecorder, and replaces the fake status loop with real progress. No backend, no bundler.

**Tech Stack:** Vanilla JS + Canvas + MediaRecorder + `@xenova/transformers` CDN ESM + WASM, decodeAudioData 16kHz mono, existing PWA (`manifest.webmanifest`, `sw.js`, icons).

**Spec:** `docs/superpowers/specs/2026-11-07-shortsmith-whisper-studio-design.md`

## Global Constraints

- Single self-contained `index.html` plus PWA files; Whisper via CDN ESM + WASM; no bundler.
- Lengths are 20s / 30s / 45s / 60s (four options).
- Captions Off means no Whisper download and Generate works right after upload with clean cuts.
- Language picker is spoken language, `task: transcribe` only, native script; UR-R/HI-R map to UR/HI with Roman label only, no transliteration and no English translate.
- Segments only in v1 (no karaoke word timing); editable textarea one segment per line; 3 caption presets (Teal Pill, Bold Yellow, Minimal White) and 3 fonts (Space Grotesk, Inter, System Bold).
- Service worker precaches shell only, never Whisper weights; STORE_KEY `shortsmith.studio.v1` retained.
- Touch targets 44px+, keyboard reachable, `aria-live` progress; design-taste Operate 4/3/6.
- Shorts capped at 12 per Generate; Tiny default, Base optional with size warning; reliable for short talks ~5 min, longer warns with cancel.

## Review Focus

- 30–60 min video → OOM / hang: expect size warning, cancel, and no freeze; pin with max-size + interval cap test in Task 4.
- Silent / no-speech video → Whisper returns empty: expect "No speech found, paste transcript" not a crash; test in Task 2.
- Safari MediaRecorder without WebM/MP4 + audio track: expect graceful video-only export + note; test in Task 4.
- Whisper CDN offline / CSP block: expect retry + paste-transcript fallback, Generate unblocked; test in Task 2.
- UR/HI RTL + bidi in canvas captions: expect native script rendering without overflow; check via visual screenshot in Task 3.

---

## File Structure

- Modify: `shortsmith/index.html` (only product file; upload, transcript, caption styles, Generate, status logic, module loader).
- Modify: `shortsmith/README.md` (usage, model sizes, limits, 20s option).
- Modify: `shortsmith/sw.js` (cache version bump comment only).
- No other files created; `manifest.webmanifest` and `server.js` (`0.0.0.0:8080`) unchanged except README port note already correct.

## Task 1: Real upload + preview + length 20s

**Files:**
- Modify: `shortsmith/index.html` (upload drop zone, `<video>` in phone, length segmented to 4 cols, scrub/play wiring, real status idle text)
- Test: inline check via `node -e` string asserts + manual fetch

**Interfaces:**
- Consumes: existing `state`, `renderPlayback`, `showView`, STORE_KEY.
- Produces: `state.videoUrl`, `state.duration`, `state.segments = []`, `window.__shortsmith = { state, setVideo(url, meta), getLength() }` for tests.

- [ ] **Step 1: Write the failing check**

```js
const fs = require('fs');
const s = fs.readFileSync('shortsmith/index.html', 'utf8');
if (!/type="file"[^>]*accept="video\/\*/.test(s)) throw new Error('no video input');
if (!/data-value="20s"/.test(s)) throw new Error('missing 20s length');
if (!/<video[^>]*playsinline/.test(s)) throw new Error('no preview video');
console.log('upload check ok');
```

- [ ] **Step 2: Run to verify it fails**

Run: `node -e "const fs=require('fs');const s=fs.readFileSync('shortsmith/index.html','utf8');if(!/data-value=\"20s\"/.test(s))throw new Error('missing 20s length');console.log('ok')"`
Expected: FAIL with "missing 20s length"

- [ ] **Step 3: Implement upload + 20s + real preview wiring in `index.html`**

Add 20s seg (`data-cols="4"` grid), hidden video input + drop zone in Home empty state and Studio top, load object URL into preview `<video>` (keep picsum as placeholder until video, then hide img), wire play/scrub to `video.currentTime/duration`, set status to "Ready to transcribe" after metadata, fit length segmented `grid-template-columns: repeat(4, minmax(0,1fr))`.

- [ ] **Step 4: Run check to verify it passes**

Run: the Step 1 node check again
Expected: PASS ("upload check ok")

- [ ] **Step 5: Verify no regression**

Run: `node "C:/Users/Hina/Documents/Default Project/.opencode/skills/design-taste/scripts/preflight.mjs" "index.html" | Out-String` and `node -e "const fs=require('fs');const h=fs.readFileSync('index.html','utf8');console.log(h.length)"`
Expected: 0 hard violations; length > 55000

- [ ] **Step 6: Commit**

```bash
git add shortsmith/index.html
git commit -m "Shortsmith: real upload, preview, and 20s length"
```

## Task 2: Whisper transcribe + editable segments + status truthful + captions-off path

**Files:**
- Modify: `shortsmith/index.html` (Transcribe button, transcript panel + textarea, Whisper dynamic import, progress callback, cancel, paste fallback)
- Test: `node --check` on extracted module + string asserts for transcribe strings

**Interfaces:**
- Consumes: Task 1 `state.videoUrl`, `state.duration`, `__shortsmith`.
- Produces: `state.segments = [{start, end, text}]`, `state.transcribed = true/false`, `transcribeVideo()` returns `Promise<segments>`.

- [ ] **Step 1: Write the failing check**

```js
const s = require('fs').readFileSync('shortsmith/index.html','utf8');
if (!/Transcribe/.test(s)) throw new Error('no Transcribe');
if (!/Loading Whisper|Transcribing/.test(s)) throw new Error('no progress');
if (!/<textarea/.test(s)) throw new Error('no editable transcript');
if (!/captions.*Off|aria-checked.*false/.test(s)) throw new Error('off path missing');
console.log('transcribe check ok');
```

- [ ] **Step 2: Run to verify it fails**

Run: `node -e "const s=require('fs').readFileSync('shortsmith/index.html','utf8');if(!/Transcribe/.test(s))throw new Error('no Transcribe')"`
Expected: FAIL

- [ ] **Step 3: Implement Whisper + editable + off path in `index.html`**

Add `<script type="module" id="whisper">` lazy import `https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2/+esm`, Tiny default with Base toggle + MB warning, `decodeAudioData` → 16kHz mono → `pipeline('automatic-speech-recognition','Xenova/whisper-tiny', { progress_callback })` with spoken `language` map EN/UR/HI (UR-R→UR, HI-R→HI), `task: transcribe`, `return_timestamps: true` (segments). Render segment list (seek on click), editable textarea one-per-line syncing to `state.segments`. Status bar: "Loading Whisper … %", "Transcribing … %", cancel flag. Empty result → toast "No speech found, paste transcript". If captions Off: skip module entirely, `transcribed = true`, Generate enabled after upload.

- [ ] **Step 4: Run checks to verify it passes**

Run: Step 1 check + `node --check server.js` + `node --check sw.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shortsmith/index.html
git commit -m "Shortsmith: Whisper WASM transcribe with editable captions"
```

## Task 3: Caption styles + fonts + persistence + preview burn-in

**Files:**
- Modify: `shortsmith/index.html` (style/font pickers, size slider, canvas caption draw helpers, localStorage fields)
- Test: string asserts for style ids + manual screenshot

**Interfaces:**
- Consumes: Task 2 `state.segments`, `state.capStyle`, `state.capFont`, `state.capSize`.
- Produces: `drawCaption(ctx, text, yPx, w, h)`, `state.capStyle in ['teal','yellow','minimal']`, `state.capFont in ['space','inter','system']`, persisted `shortsmith.studio.v1` extended fields.

- [ ] **Step 1: Write the failing check**

```js
const s=require('fs').readFileSync('shortsmith/index.html','utf8');
for (const id of ['Teal Pill','Bold Yellow','Minimal White']) if(!s.includes(id)) throw new Error('missing '+id);
if(!/capStyle/.test(s)||!/capFont/.test(s)) throw new Error('missing style state');
console.log('style check ok');
```

- [ ] **Step 2: Run to verify it fails**

Run: `node -e "const s=require('fs').readFileSync('shortsmith/index.html','utf8');if(!s.includes('Bold Yellow'))throw new Error('missing style')"`
Expected: FAIL

- [ ] **Step 3: Implement styles + fonts in `index.html`**

Add segmented style (3) + font (3) + size range inputs below language chips, 44px targets, persist `capStyle/capFont/capSize` in `saveState/restoreState`. Preview caption band applies chosen style (bg/color/weight). `drawCaption` draws wrapped text with chosen font string (`700 Xpx "Space Grotesk"` etc.), honors RTL via `ctx.direction='rtl'` for UR/HI.

- [ ] **Step 4: Run check to verify it passes**

Run: Step 1 check again + preflight
Expected: PASS, 0 hard violations

- [ ] **Step 5: Commit**

```bash
git add shortsmith/index.html
git commit -m "Shortsmith: caption styles, fonts, and editable burn-in"
```

## Task 4: Generate real exports + Shorts list + truthful status + PWA/docs

**Files:**
- Modify: `shortsmith/index.html` (Generate logic, canvas recorder, Shorts section, real progress interval removed)
- Modify: `shortsmith/sw.js` (cache bump), `shortsmith/README.md` (usage/limits)
- Test: string asserts for MediaRecorder + Shorts anchors, live fetch

**Interfaces:**
- Consumes: Tasks 1–3 (video, segments, style/font, length 20/30/45/60, bg/fit).
- Produces: `state.shorts = [{url, name, mime}]`, `generateShorts()` sequential realtime record, `<video controls>` + `<a download>` list.

- [ ] **Step 1: Write the failing check**

```js
const s=require('fs').readFileSync('shortsmith/index.html','utf8');
if(!/MediaRecorder/.test(s)) throw new Error('no recorder');
if(!/captureStream/.test(s)) throw new Error('no captureStream');
if(!/Making short|short.*download/i.test(s)) throw new Error('no shorts list');
if(/Listening to speech.*23% \(shorts appear/.test(s)) throw new Error('fake loop still present');
console.log('generate check ok');
```

- [ ] **Step 2: Run to verify it fails**

Run: `node -e "const s=require('fs').readFileSync('shortsmith/index.html','utf8');if(!/MediaRecorder/.test(s))throw new Error('no recorder')"`
Expected: FAIL

- [ ] **Step 3: Implement Generate in `index.html`**

Replace fake `setInterval` 23% loop with real state: idle "Ready", transcribing %, "Making short i/N … %". `generateShorts()`: N=`min(12, floor(duration/length))`, each clip seek → play hidden video → canvas resize by ratio → draw bg (blur/solid/image) + cover video + caption via Task 3 `drawCaption` → `canvas.captureStream(30)` + `video.captureStream()` audio (if available) → MediaRecorder MIME vp9→vp8→mp4 → `onstop` → blob URL → append `<video controls>` + download link with `shortsmith-short-01.webm`. Sequential, cancelable, revoke on new upload. Captions Off skips transcription and burn-in. Bump `sw.js` cache to `shortsmith-v1.2.0` with weights-not-precached comment. README: add upload/transcribe/generate, Tiny 75MB/Base 500MB, realtime note, lengths 20/30/45/60.

- [ ] **Step 4: Run checks to verify it passes**

Run: Step 1 check + `node --check server.js` + preflight + `Get-Content manifest.webmanifest -Raw | ConvertFrom-Json` name check
Expected: PASS, 0 hard violations, manifest name `Shortsmith - Shorts Studio`

- [ ] **Step 5: Verify live on local**

Run: `node server.js` background on `0.0.0.0:8080`, fetch `http://127.0.0.1:8080/` and `http://192.168.0.132:8080/` for 200 + title `Shortsmith`
Expected: Both 200

- [ ] **Step 6: Commit**

```bash
git add shortsmith/index.html shortsmith/sw.js shortsmith/README.md
git commit -m "Shortsmith: real Generate with downloadable shorts"
```
