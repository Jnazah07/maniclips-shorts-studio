#!/usr/bin/env python3
"""Shortsmith MCP server — link in, ranked clips out, driven by an agent.

Thin stdio MCP front end over the Shortsmith HTTP engine (server.py), so the
browser studio and an agent share one job queue, one transcript cache and one
clip folder.

    python server.py        # engine  (http://127.0.0.1:8080)
    python mcp_server.py    # this MCP server (stdio)

Env: SHORTSMITH_URL (default http://127.0.0.1:8080)
"""
import asyncio
import json
import os
import time
import urllib.error
import urllib.request

from mcp.server.mcpserver import MCPServer

BASE = os.environ.get("SHORTSMITH_URL", "http://127.0.0.1:8080").rstrip("/")

server = MCPServer(
    name="shortsmith",
    title="Shortsmith",
    version="1.2.0",
    instructions=(
        "Shortsmith turns a YouTube link or local video into ranked vertical shorts.\n"
        "Typical run: shortsmith_make_shorts(url, length) for one shot, or the manual chain\n"
        "shortsmith_ingest -> shortsmith_transcribe -> shortsmith_plan -> shortsmith_generate\n"
        "when you want to choose or rename the moments yourself.\n"
        "Work in seconds. Clip lengths are 20, 30, 45 or 60. Every tool needs the local engine\n"
        "running (python server.py); shortsmith_health says whether it is up."
    ),
)


class EngineError(RuntimeError):
    pass


def _request(path, payload=None, method=None, timeout=90):
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    if data:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:400]
        raise EngineError(f"HTTP {exc.code} from {path}: {body}") from exc
    except urllib.error.URLError as exc:
        raise EngineError(
            f"Cannot reach the Shortsmith engine at {BASE} ({exc.reason}). "
            "Start it with `python server.py` in the Shortsmith folder."
        ) from exc


async def post(path, payload, timeout=90):
    return await asyncio.to_thread(_request, path, payload, "POST", timeout)


async def get(path, timeout=60):
    return await asyncio.to_thread(_request, path, None, "GET", timeout)


async def wait_job(job_id, timeout=3600, poll=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = await get(f"/api/jobs/{job_id}")
        if job.get("status") == "done":
            return job
        if job.get("status") == "error":
            raise EngineError(job.get("error") or "job failed")
        await asyncio.sleep(poll)
    raise EngineError(f"job {job_id} still running after {timeout}s; call shortsmith_job_status")


@server.tool()
async def shortsmith_health() -> dict:
    """Check the engine: ffmpeg, faster-whisper, planner and version."""
    return await get("/api/health")


@server.tool()
async def shortsmith_ingest(youtube_url: str) -> dict:
    """Download a YouTube video to the engine and return the file_id used by every other tool."""
    if not youtube_url.strip():
        raise EngineError("youtube_url is empty")
    result = await post("/api/ingest", {"url": youtube_url.strip()}, timeout=900)
    return {
        "file_id": result.get("file_id"),
        "bytes": result.get("bytes"),
        "duration": result.get("duration"),
    }


@server.tool()
async def shortsmith_transcribe(file_id: str, language: str = "en", model: str = "tiny") -> dict:
    """Transcribe with faster-whisper. model is tiny (fast) or base (more accurate)."""
    job = await post("/api/transcribe", {"file_id": file_id, "language": language, "model": model})
    done = await wait_job(job["job_id"], timeout=7200, poll=3.0)
    segments = done.get("segments") or []
    return {"language": done.get("lang") or language, "segments": segments, "count": len(segments)}


@server.tool()
async def shortsmith_plan(
    file_id: str,
    length: int = 30,
    segments: list | None = None,
    limit: int = 12,
) -> dict:
    """Rank the best clip windows by speech density, hook words and clean boundaries.

    Pass the segments from shortsmith_transcribe, or omit them for evenly spaced cuts.
    Each cut has start, end, score, title, words and hooks. Edit titles before generating.
    """
    payload = {"file_id": file_id, "length": int(length), "limit": int(limit)}
    if segments:
        payload["segments"] = segments
    return await post("/api/plan", payload)


@server.tool()
async def shortsmith_generate(
    file_id: str,
    length: int = 30,
    ratio: str = "9:16",
    plan: list | None = None,
    segments: list | None = None,
    captions: bool = True,
    hook: bool = True,
    cap_style: str = "teal",
    cap_font: str = "space",
    cap_size: int = 28,
    cap_y: float = 54,
    background: str = "blur",
    fit: str = "blur",
    center: bool = True,
    wait: bool = True,
) -> dict:
    """Cut, crop, burn captions and hook titles. Returns clip URLs.

    ratio: 9:16, 1:1 or 16:9. cap_style: teal, yellow or minimal.
    center: keep the speaker framed by cropping around the detected face.
    plan: the cuts list from shortsmith_plan (recommended); omit for even slices.
    """
    payload = {
        "file_id": file_id, "length": int(length), "ratio": ratio,
        "captions": bool(captions), "hook": bool(hook), "center": bool(center),
        "capStyle": cap_style, "capFont": cap_font, "capSize": int(cap_size), "capY": float(cap_y),
        "bg": background, "fit": fit,
    }
    if segments:
        payload["segments"] = segments
    if plan:
        payload["plan"] = [
            {"start": float(p.get("start", 0)),
             "len": float(p.get("len") or (float(p.get("end", 0)) - float(p.get("start", 0)))),
             "title": str(p.get("title") or "")}
            for p in plan
        ]
    job = await post("/api/generate", payload)
    if not wait:
        return {"job_id": job["job_id"], "status": "running"}
    done = await wait_job(job["job_id"], timeout=7200, poll=3.0)
    return {
        "job_id": job["job_id"],
        "status": "done",
        "clips": done.get("clips") or [],
        "items": done.get("items") or [],
    }


@server.tool()
async def shortsmith_job_status(job_id: str) -> dict:
    """Progress, log line, finished clips or the error for a running job."""
    return await get(f"/api/jobs/{job_id}")


@server.tool()
async def shortsmith_clips() -> dict:
    """Recently rendered clips with URLs, sizes and modified times."""
    return await get("/api/clips")


@server.tool()
async def shortsmith_styles(name: str = "", style: dict | None = None) -> dict:
    """List saved style recipes, or save one by passing both name and style."""
    if name and style:
        return await post("/api/presets", {"name": name, "style": style})
    return await get("/api/presets")


@server.tool()
async def shortsmith_make_shorts(
    youtube_url: str,
    length: int = 30,
    ratio: str = "9:16",
    language: str = "en",
    model: str = "tiny",
    limit: int = 6,
    captions: bool = True,
    hook: bool = True,
    cap_style: str = "teal",
    cap_font: str = "space",
    center: bool = True,
) -> dict:
    """One shot: download, transcribe, plan and render shorts from a YouTube link."""
    ingested = await shortsmith_ingest(youtube_url)
    file_id = ingested["file_id"]
    transcript = await shortsmith_transcribe(file_id, language=language, model=model)
    planned = await shortsmith_plan(file_id, length=length, segments=transcript["segments"], limit=limit)
    rendered = await shortsmith_generate(
        file_id=file_id, length=length, ratio=ratio, plan=planned["cuts"],
        segments=transcript["segments"], captions=captions, hook=hook,
        cap_style=cap_style, cap_font=cap_font, center=center,
    )
    return {
        "file_id": file_id,
        "segments": transcript["count"],
        "plan": planned["cuts"],
        "clips": rendered["clips"],
        "items": rendered["items"],
    }


if __name__ == "__main__":
    server.run()
