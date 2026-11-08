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

def yt_id(u: str):
    import re
    for pat in [r"youtu\.be/([^\?&]+)", r"[?&]v=([^\?&]+)", r"embed/([^\?&]+)", r"shorts/([^\?&]+)"]:
        m = re.search(pat, u)
        if m:
            return m.group(1)
    return None

def run(job, cmd):
    job["log"] = " ".join(cmd)
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "cmd failed")[:800])
    return p

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
        if u.path == "/api/health":
            self._json(200, {"ok": True, "backend": "python", "faster_whisper": HAS_FW, "ffmpeg": True})
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
        self.end_headers()
        self.wfile.write(p.read_bytes())

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(length) if length else b""
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
            job_id = uuid.uuid4().hex[:8]
            job = {"id": job_id, "status": "running", "progress": 5, "clips": []}
            with jobs_lock:
                jobs[job_id] = job
            def gen():
                try:
                    src = UPLOADS / Path(fid).name
                    if not src.exists():
                        job.update(status="error", error="file not found"); return
                    # probe duration
                    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(src)], capture_output=True, text=True)
                    dur = float((probe.stdout or "0").strip() or 0)
                    n = min(12, int(dur // length)) if length else 1
                    w, h = (720, 1280) if ratio == "9:16" else (720, 720) if ratio == "1:1" else (1280, 720)
                    clips = []
                    for i in range(n):
                        if job.get("cancel"):
                            break
                        start = i * length
                        outp = CLIPS / f"shortsmith-short-{i+1:02d}.mp4"
                        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
                        run(job, ["ffmpeg", "-y", "-ss", str(start), "-t", str(length), "-i", str(src), "-vf", vf, "-c:a", "aac", "-b:a", "128k", str(outp)])
                        clips.append(f"/data/clips/{outp.name}")
                        job["progress"] = 5 + int((i + 1) / max(1, n) * 90)
                    job.update(status="done", progress=100, clips=clips)
                except Exception as e:
                    job.update(status="error", error=str(e)[:600])
            threading.Thread(target=gen, daemon=True).start()
            self._json(202, {"job_id": job_id, "clips": []})
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

ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
