# StreamPulse Codex — 10-Minute Stream Arc Report (`streampulse-b8cbe7ca56f0`)

- **Result Digest**: `sha256:b8cbe7ca56f09f63c347871f64547623cf9e3e07e2de8bf6b5ee6ed868102d59`
- **Total Stream Arc Duration**: `600 seconds` (7 phases)
- **Accepted Viewer Votes**: `268` | **Cooldown Filtered**: `12`
- **Winning Chaos Command**: `!heal_party` (`71` votes)
- **EventSub State Machine**: `live_ready` (`live_ready=True`, Session `es-sess-42-handover`)

## 1. 7-Phase Stream Arc Telemetry (600s Total)

| Phase | Label | Window (s) | Accepted Votes | Cooldown Blocked | Leader Command |
| :---: | :--- | :---: | :---: | :---: | :---: |
| `01_intro_warmup` | Stream Warmup & Chat Greeting | 0-60s (60s) | 38 | 2 | `!invert_controls` (12) |
| `02_exploration_build` | Dungeon Exploration & Viewer Loadout Vote | 60-150s (90s) | 40 | 0 | `!invert_controls` (24) |
| `03_miniboss_spike` | Mini-Boss Encounter & Velocity Spike | 150-240s (90s) | 39 | 1 | `!gravity_low` (30) |
| `04_chaos_arena_voting` | High-Velocity Chaos Command Poll | 240-360s (120s) | 38 | 2 | `!heal_party` (42) |
| `05_boss_climax` | Boss Phase 2 Climax & Channel Points Surge | 360-450s (90s) | 36 | 4 | `!gravity_low` (50) |
| `06_clutch_recovery` | Clutch Recovery & Party Heal Poll | 450-540s (90s) | 40 | 0 | `!invert_controls` (62) |
| `07_victory_cooldown` | Victory Lap & Recap Summary | 540-600s (60s) | 37 | 3 | `!heal_party` (71) |

## 2. Human-Approved Streamer Deck Proposal

- **Proposal ID**: `prop-42-01` (`start_poll`)
- **Title**: Activate !heal_party for Boss Phase?
- **Options**: `Yes - Unleash Chaos!, No - Save the Party!, Double Boss Speed`
- **Status**: **approved_human** (Approved by `streamer_deck_human`)

## 3. Channel Points Redemption Security Audit

- **`redemp-42-01`**: status=`validated_pending_approval`, duplicate=`False`, sanitized_input=`Invert gravity for the final boss phase!`
- **`redemp-42-01`**: status=`validated_pending_approval`, duplicate=`True`, sanitized_input=``
- **`redemp-42-02`**: status=`rejected_refund_pending`, duplicate=`False`, sanitized_input=``
