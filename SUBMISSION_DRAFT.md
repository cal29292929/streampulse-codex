# Devpost Submission Draft — Codex x TwitchCon Hackathon (`05-twitchcon-codex`)

- **Devpost URL**: https://twitchcon-codex.devpost.com/
- **Submission Deadline (JST)**: `2026-11-03T07:00:00+09:00`
- **Project Name**: StreamPulse Codex: EventSub Co-Pilot & Human-Gated Live Stream Director
- **Elevator Pitch**: Real-time Twitch EventSub co-pilot with RFC 9110 HMAC-SHA256 replay defense, privacy-scrubbed sentiment velocity, and a human-in-the-loop moderator state machine built with OpenAI Codex.
- **Target GitHub Repository URL**: `https://github.com/cal29292929/streampulse-codex`
- **Target GitHub Release URL**: `https://github.com/cal29292929/streampulse-codex/releases/tag/v1.0.0`
- **Demo Video**: `/workspace/hackathons/05-twitchcon-codex/submission_assets/demo_video.mp4` (1920x1080, 150s, H.264/AAC)
- **Unit Test Suite**: `6 passed`

## Built With Tags
- `openai-codex`
- `gpt-6-luna`
- `claude-opus-5-5`
- `sakura-ai-engine`
- `twitch-eventsub`
- `model-context-protocol`
- `python`

## Try It Out URLs
- https://github.com/cal29292929/streampulse-codex
- https://github.com/cal29292929/streampulse-codex/releases/tag/v1.0.0

## About the Project (Copy-Paste Ready for Devpost)

## Inspiration
High-velocity Twitch streams generate hundreds of chat messages, raids, and channel point redemptions per minute. Streamers and moderators need an intelligent co-pilot that surfaces hype spikes, launches context-aware polls/predictions, and protects chat safety—without ever letting an autonomous agent execute destructive moderation or stream mutations without human approval.

## What it does
**StreamPulse Codex** (`streampulse_codex`) delivers a 4-layer live stream co-pilot:
1. **RFC 9110 Twitch EventSub HMAC-SHA256 Verifier**: Enforces constant-time `hmac.compare_digest` verification (`sha256=` prefix), 600-second replay window, and LRU `message_id` deduplication.
2. **Privacy-First Chat Velocity & Hype Detector**: Scrubs emails, phone numbers, URLs, and `@mentions` (`len <= 500`) before computing rolling 30-second excitement/sentiment scores.
3. **Human-Gated Action Card State Machine**: Every poll, prediction, clip marker, or timeout goes through `PROPOSED -> APPROVED / REJECTED -> EXECUTED` with full audit trails.
4. **MCP JSON-RPC 2.0 Server**: Exposes `get_stream_telemetry` and `propose_director_card` for live studio assistants.

## OpenAI Codex Verification (Stage One Requirement)
- **Codex Architecture & Security Review Session ID**: `01a17db5-d802-7142-af5d-1f98c633b614`
- **Codex Post-Implementation Code Review Session ID**: `01a17dc6-c36f-7650-8e6e-1e44776a2c1e`
- Recorded in `artifacts/codex_provenance.json`, `REVIEW_LUNA56.md`, and `CODE_REVIEW_LUNA56.md`.


## Multi-Model Pipeline Provenance & Custom Questions
```json
{
  "codex_session_ids": [
    "01a17db5-d802-7142-af5d-1f98c633b614",
    "01a17dc6-c36f-7650-8e6e-1e44776a2c1e"
  ],
  "opus55_session_id": "33899088-2f8f-4cbf-8762-d1a002a47bf7",
  "sakura_model": "preview/Kimi-K2.7-Code"
}
```

## Screenshots (1920x1080 PNG)
- `/workspace/hackathons/05-twitchcon-codex/submission_assets/00_thumbnail.png`
- `/workspace/hackathons/05-twitchcon-codex/submission_assets/01_eventsub_state_machine_and_hmac.png`
- `/workspace/hackathons/05-twitchcon-codex/submission_assets/02_chaos_poll_and_stream_arc.png`
- `/workspace/hackathons/05-twitchcon-codex/submission_assets/03_redemption_guard_and_xss_protection.png`
- `/workspace/hackathons/05-twitchcon-codex/submission_assets/04_human_approval_gate_and_overlay.png`
- `/workspace/hackathons/05-twitchcon-codex/submission_assets/05_codex_session_provenance.png`
- `/workspace/hackathons/05-twitchcon-codex/submission_assets/06_test_verification_and_quickstart.png`
