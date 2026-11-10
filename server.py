#!/usr/bin/env python3
"""Shortsmith fast backend: serves index.html + /api (yt-dlp, faster-whisper, ffmpeg)."""
import os, json, subprocess, tempfile, uuid, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
CLIPS = DATA / "clips"
UPLOADS.mkdir(parents=True, exist_ok=True)
CLIPS.mkdir(parents=True, exist_ok=True)
jobs = {}
jobs_lock = threading.Lock()

try:
    from faster_whisper import WhisperModel
    HAS_FW = True
except Exception:
    HAS_FW = False
    WhisperModel = None

try:
    import numpy as np
except Exception:
    np = None

def yt_id(u: str):
    import re
    for pat in [r"youtu\.be/([^\?&]+)", r"[?&]v=([^\?&]+)", r"embed/([^\?&]+)", r"shorts/([^\?&]+)"]:
        m = re.search(pat, u)
        if m:
            return m.group(1)
    return None

def run(job, cmd):
    job["log"] = " ".join(cmd)
    p = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "cmd failed")[:800])
    return p


# ---------- Shortsmith smart planner (my own scoring, not ManiClips' slice-every-N-seconds) ----------

HOOK_WORDS = {
    "how", "why", "what", "when", "never", "always", "secret", "mistake", "stop", "start",
    "best", "worst", "truth", "nobody", "everyone", "actually", "because", "should", "wrong",
    "biggest", "free", "fast", "easy", "hate", "love", "problem", "fix", "money", "time",
    "first", "last", "only", "real", "honest", "told", "learned", "changed", "wish", "regret",
}
TITLE_STOP = {"the", "and", "but", "for", "with", "that", "this", "you", "your", "they", "them"}


def _clean_title(text, max_words=9, max_chars=58):
    words = str(text or "").replace("\n", " ").split()
    picked = []
    for w in words:
        picked.append(w.strip(".,!?;:\"'"))
        if len(" ".join(picked)) >= max_chars or len(picked) >= max_words:
            break
    t = " ".join([w for w in picked if w])
    t = t.strip(" .,!?;:-")
    if not t:
        return "Untitled moment"
    return t[0].upper() + t[1:]


