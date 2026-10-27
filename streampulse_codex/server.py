"""
HTTP Control Deck & Read-Only OBS Overlay Server for StreamPulse Codex (`05-twitchcon-codex`).
Enforces GPT-5.6 Luna P0 security controls:
- Unauthenticated `/api/v1/health` and `/api/v1/overlay` never leak `codex_session_id` or tokens.
- Bounded request bodies and strict HTML escaping on all viewer inputs.
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import urllib.parse
from typing import Any, Dict, Optional

from .engine import StreamPulseEngine
from .mcp_server import StreamPulseMCPServer


MAX_BODY_BYTES = 262_144

DECK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>StreamPulse Codex — Live Streamer Control Deck &amp; EventSub Co-Pilot</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  body { margin: 0; padding: 24px; background: #0e0e10; color: #efeff1; font-family: system-ui, sans-serif; }
  header { padding: 18px 24px; background: #18181b; border: 1px solid #9147ff; border-radius: 12px; margin-bottom: 18px; display: flex; justify-content: space-between; align-items: center; }
  .badge { background: rgba(145, 71, 255, 0.2); color: #bf94ff; border: 1px solid #9147ff; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .panel { background: #18181b; border: 1px solid #303032; border-radius: 12px; padding: 20px; }
  button { width: 100%; padding: 12px; border-radius: 8px; border: none; background: #9147ff; color: #fff; font-weight: 700; cursor: pointer; }
  pre { background: #09090b; padding: 12px; border-radius: 8px; border: 1px solid #27272a; overflow-x: auto; font-size: 12px; }
</style>
</head>
<body>
<header>
  <div>
    <h1 style="margin:0;font-size:22px;">StreamPulse Codex Control Deck</h1>
    <div style="color:#adadb8;font-size:13px;margin-top:4px;">Twitch EventSub + Chaos Poll Aggregator + Human-Gated AI Co-Pilot</div>
  </div>
  <span class="badge">Codex x TwitchCon Hackathon</span>
</header>
<div class="grid">
  <div class="panel">
    <h2 style="margin-top:0;font-size:18px;">1. 600s (7-Phase) Stream Arc Simulation</h2>
    <button id="runBtn">Run Deterministic 10-Min Stream Arc (Seed 42)</button>
    <pre id="statusBox">Ready.</pre>
  </div>
  <div class="panel">
    <h2 style="margin-top:0;font-size:18px;">2. EventSub State, Tallies &amp; Approved Proposal</h2>
    <pre id="resultBox">Awaiting run...</pre>
  </div>
</div>
<script>
document.getElementById("runBtn").addEventListener("click", async () => {
  const resp = await fetch("/api/v1/simulate", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({seed: 42})
  });
  const data = await resp.json();
  document.getElementById("statusBox").textContent = "Run ID: " + data.run_id + " | Digest: " + data.result_digest;
  document.getElementById("resultBox").textContent = JSON.stringify(data, null, 2);
});
</script>
</body>
</html>
"""


class StreamPulseRequestHandler(BaseHTTPRequestHandler):
    engine: StreamPulseEngine = StreamPulseEngine()
    mcp_server: StreamPulseMCPServer = StreamPulseMCPServer(engine=engine)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            raw = DECK_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if path == "/api/v1/health":
            # P0 security fix: never expose codex_session_id or tokens on unauthenticated health endpoint
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "streampulse-codex",
                    "version": "1.0.0",
                    "autopilot_default": False,
                },
            )
            return

        if path == "/api/v1/overlay":
            # Read-only sanitized view for OBS Browser Source
            sim = self.engine.run_stream_arc(seed=42)
            self._send_json(
                HTTPStatus.OK,
                {
                    "leader_command": sim["leader_command"],
                    "leader_votes": sim["leader_votes"],
                    "tallies": sim["tallies"],
                    "active_proposal": sim["director_proposal"],
                },
            )
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint: {path}"})

    def do_POST(self) -> None:
        length_str = self.headers.get("Content-Length")
        if not length_str:
            self._send_json(HTTPStatus.LENGTH_REQUIRED, {"error": "Content-Length required"})
            return
        try:
            length = int(length_str)
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length"})
            return
        if length < 0 or length > MAX_BODY_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Payload too large"})
            return

        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Malformed JSON"})
            return

        path = urllib.parse.urlparse(self.path).path
        if path == "/mcp":
            resp = self.mcp_server.handle_jsonrpc(body)
            self._send_json(HTTPStatus.OK, resp or {"jsonrpc": "2.0", "result": "accepted"})
            return

        if path == "/api/v1/simulate":
            seed = body.get("seed", 42)
            if isinstance(seed, bool) or not isinstance(seed, int):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "seed must be an integer"})
                return
            res = self.engine.run_stream_arc(seed=seed)
            # Exclude internal session IDs from browser response
            safe_res = {k: v for k, v in res.items() if k != "codex_provenance"}
            self._send_json(HTTPStatus.OK, safe_res)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint: {path}"})


def create_http_server(
    host: str = "127.0.0.1",
    port: int = 8082,
    engine: Optional[StreamPulseEngine] = None,
) -> ThreadingHTTPServer:
    eng = engine or StreamPulseEngine()

    class BoundHandler(StreamPulseRequestHandler):
        pass

    BoundHandler.engine = eng
    BoundHandler.mcp_server = StreamPulseMCPServer(engine=eng)
    return ThreadingHTTPServer((host, port), BoundHandler)
