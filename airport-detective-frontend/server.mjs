import { createServer, request as httpRequest } from "node:http";
import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize, resolve } from "node:path";

function getArg(name, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const root = resolve(process.cwd(), getArg("root", "."));
const port = Number(getArg("port", process.env.PORT || 5173));
const maxPort = port + 10;
const backend = new URL(process.env.BACKEND_URL || "http://127.0.0.1:5180");

function proxyBackend(req, res) {
  const headers = { ...req.headers, host: backend.host };
  if (headers.origin && new URL(headers.origin).host === req.headers.host) headers.origin = backend.origin;
  const upstream = httpRequest(new URL(req.url, backend), { method: req.method, headers }, response => {
    res.writeHead(response.statusCode, response.headers);
    response.pipe(res);
  });
  const timeout = req.method === "POST" && /\/archive\/L\d+\/replay$/.test(req.url || "") ? 75000 : 15000;
  upstream.setTimeout(timeout, () => upstream.destroy(new Error("后端请求超时")));
  upstream.on("error", error => {
    if (!res.headersSent) writeJson(res, 502, { error: "后端尚未启动，请运行 total-program/start-monitor.cmd。" });
    else res.destroy(error);
  });
  req.on("aborted", () => upstream.destroy());
  res.on("close", () => upstream.destroy());
  req.pipe(upstream);
}
const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".mp4": "video/mp4"
};

function writeJson(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store"
  });
  res.end(body);
}

function resolveRequestPath(url) {
  const safeUrl = decodeURIComponent(url.split("?")[0]);
  const candidate = normalize(safeUrl === "/" ? "/index.html" : safeUrl);
  const resolved = resolve(join(root, candidate));
  if (!resolved.startsWith(root)) {
    return null;
  }
  return resolved;
}

async function handleRequest(req, res) {
  if ((req.url || "").startsWith("/api/")) return proxyBackend(req, res);
  const filePath = resolveRequestPath(req.url || "/");
  if (!filePath || !existsSync(filePath) || !statSync(filePath).isFile()) {
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Not found");
    return;
  }

  const stats = statSync(filePath);
  const contentType = mimeTypes[extname(filePath).toLowerCase()] || "application/octet-stream";
  const range = req.headers.range;

  if (range) {
    const [startText, endText] = range.replace(/bytes=/, "").split("-");
    const start = Number.parseInt(startText, 10);
    const end = endText ? Number.parseInt(endText, 10) : stats.size - 1;

    if (Number.isNaN(start) || Number.isNaN(end) || start >= stats.size || end >= stats.size) {
      res.writeHead(416, { "Content-Range": `bytes */${stats.size}` });
      res.end();
      return;
    }

    res.writeHead(206, {
      "Content-Range": `bytes ${start}-${end}/${stats.size}`,
      "Accept-Ranges": "bytes",
      "Content-Length": end - start + 1,
      "Content-Type": contentType,
      "Cache-Control": "no-store"
    });
    if (req.method === "HEAD") {
      res.end();
      return;
    }
    createReadStream(filePath, { start, end }).pipe(res);
    return;
  }

  res.writeHead(200, {
    "Content-Type": contentType,
    "Content-Length": stats.size,
    "Accept-Ranges": "bytes",
    "Cache-Control": "no-store"
  });
  if (req.method === "HEAD") {
    res.end();
    return;
  }
  createReadStream(filePath).pipe(res);
}

function startServer(currentPort) {
  const server = createServer((req, res) => {
    handleRequest(req, res).catch((error) => {
      console.error(error);
      writeJson(res, 500, { success: false, message: "服务器内部错误" });
    });
  });
  server.on("error", (error) => {
    if (error.code === "EADDRINUSE" && currentPort < maxPort) {
      console.warn(`Port ${currentPort} is already in use, trying ${currentPort + 1}...`);
      startServer(currentPort + 1);
      return;
    }
    throw error;
  });
  server.listen(currentPort, "127.0.0.1", () => {
    console.log(`Rail left-item detection demo: http://localhost:${currentPort}/`);
  });
}

startServer(port);