def plan_cuts(segments, length, total, limit=12):
    """Rank candidate windows by speech density, hook words and clean cut boundaries."""
    segs = sorted([s for s in segments if str(s.get("text") or "").strip()], key=lambda s: float(s.get("start", 0)))
    total = max(float(total or 0), max([float(s.get("end", 0)) for s in segs] or [0]))
    if not segs:
        n = max(1, min(limit, int(total // max(1, length)))) if total else 1
        return [{"start": i * length, "end": min(total or (i + 1) * length, (i + 1) * length),
                 "score": 0, "title": f"Clip {i + 1}", "words": 0, "hooks": 0} for i in range(n)]

    cands = []
    for anchor in segs:
        start = max(0.0, float(anchor["start"]) - 0.35)
        if total and start + length > total:
            start = max(0.0, total - length)
        end = start + length
        inside = [x for x in segs if float(x.get("start", 0)) < end and float(x.get("end", 0)) > start]
        if not inside:
            continue
        words = sum(len(str(x.get("text") or "").split()) for x in inside)
        density = words / max(1.0, length)
        hooks = sum(1 for x in inside for w in str(x.get("text") or "").lower().split()
                    if w.strip(".,!?;:") in HOOK_WORDS)
        tail_gap = min(abs(end - float(x.get("end", 0))) for x in inside)
        head_gap = abs(start - float(inside[0].get("start", 0)))
        score = density * 2.2 + min(hooks, 8) * 1.6
        score += 1.0 if tail_gap < 1.6 else 0.4 if tail_gap < 3.5 else 0.0
        score += 0.6 if head_gap < 2.0 else 0.0
        if total:
            score += max(0.0, 1.2 * (1 - start / total))  # earlier material usually carries the promise
        cands.append({
            "start": round(start, 2), "end": round(end, 2), "score": round(score, 2),
            "title": _clean_title(inside[0].get("text")), "words": words, "hooks": hooks,
        })

    picked = []
    for c in sorted(cands, key=lambda c: -c["score"]):
        if all(abs(c["start"] - p["start"]) >= length * 0.85 for p in picked):
            picked.append(c)
        if len(picked) >= limit:
            break
    picked.sort(key=lambda c: c["start"])
    for i, c in enumerate(picked):
        c["index"] = i + 1
    return picked


def _ass_ts(s):
    s = max(0.0, float(s))
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}.{int(round((s - int(s)) * 100)):02d}"


def _ass_wrap(text, width=42, max_lines=3):
    import textwrap
    lines = []
    for para in str(text or "").split("\n"):
        lines.extend(textwrap.wrap(para, width=width) or [""])
    return "\\N".join(lines[:max_lines])


def _font_stack(preferred):
    """libass can only use fonts installed on the machine; fall back to real Windows faces."""
    try:
        fonts = {p.name.lower() for p in Path(os.environ.get("WINDIR", r"C:\Windows")).joinpath("Fonts").glob("*")}
    except Exception:
        fonts = set()
    if preferred == "space" and any("spacegrotesk" in f or "space grotesk" in f for f in fonts):
        return "Space Grotesk"
    if preferred == "inter" and any(f.startswith("inter") for f in fonts):
        return "Inter"
    if preferred == "system":
        return "Segoe UI" if any("segoeui" in f for f in fonts) else "Arial"
    # closest wide faces shipped with Windows
    if any("seguibl" in f or "segoeui" in f for f in fonts):
        return "Segoe UI Semibold"
    return "Arial"


CAP_STYLES = {
    # BorderStyle 3 = opaque box behind the text, which is what the studio preview shows.
    "teal": {"font": "&H00F9FDEA", "outline": "&H00292E0A", "back": "&HAA292E0A", "border": 3, "outline_w": 6, "shadow": 0, "bold": -1},
    "yellow": {"font": "&H0016141A", "outline": "&H003AC9E9", "back": "&HCC3AC9E9", "border": 3, "outline_w": 6, "shadow": 0, "bold": -1},
    "minimal": {"font": "&H00FFFFFF", "outline": "&H00000000", "back": "&H99000000", "border": 1, "outline_w": 2, "shadow": 1, "bold": 0},
    "hook": {"font": "&H00F9FDEA", "outline": "&H00000000", "back": "&H66081212", "border": 3, "outline_w": 0, "shadow": 0, "bold": -1},
}


def build_ass(path, w, h, start, length, segments, opts):
    """One ASS per clip, shifted to clip-local time so captions and hooks actually line up."""
    cap = CAP_STYLES.get(opts.get("capStyle"), CAP_STYLES["teal"])
    font = _font_stack(opts.get("capFont"))
    size = max(16, min(56, int(opts.get("capSize") or 28)))
    cap_y = float(opts.get("capY") or 54)
    margin_v = max(24, int(h * 0.5 - h * (cap_y / 100.0)) if cap_y > 50 else int(h * (100 - cap_y) / 100.0 * 0.5))
    margin_v = max(24, min(int(h * 0.42), margin_v))
    hook_on = bool(opts.get("hook"))
    hook_size = max(22, min(58, int(size * 1.35)))
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic,"
        " Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL,"
        " MarginR, MarginV, Encoding",
        f"Style: Cap,{font},{size},{cap['font']},&H000000FF,{cap['outline']},{cap['back']},{cap['bold']},0,0,0,100,100,0,0,"
        f"{cap['border']},{cap['outline_w']},{cap['shadow']},2,24,24,{margin_v},1",
        f"Style: Hook,{font},{hook_size},&H00FFFFFF,&H000000FF,&H00000000,&H88000000,-1,0,0,0,100,100,0,0,3,0,0,8,24,24,{max(28, int(h * 0.045))},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    from_ = start
    to = start + length
    if opts.get("captions", True) and segments:
        for seg in segments:
            s, e = float(seg.get("start", 0)), float(seg.get("end", 0))
            if e <= from_ or s >= to:
                continue
            s2 = max(0.0, s - from_)
            e2 = min(length, e - from_)
            if e2 - s2 < 0.25:
                continue
            lines.append(f"Dialogue: 0,{_ass_ts(s2)},{_ass_ts(e2)},Cap,,0,0,0,,{_ass_wrap(seg.get('text'))}")
    title = str(opts.get("hookText") or "").strip()
    if hook_on and title:
        lines.append(f"Dialogue: 1,{_ass_ts(0)},{_ass_ts(min(length, 5.0))},Hook,,0,0,0,,{_ass_wrap(title.upper(), width=26, max_lines=2)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _ff_escape(p):
    return str(p).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


_DETECTOR = None


def _detector():
    """(cv2, [cascades]) once, or (None, None). OpenCV 5 dropped the Haar classes, hence the guard."""
    global _DETECTOR
    if _DETECTOR is not None:
        return _DETECTOR
    try:
        import cv2
    except Exception:
        _DETECTOR = (None, None)
        return _DETECTOR
    cascades = []
    for name in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml"):
        try:
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + name)
            if not cascade.empty():
                cascades.append(cascade)
        except Exception:
            pass
    _DETECTOR = (cv2, cascades) if cascades else (None, None)
    return _DETECTOR


def _weighted_median(hits):
    hits = sorted(hits, key=lambda h: h[0])
    total = sum(h[2] for h in hits)
    acc = 0.0
    for hit in hits:
        acc += hit[2]
        if acc >= total / 2.0:
            return hit
    return hits[-1]


def _sample_gray(src, start, length, n, width, dims=None):
    """Pull n evenly spaced grey frames through ffmpeg in one pass. Returns (frames, w, h)."""
    sw, sh = dims or (16, 9)
    dh = max(2, int(round(width * float(sh) / max(1.0, float(sw)))) // 2 * 2)
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, float(start)):.3f}", "-t", f"{float(length):.3f}",
           "-i", str(src), "-vf", f"fps={n / max(0.1, float(length)):.5f},scale={width}:{dh}",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=120)
    except Exception:
        return [], width, dh
    block = width * dh
    raw = proc.stdout or b""
    frames = [raw[i:i + block] for i in range(0, len(raw) - block + 1, block)]
    return frames, width, dh


