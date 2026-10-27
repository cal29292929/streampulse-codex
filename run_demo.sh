#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
echo "[1/2] Running StreamPulse Codex unit, EventSub HMAC, RedemptionGuard & determinism tests..."
python3 -m unittest discover -s tests -v

echo "[2/2] Running deterministic 600-second (7-phase) Twitch stream arc simulation..."
python3 -m streampulse_codex.cli demo --seed 42 --out-dir artifacts
echo "Done. Artifacts written to artifacts/latest_stream_arc.json, artifacts/latest_stream_arc.md, and artifacts/codex_provenance.json."
