"""
JSON-RPC 2.0 Model Context Protocol (MCP) Server for StreamPulse Codex (`2025-06-18`).
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from .engine import StreamPulseEngine


MCP_PROTOCOL_VERSION = "2025-06-18"

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "streampulse_run_arc",
        "description": "Execute a deterministic 600-second (7-phase) Twitch EventSub & Chaos Poll stream arc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "seed": {"type": "integer", "default": 42},
                "mode": {"type": "string", "enum": ["simulated", "hybrid", "live"], "default": "simulated"},
            },
        },
    },
    {
        "name": "streampulse_get_provenance",
        "description": "Return OpenAI Codex Session ID, Claude Opus 5.5 design metadata, and Sakura Kimi-K2.7-Code synthesis provenance.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class StreamPulseMCPServer:
    def __init__(self, engine: Optional[StreamPulseEngine] = None) -> None:
        self.engine = engine or StreamPulseEngine()

    def handle_jsonrpc(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32600, "message": "Invalid JSON-RPC 2.0 request."},
            }

        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params") or {}

        if method == "notifications/initialized" or (req_id is None and method.startswith("notifications/")):
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "streampulse-codex-mcp", "version": "1.0.0"},
                },
            }

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}

        if method == "tools/call":
            if not isinstance(params, dict):
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "Invalid params"}}
            name = params.get("name")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "arguments must be an object"}}
            try:
                if name == "streampulse_run_arc":
                    seed = args.get("seed", 42)
                    if isinstance(seed, bool) or not isinstance(seed, int):
                        raise ValueError("seed must be an integer")
                    mode = args.get("mode", "simulated")
                    if mode not in ("simulated", "hybrid", "live"):
                        raise ValueError("Invalid mode")
                    res = self.engine.run_stream_arc(seed=seed, mode=mode)
                elif name == "streampulse_get_provenance":
                    res = self.engine.run_stream_arc(seed=42)["codex_provenance"]
                else:
                    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}],
                        "isError": False,
                    },
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"error": str(exc)}, ensure_ascii=False)}],
                        "isError": True,
                    },
                }

        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def run_stdio_server() -> None:
    server = StreamPulseMCPServer()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        resp = server.handle_jsonrpc(payload)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