def subject_center(src, start, length, samples=8, min_share=0.3, dims=None):
    """Largest recurring face in the clip -> one stable crop centre (no per-frame pan jitter).

    Returns x/y as fractions of the frame (0-1), so callers never mix up source and upscaled pixels.
    Falls back to None (dead-centre crop) when the evidence is thin, because a wrong guess frames
    the subject worse than simply staying centred.
    """
    cv2, cascades = _detector()
    if cv2 is None or np is None:
        return None
    n = max(3, int(samples))
    frames, dw, dh = _sample_gray(src, start, length, n, 640, dims)
    if len(frames) < 3:
        return None
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    min_side = max(24, int(dw * 0.04))
    hits = []
    for raw in frames:
        gray = clahe.apply(np.frombuffer(raw, np.uint8).reshape(dh, dw).copy())
        faces = []
        for cascade in cascades:  # first cascade usually wins; the second only runs on a miss
            found = cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=3,
                                             minSize=(min_side, min_side))
            faces = [f for f in found if 0.6 <= (f[2] / float(f[3])) <= 1.5]
            if faces:
                break
        if not faces:
            continue
        fx, fy, ffw, ffh = max(faces, key=lambda f: int(f[2]) * int(f[3]))
        hits.append((float(fx + ffw / 2.0), float(fy + ffh / 2.0), float(ffw * ffh)))
    if not hits:
        return None
    # Keep only hits near the weighted median; a stray detection on a cutaway must not drag the crop.
    seed = _weighted_median(hits)
    keep = [h for h in hits if abs(h[0] - seed[0]) <= dw * 0.18] or [seed]
    share = len(keep) / float(n)
    if share < min_share:
        return None
    pick = _weighted_median(keep)
    # Confidence ramps 0.3 -> 0.7 of frame share, so a shaky read drifts toward centre, not past it.
    confidence = min(1.0, (share - min_share) / 0.4)
    return {"x": 0.5 + (pick[0] / float(dw) - 0.5) * confidence,
            "y": 0.5 + (pick[1] / float(dh) - 0.5) * confidence,
            "hits": len(keep), "seen": len(hits), "confidence": round(confidence, 2)}


