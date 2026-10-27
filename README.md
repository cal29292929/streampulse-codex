# StreamPulse Codex — EventSub Co-Pilot, Chaos Poll Aggregator & Human-Gated Live Stream Director

> **Built for the [Codex x TwitchCon Hackathon](https://twitchcon-codex.devpost.com/) (October–November 2026)**
> **Multi-Model Pipeline**: Claude Opus 5.5 (`DESIGN_OPUS55.md`) + OpenAI Codex GPT-5.6 Luna (`REVIEW_LUNA56.md`, Session ID `01a17db5-d802-7142-af5d-1f98c633b614`) + Sakura AI Engine `preview/Kimi-K2.7-Code`
> **Author**: Kazutoshi Hayashi (`cal29292929`) | **License**: MIT

---

## 1. Overview & Architecture

**StreamPulse Codex** turns high-velocity Twitch chat and Channel Points redemptions into structured, streamer-approved interactive moments:
1. **RFC-Compliant EventSub HMAC-SHA256 Verifier (`verify_eventsub_signature`)**: Verifies `Twitch-Eventsub-Message-Signature` over `Message-Id + Message-Timestamp + raw_body` using constant-time `hmac.compare_digest`, enforces a 600-second replay window and 30-second future clock-skew guard, and deduplicates message IDs in a thread-safe LRU cache.
2. **Explicit EventSub Reconnect State Machine (`EventSubStateMachine`)**: Separates fresh `session_welcome` Helix subscription registration from `session_reconnect` seamless handover, and never reports `live_ready` if any required subscription fails (`degraded_partial`).
3. **100-Hz Viewer Chaos Poll Engine (`ChaosPollEngine`)**: Tallies viewer chaos commands (`!gravity_low`, `!spawn_boss`, `!heal_party`, `!invert_controls`) with per-user anti-brigading cooldowns and deterministic alphabetical tie-breaking.
4. **Channel Points Redemption Guard (`RedemptionGuard`)**: Verifies broadcaster & reward ownership, guarantees per-`redemption_id` idempotency, and sanitizes untrusted viewer `user_input` against XSS and prompt injection.
5. **Human-Gated Streamer Deck & Bounded Autopilot (`ApprovalGate`)**: Keeps Autopilot strictly disabled by default, blocks LLM/MCP callers from escalating Autopilot privileges, and atomically transitions human-approved proposals to the read-only OBS Browser Source overlay.
6. **Byte-Identical 600-Second (7-Phase) Stream Arc Simulation (`StreamPulseEngine`)**: Runs a full 10-minute virtual-clock stream arc in `< 0.5s` with zero external network calls and deterministic SHA-256 `result_digest`.

---

## 2. Quickstart (< 5 Seconds, Zero External Dependencies)

```bash
# Run unit test suite and generate 600s stream arc artifacts
./run_demo.sh

# Start the local Control Deck & OBS Overlay Server (loopback 127.0.0.1:8082)
python3 -m streampulse_codex.cli serve --host 127.0.0.1 --port 8082

# Run as a JSON-RPC 2.0 Model Context Protocol (MCP) stdio server
python3 -m streampulse_codex.cli mcp
```
