const http = require("http");
const fs = require("fs");
const path = require("path");
const { execFile } = require("child_process");
const os = require("os");

const root = __dirname;
const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml"
};

function ytId(u) {
  const m = /youtu\.be\/([^\?&]+)/.exec(u) || /[?&]v=([^\?&]+)/.exec(u) || /embed\/([^\?&]+)/.exec(u) || /shorts\/([^\?&]+)/.exec(u);
  return m ? m[1] : null;
}

const server = http.createServer((req, res) => {
  const method = req.method;
  const rawUrl = req.url.split("?")[0];
  const urlPath = decodeURIComponent(rawUrl);

  if (method === "POST" && urlPath === "/api/youtube") {
    let body = "";
    req.on("data", (c) => { body += c; if (body.length > 4096) req.destroy(); });
    req.on("end", () => {
      let data;
      try { data = JSON.parse(body || "{}"); } catch { res.writeHead(400, {"content-type":"application/json"}).end(JSON.stringify({error:"bad json"})); return; }
      const url = String(data.url || "");
      const id = ytId(url);
      if (!id) { res.writeHead(400, {"content-type":"application/json"}).end(JSON.stringify({error:"Not a YouTube link"})); return; }
      const tmp = path.join(os.tmpdir(), "shortsmith-yt-" + id + ".mp4");
      const bin = "yt-dlp";
      const args = ["-f", "best[ext=mp4][filesize<500M]/best[ext=mp4]/best", "--no-playlist", "-o", tmp, "--merge-output-format", "mp4", url];
      console.log("yt-dlp fetching", id);
      execFile(bin, args, { timeout: 10 * 60 * 1000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
        if (err || !fs.existsSync(tmp)) {
          console.error("yt-dlp failed", (stderr || "").slice(0, 500));
          res.writeHead(500, {"content-type":"application/json"}).end(JSON.stringify({error:"Download failed. Is yt-dlp installed? Try: pip install yt-dlp (Python 3)."}));
          return;
        }
        res.writeHead(200, { "content-type": "video/mp4", "content-length": fs.statSync(tmp).size, "content-disposition": 'attachment; filename="shortsmith-youtube-' + id + '.mp4"' });
        fs.createReadStream(tmp).pipe(res).on("close", () => { try { fs.unlinkSync(tmp); } catch {} });
      });
    });
    return;
  }

  if (method === "GET" && urlPath === "/api/health") {
    res.writeHead(200, {"content-type":"application/json"}).end(JSON.stringify({ok:true, yt:true}));
    return;
  }

  const file = path.join(root, urlPath === "/" ? "index.html" : urlPath);
  if (!file.startsWith(root)) {
    res.writeHead(403).end("forbidden");
    return;
  }
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(404).end("not found");
      return;
    }
    res.writeHead(200, { "content-type": types[path.extname(file)] || "application/octet-stream" });
    res.end(data);
  });
});
server.listen(8080, "0.0.0.0", () => console.log("serving on http://0.0.0.0:8080"));