def subject_crop_prefix(src, start, length, target_w, target_h, sw, sh, label=""):
    """ffmpeg filter prefix that crops the source around the subject before scaling."""
    if not sw or not sh or not target_w or not target_h:
        return "", None
    track = subject_center(src, start, length, dims=(sw, sh))
    cw = int(round(sh * (target_w / float(target_h))))
    ch = sh
    if cw >= sw:
        cw = sw - (sw % 2)
        ch = int(round(sw * (target_h / float(target_w))))
        ch -= ch % 2
        if ch >= sh:
            return "", track
    cw -= cw % 2
    if cw < sw:
        cx = sw * track["x"] if track else sw / 2.0
        x = int(max(0, min(sw - cw, round(cx - cw / 2.0))))
        return f"crop={cw}:{ch}:{x}:0,", track
    cy = sh * track["y"] if track else sh / 2.0
    y = int(max(0, min(sh - ch, round(cy - ch / 2.0))))
    return f"crop={cw}:{ch}:0:{y},", track

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path.startswith("/api/jobs/"):
            jid = u.path.split("/")[-1]
            with jobs_lock:
                j = jobs.get(jid)
            if not j:
                self._json(404, {"error": "job not found"}); return
            self._json(200, j); return
        if u.path == "/api/presets":
            pf = DATA / "presets.json"
            try:
                presets = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
            except Exception:
                presets = {}
            self._json(200, {"presets": presets if isinstance(presets, dict) else {}})
            return
        if u.path == "/api/clips":
            items = []
            for p in sorted(CLIPS.glob("*.mp4")):
                st = p.stat()
                items.append({"name": p.name, "url": f"/data/clips/{p.name}", "bytes": st.st_size,
                              "modified": int(st.st_mtime)})
            items.sort(key=lambda i: -i["modified"])
            self._json(200, {"clips": items[:60]})
            return
        if u.path == "/api/health":
            _, _cascade = _detector()
            self._json(200, {"ok": True, "backend": "python", "faster_whisper": HAS_FW, "ffmpeg": True,
                             "opencv": _cascade is not None, "planner": True, "presets": True,
                             "version": "1.3.0"})
            return
        if u.path.startswith("/data/clips/") or u.path.startswith("/data/uploads/"):
            p = ROOT / u.path.lstrip("/")
            if not p.exists():
                self.send_response(404); self.end_headers(); return
            self.send_response(200)
            self.send_header("content-type", "video/mp4" if p.suffix == ".mp4" else "video/webm")
            self.send_header("content-length", str(p.stat().st_size))
            self.end_headers()
            self.wfile.write(p.read_bytes())
            return
        # static
        p = ROOT / ("index.html" if u.path == "/" else u.path.lstrip("/"))
        if not p.exists() or p.is_dir():
            self.send_response(404); self.end_headers(); return
        types = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".webmanifest": "application/manifest+json", ".png": "image/png", ".svg": "image/svg+xml", ".json": "application/json"}
        self.send_response(200)
        self.send_header("content-type", types.get(p.suffix, "application/octet-stream"))
        self.send_header("content-length", str(p.stat().st_size))
        if p.suffix in (".html", ".js", ".webmanifest"):
            self.send_header("cache-control", "no-cache")
        self.end_headers()
        self.wfile.write(p.read_bytes())

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(length) if length else b""
        if u.path == "/api/ingest":
            try:
                data = json.loads(body or b"{}")
            except Exception:
                self._json(400, {"error": "bad json"}); return
            url = str(data.get("url") or "")
            vid = yt_id(url)
            if not vid:
                self._json(400, {"error": "Not a YouTube link"}); return
            dst = UPLOADS / f"shortsmith-youtube-{vid}.mp4"
            try:
                subprocess.run(["yt-dlp", "-f", "best[ext=mp4][filesize<2G]/best[ext=mp4]/best",
                                "--no-playlist", "-o", str(dst), "--merge-output-format", "mp4", url],
                               capture_output=True, text=True, timeout=900)
            except Exception as e:
                self._json(500, {"error": str(e)[:400]}); return
            if not dst.exists():
                self._json(500, {"error": "Download failed. Is yt-dlp installed?"}); return
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "default=noprint_wrappers=1:nokey=1", str(dst)],
                                   capture_output=True, text=True)
            try:
                duration = round(float((probe.stdout or "0").strip() or 0), 2)
            except Exception:
                duration = 0
            self._json(200, {"file_id": dst.name, "video_id": vid, "bytes": dst.stat().st_size,
                             "duration": duration, "url": f"/data/uploads/{dst.name}"})
            return
        if u.path == "/api/youtube":
            try:
                data = json.loads(body or b"{}")
            except Exception:
                self._json(400, {"error": "bad json"}); return
            url = str(data.get("url") or "")
            vid = yt_id(url)
            if not vid:
                self._json(400, {"error": "Not a YouTube link"}); return
            dst = UPLOADS / f"shortsmith-youtube-{vid}.mp4"
            try:
                subprocess.run(["yt-dlp", "-f", "best[ext=mp4][filesize<2G]/best[ext=mp4]/best", "--no-playlist", "-o", str(dst), "--merge-output-format", "mp4", url], capture_output=True, text=True, timeout=600)
                if not dst.exists():
                    self._json(500, {"error": "Download failed. Is yt-dlp installed?"}); return
                stats = dst.stat()
                self.send_response(200)
                self.send_header("content-type", "video/mp4")
                self.send_header("content-length", str(stats.st_size))
                self.send_header("content-disposition", f'attachment; filename="shortsmith-youtube-{vid}.mp4"')
                self.end_headers()
                self.wfile.write(dst.read_bytes())
            except Exception as e:
                self._json(500, {"error": str(e)[:500]})
            return
        if u.path == "/api/upload":
            # expect raw video bytes, filename in header X-Filename
            fname = self.headers.get("X-Filename", "upload.mp4")
            safe = Path(fname).name
            dest = UPLOADS / safe
            dest.write_bytes(body)
            self._json(200, {"file_id": safe, "size": len(body)})
            return
        if u.path == "/api/transcribe":
            try:
                data = json.loads(body or b"{}")
            except Exception:
                self._json(400, {"error": "bad json"}); return
            fid = str(data.get("file_id") or "")
            lang = str(data.get("language") or "en")
            model_size = str(data.get("model") or "tiny")
            job_id = uuid.uuid4().hex[:8]
            job = {"id": job_id, "status": "running", "progress": 5}
            with jobs_lock:
                jobs[job_id] = job
            def tr():
                try:
                    if not HAS_FW:
                        job.update(status="error", error="faster-whisper not installed. Run: pip install faster-whisper")
                        return
                    src = UPLOADS / Path(fid).name
                    if not src.exists():
                        job.update(status="error", error="file not found"); return
                    model = WhisperModel(model_size, device="cpu", compute_type="int8")
                    segs, info = model.transcribe(str(src), language=lang if lang in ("en", "ur", "hi") else "en", beam_size=1)
                    out = []
                    for s in segs:
                        if s.text.strip():
                            out.append({"start": float(s.start), "end": float(s.end), "text": s.text.strip()})
                        if job.get("cancel"):
                            break
                    job.update(status="done", progress=100, segments=out, lang=info.language)
                except Exception as e:
                    job.update(status="error", error=str(e)[:600])
            threading.Thread(target=tr, daemon=True).start()
            self._json(202, {"job_id": job_id})
            return
        if u.path == "/api/generate":
            try:
                data = json.loads(body or b"{}")
            except Exception:
                self._json(400, {"error": "bad json"}); return
            fid = str(data.get("file_id") or "")
            length = int(data.get("length") or 30)
            ratio = str(data.get("ratio") or "9:16")
            bg = str(data.get("bg") or "blur")
            fit = str(data.get("fit") or "blur")
            segments = data.get("segments") or []
            capStyle = str(data.get("capStyle") or "teal")
            capFont = str(data.get("capFont") or "space")
            capSize = int(data.get("capSize") or 28)
            capY = float(data.get("capY") or 54)
            wantCaps = bool(data.get("captions") if "captions" in data else bool(segments))
            hook = bool(data.get("hook", True))
            center = bool(data.get("center", True))
            job_id = uuid.uuid4().hex[:8]
            job = {"id": job_id, "status": "running", "progress": 5, "clips": []}
            with jobs_lock:
                jobs[job_id] = job
            def gen():
                try:
                    src = UPLOADS / Path(fid).name
                    if not src.exists():
                        job.update(status="error", error="file not found"); return
                    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(src)], capture_output=True, text=True)
                    dur = float((probe.stdout or "0").strip() or 0)
                    w, h = (720, 1280) if ratio == "9:16" else (720, 720) if ratio == "1:1" else (1280, 720)
                    sw = sh = 0
                    try:
                        dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                               "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
                                               str(src)], capture_output=True, text=True)
                        parts = (dims.stdout or "").strip().split("x")
                        sw, sh = int(parts[0]), int(parts[1])
                    except Exception:
                        sw = sh = 0
                    plan = data.get("plan") or []
                    if plan:
                        cuts = []
                        for p in plan:
                            s0 = float(p.get("start") or 0)
                            l0 = p.get("len") or (float(p.get("end") or 0) - s0) or length
                            cuts.append({"start": s0, "len": float(l0), "title": str(p.get("title") or "")})
                    else:
                        n = min(12, int(dur // length)) if (length and dur) else 1
                        cuts = [{"start": i * length, "len": float(length), "title": ""} for i in range(n)]
                    clips = []
                    total_cuts = max(1, len(cuts))
                    for i, cut in enumerate(cuts):
                        if job.get("cancel"):
                            break
                        start = max(0.0, cut["start"])
                        seg_len = max(1.0, min(cut["len"], (dur - start) if dur else cut["len"]))
                        outp = CLIPS / f"shortsmith-{job_id}-{i+1:02d}.mp4"
                        pre, track = ("", None)
                        if center:
                            pre, track = subject_crop_prefix(src, start, seg_len, w, h, sw, sh)
                        ass_path = DATA / f"caps-{job_id}-{i+1:02d}.ass"
                        build_ass(ass_path, w, h, start, seg_len, segments, {
                            "capStyle": capStyle, "capFont": capFont, "capSize": capSize, "capY": capY,
                            "captions": wantCaps, "hook": hook, "hookText": cut.get("title") or "",
                        })
                        if bg == "blur" and fit == "blur":
                            fc = "[0:v]" + pre + f"split=2[b][m];[b]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=18[bg];[m]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
                        elif bg == "solid":
                            fc = "[0:v]" + pre + f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=#1a2e2a,format=yuv420p"
                        elif fit == "full":
                            fc = "[0:v]" + pre + f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p"
                        else:
                            fc = "[0:v]" + pre + f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
                        fc += f",subtitles='{_ff_escape(ass_path)}'"
                        run(job, ["ffmpeg", "-y", "-ss", str(start), "-t", str(seg_len), "-i", str(src),
                                  "-filter_complex", fc, "-c:a", "aac", "-b:a", "128k", str(outp)])
                        try:
                            ass_path.unlink()
                        except Exception:
                            pass
                        clips.append({"url": f"/data/clips/{outp.name}", "name": outp.name,
                                      "start": round(start, 2), "len": round(seg_len, 2),
                                      "title": cut.get("title") or "",
                                      "subject": ({"x_pct": round(track["x"] * 100), "hits": track["hits"],
                                                   "seen": track["seen"]} if track else None)})
                        job["progress"] = 5 + int((i + 1) / total_cuts * 90)
                    job.update(status="done", progress=100,
                               clips=[c["url"] for c in clips], items=clips)
                except Exception as e:
                    job.update(status="error", error=str(e)[:600])
            threading.Thread(target=gen, daemon=True).start()
            self._json(202, {"job_id": job_id, "clips": []})
            return
        if u.path == "/api/plan":
            try:
                data = json.loads(body or b"{}")
            except Exception:
                self._json(400, {"error": "bad json"}); return
            fid = str(data.get("file_id") or "")
            length = int(data.get("length") or 30)
            segments = data.get("segments") or []
            src = UPLOADS / Path(fid).name
            total = float(data.get("duration") or 0)
            if not total and src.exists():
                probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                        "-of", "default=noprint_wrappers=1:nokey=1", str(src)],
                                       capture_output=True, text=True)
                try:
                    total = float((probe.stdout or "0").strip() or 0)
                except Exception:
                    total = 0
            cuts = plan_cuts(segments, length, total, int(data.get("limit") or 12))
            self._json(200, {"cuts": cuts, "duration": round(total, 2), "length": length})
            return
        if u.path == "/api/presets":
            try:
                data = json.loads(body or b"{}")
            except Exception:
                self._json(400, {"error": "bad json"}); return
            pf = DATA / "presets.json"
            try:
                presets = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
            except Exception:
                presets = {}
            if not isinstance(presets, dict):
                presets = {}
            name = str(data.get("name") or "").strip()[:40]
            style = data.get("style")
            if not name or not isinstance(style, dict):
                self._json(400, {"error": "name and style required"}); return
            presets[name] = style
            pf.write_text(json.dumps(presets, indent=2), encoding="utf-8")
            self._json(200, {"ok": True, "presets": presets})
            return
        self._json(404, {"error": "unknown"})

    def do_DELETE(self):
        u = urlparse(self.path)
        if u.path.startswith("/api/jobs/"):
            jid = u.path.split("/")[-1]
            with jobs_lock:
                if jid in jobs:
                    jobs[jid]["cancel"] = True
            self._json(200, {"ok": True})
            return
        self.send_response(404); self.end_headers()

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
