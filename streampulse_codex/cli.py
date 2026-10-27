"""
CLI Entrypoint for StreamPulse Codex (`streampulse_codex.cli`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List, Optional

from .engine import StreamPulseEngine
from .mcp_server import run_stdio_server
from .server import create_http_server


def render_markdown_report(data: dict) -> str:
    dp = data["director_proposal"]
    es = data["eventsub_state"]
    lines = [
        f"# StreamPulse Codex — 10-Minute Stream Arc Report (`{data['run_id']}`)",
        "",
        f"- **Result Digest**: `{data['result_digest']}`",
        f"- **Total Stream Arc Duration**: `{data['total_arc_seconds']} seconds` (7 phases)",
        f"- **Accepted Viewer Votes**: `{data['accepted_votes']}` | **Cooldown Filtered**: `{data['cooldown_rejected_votes']}`",
        f"- **Winning Chaos Command**: `{data['leader_command']}` (`{data['leader_votes']}` votes)",
        f"- **EventSub State Machine**: `{es['state']}` (`live_ready={es['live_ready']}`, Session `{es['active_session_id']}`)",
        "",
        "## 1. 7-Phase Stream Arc Telemetry (600s Total)",
        "",
        "| Phase | Label | Window (s) | Accepted Votes | Cooldown Blocked | Leader Command |",
        "| :---: | :--- | :---: | :---: | :---: | :---: |",
    ]
    for p in data["phases"]:
        lines.append(
            f"| `{p['phase_id']}` | {p['label']} | {p['start_sec']:.0f}-{p['end_sec']:.0f}s ({p['duration_sec']}s) | "
            f"{p['accepted_votes']} | {p['cooldown_rejected_votes']} | `{p['current_leader_command']}` ({p['current_leader_votes']}) |"
        )
    lines.extend(
        [
            "",
            "## 2. Human-Approved Streamer Deck Proposal",
            "",
            f"- **Proposal ID**: `{dp['proposal_id']}` (`{dp['action_type']}`)",
            f"- **Title**: {dp['title']}",
            f"- **Options**: `{', '.join(dp['options'])}`",
            f"- **Status**: **{dp['status']}** (Approved by `{dp['approved_by']}`)",
            "",
            "## 3. Channel Points Redemption Security Audit",
            "",
        ]
    )
    for r in data["redemption_audit"]:
        lines.append(
            f"- **`{r['redemption_id']}`**: status=`{r['status']}`, duplicate=`{r['duplicate']}`, sanitized_input=`{r.get('sanitized_input', '')}`"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="streampulse-codex", description="StreamPulse Codex CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_demo = sub.add_parser("demo", help="Run deterministic 600s stream arc and write artifacts")
    p_demo.add_argument("--seed", type=int, default=42)
    p_demo.add_argument("--out-dir", default="artifacts")

    p_serve = sub.add_parser("serve", help="Start local Control Deck & OBS Overlay HTTP server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8082)

    sub.add_parser("mcp", help="Run stdio JSON-RPC 2.0 MCP server")

    args = parser.parse_args(argv)
    engine = StreamPulseEngine()

    if args.cmd == "mcp":
        run_stdio_server()
        return 0

    if args.cmd == "serve":
        srv = create_http_server(host=args.host, port=args.port, engine=engine)
        print(f"StreamPulse Codex Control Deck listening on http://{args.host}:{args.port}")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            srv.server_close()
        return 0

    if args.cmd == "demo":
        res = engine.run_stream_arc(seed=args.seed)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "latest_stream_arc.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        (out_dir / "latest_stream_arc.md").write_text(render_markdown_report(res), encoding="utf-8")
        (out_dir / "codex_provenance.json").write_text(
            json.dumps(res["codex_provenance"], indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "run_id": res["run_id"],
                    "result_digest": res["result_digest"],
                    "total_arc_seconds": res["total_arc_seconds"],
                    "leader_command": res["leader_command"],
                },
                indent=2,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
