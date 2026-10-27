"""
Core primitives for StreamPulse Codex (`05-twitchcon-codex` — Codex x TwitchCon Hackathon).
Synthesized by Sakura AI Engine `preview/Kimi-K2.7-Code` and hardened per OpenAI Codex GPT-5.6 Luna review (`REVIEW_LUNA56.md`).
Standard library only; Python 3.11+.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import html
import math
import re
import threading
import time
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple


__all__ = [
    "verify_eventsub_signature",
    "_clear_seen_eventsub_ids",
    "VALID_CHAOS_COMMANDS",
    "ChaosPollEngine",
    "EventSubConnectionState",
    "EventSubStateMachine",
    "RedemptionGuard",
    "ActionType",
    "DirectorProposal",
    "ApprovalGate",
    "CodexSessionLedger",
    "CodexSessionEntry",
    "Opus55Review",
    "Gpt56LunaReview",
]

_MAX_SEEN_MSG_IDS = 10_000
_DEFAULT_REPLAY_WINDOW_SECONDS = 600.0
_MAX_FUTURE_SKEW_SECONDS = 30.0
_MAX_WEBHOOK_BODY_BYTES = 262_144  # 256 KiB cap

_SEEN_MSG_IDS: OrderedDict[str, float] = OrderedDict()
_SEEN_LOCK = threading.Lock()


def _parse_timestamp(value: str | float | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Naive datetime not allowed")
        return value.astimezone(timezone.utc)
    if isinstance(value, bool):
        raise ValueError("Boolean is not a valid timestamp")
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError("Non-finite timestamp")
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if not isinstance(value, str):
        raise ValueError("Unsupported timestamp type")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Empty timestamp")
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include timezone offset")
    return dt.astimezone(timezone.utc)


def _timestamp_bytes(value: str | float | datetime) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().encode("utf-8")
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().encode("utf-8")


def verify_eventsub_signature(
    secret: bytes | str,
    msg_id: str,
    msg_timestamp: str | float | datetime,
    raw_body: bytes,
    signature_header: str,
    *,
    replay_window_seconds: float = _DEFAULT_REPLAY_WINDOW_SECONDS,
    max_future_skew_seconds: float = _MAX_FUTURE_SKEW_SECONDS,
    max_seen_ids: int = _MAX_SEEN_MSG_IDS,
    now_fn: Optional[Callable[[], datetime]] = None,
) -> bool:
    """
    Verify a Twitch EventSub HMAC-SHA256 signature and atomically reject replays,
    future timestamps, oversized bodies, or malformed headers.
    """
    if not isinstance(msg_id, str) or not msg_id.strip() or len(msg_id) > 128:
        return False
    if not isinstance(signature_header, str) or not signature_header.startswith("sha256="):
        return False
    if not isinstance(raw_body, (bytes, bytearray)) or len(raw_body) > _MAX_WEBHOOK_BODY_BYTES:
        return False
    if not secret:
        return False

    try:
        msg_dt = _parse_timestamp(msg_timestamp)
    except Exception:
        return False

    now = now_fn() if now_fn is not None else datetime.now(timezone.utc)
    age = (now - msg_dt).total_seconds()
    if age > replay_window_seconds:
        return False
    if age < -max_future_skew_seconds:
        # Reject future timestamps beyond tight clock-skew tolerance
        return False

    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
    payload = msg_id.encode("utf-8") + _timestamp_bytes(msg_timestamp) + bytes(raw_body)
    expected_hex = hmac.new(secret_bytes, payload, hashlib.sha256).hexdigest()
    expected_header = f"sha256={expected_hex}"

    if not hmac.compare_digest(expected_header, signature_header):
        return False

    with _SEEN_LOCK:
        if msg_id in _SEEN_MSG_IDS:
            return False
        _SEEN_MSG_IDS[msg_id] = now.timestamp()
        _SEEN_MSG_IDS.move_to_end(msg_id)
        while len(_SEEN_MSG_IDS) > max_seen_ids:
            _SEEN_MSG_IDS.popitem(last=False)

    return True


def _clear_seen_eventsub_ids() -> None:
    with _SEEN_LOCK:
        _SEEN_MSG_IDS.clear()


VALID_CHAOS_COMMANDS: FrozenSet[str] = frozenset(
    {"!gravity_low", "!spawn_boss", "!heal_party", "!invert_controls"}
)


class ChaosPollEngine:
    """Thread-safe viewer chaos command aggregator with injectable clock and per-user cooldowns."""

    def __init__(
        self,
        cooldown_seconds: float = 10.0,
        clock_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        if isinstance(cooldown_seconds, bool) or not math.isfinite(cooldown_seconds) or cooldown_seconds < 0:
            raise ValueError("cooldown must be a finite non-negative number")
        self._cooldown_seconds = float(cooldown_seconds)
        self._clock_fn = clock_fn or time.monotonic
        self._tallies: Dict[str, int] = {cmd: 0 for cmd in sorted(VALID_CHAOS_COMMANDS)}
        self._last_used: Dict[str, Dict[str, float]] = {}
        self._lock = threading.RLock()

    @property
    def cooldown_seconds(self) -> float:
        return self._cooldown_seconds

    def vote(self, user_id: str, command: str) -> Tuple[bool, str]:
        if not isinstance(command, str) or not isinstance(user_id, str):
            return False, "invalid_input"
        cmd_norm = command.lower().strip()
        if cmd_norm not in VALID_CHAOS_COMMANDS:
            return False, "invalid_command"
        uid_norm = user_id.strip()
        if not uid_norm or len(uid_norm) > 64:
            return False, "invalid_user"

        now = float(self._clock_fn())
        with self._lock:
            user_cd = self._last_used.setdefault(uid_norm, {})
            if cmd_norm in user_cd:
                elapsed = now - user_cd[cmd_norm]
                if elapsed < self._cooldown_seconds:
                    remaining = self._cooldown_seconds - elapsed
                    return False, f"cooldown:{remaining:.1f}"
            user_cd[cmd_norm] = now
            self._tallies[cmd_norm] += 1
        return True, "accepted"

    def get_tallies(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._tallies)

    def get_leader(self) -> Tuple[Optional[str], int]:
        with self._lock:
            if not any(self._tallies.values()):
                return None, 0
            # Deterministic alphabetical tie-breaker
            leader = sorted(self._tallies.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            return leader[0], leader[1]

    def reset(self) -> None:
        with self._lock:
            self._tallies = {cmd: 0 for cmd in sorted(VALID_CHAOS_COMMANDS)}
            self._last_used.clear()


class EventSubConnectionState:
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    WELCOME_RECEIVED = "welcome_received"
    SUBSCRIBING = "subscribing"
    LIVE_READY = "live_ready"
    DEGRADED_PARTIAL = "degraded_partial"
    RECONNECTING_HANDOVER = "reconnecting_handover"


class EventSubStateMachine:
    """
    Explicit state machine separating fresh connect + Helix subscription registration
    from `session_reconnect` handover (P0 fix from REVIEW_LUNA56.md).
    Never reports `live_ready` if any required subscription failed.
    """

    REQUIRED_SUBSCRIPTIONS = (
        "channel.chat.message",
        "channel.channel_points_custom_reward_redemption.add",
        "channel.poll.begin",
        "channel.poll.end",
    )

    def __init__(self, required_subscriptions: Tuple[str, ...] = REQUIRED_SUBSCRIPTIONS) -> None:
        self._lock = threading.RLock()
        self.required_subscriptions = required_subscriptions
        self.state = EventSubConnectionState.DISCONNECTED
        self.active_session_id: Optional[str] = None
        self.pending_handover_session_id: Optional[str] = None
        self.subscription_statuses: Dict[str, str] = {sub: "unregistered" for sub in required_subscriptions}

    def on_connect_started(self) -> str:
        with self._lock:
            self.state = EventSubConnectionState.CONNECTING
            return self.state

    def on_welcome(self, session_id: str) -> str:
        if not session_id or not isinstance(session_id, str):
            raise ValueError("session_id must be a non-empty string")
        with self._lock:
            if self.state == EventSubConnectionState.RECONNECTING_HANDOVER:
                # Handover carries over existing Helix subscriptions without re-creating them
                self.active_session_id = session_id
                self.pending_handover_session_id = None
                self.state = (
                    EventSubConnectionState.LIVE_READY
                    if all(v == "enabled" for v in self.subscription_statuses.values())
                    else EventSubConnectionState.DEGRADED_PARTIAL
                )
                return self.state

            self.active_session_id = session_id
            self.state = EventSubConnectionState.WELCOME_RECEIVED
            return self.state

    def record_subscription_results(self, results: Dict[str, bool]) -> str:
        with self._lock:
            self.state = EventSubConnectionState.SUBSCRIBING
            for sub in self.required_subscriptions:
                ok = results.get(sub) is True
                self.subscription_statuses[sub] = "enabled" if ok else "failed"
            if all(status == "enabled" for status in self.subscription_statuses.values()):
                self.state = EventSubConnectionState.LIVE_READY
            else:
                self.state = EventSubConnectionState.DEGRADED_PARTIAL
            return self.state

    def on_session_reconnect_requested(self, new_reconnect_url: str) -> str:
        if not new_reconnect_url.startswith("wss://"):
            raise ValueError("Reconnect URL must use wss://")
        with self._lock:
            self.state = EventSubConnectionState.RECONNECTING_HANDOVER
            return self.state

    def on_unexpected_disconnect(self) -> str:
        with self._lock:
            self.state = EventSubConnectionState.DISCONNECTED
            self.active_session_id = None
            self.subscription_statuses = {sub: "unregistered" for sub in self.required_subscriptions}
            return self.state

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self.state,
                "live_ready": self.state == EventSubConnectionState.LIVE_READY,
                "active_session_id": self.active_session_id,
                "subscriptions": dict(self.subscription_statuses),
            }


_PROMPT_INJECTION_RE = re.compile(
    r"(ignore\s+previous\s+instructions|system\s+prompt|<script|javascript:|onerror=|onload=)",
    re.IGNORECASE,
)


class RedemptionGuard:
    """
    Validates Channel Points reward ownership, enforces idempotency per `redemption_id`,
    and sanitizes untrusted viewer `user_input` (P0 fix from REVIEW_LUNA56.md).
    """

    def __init__(self, broadcaster_id: str, owned_reward_ids: FrozenSet[str]) -> None:
        if not broadcaster_id:
            raise ValueError("broadcaster_id is required")
        self.broadcaster_id = broadcaster_id
        self.owned_reward_ids = frozenset(owned_reward_ids)
        self._redemption_states: Dict[str, str] = {}
        self._lock = threading.RLock()

    @staticmethod
    def sanitize_viewer_input(raw_text: str, max_len: int = 140) -> Tuple[bool, str, Optional[str]]:
        if not isinstance(raw_text, str):
            return False, "", "non_string_input"
        # Strip ASCII/Unicode control characters
        cleaned = "".join(ch for ch in raw_text if ch.isprintable() and ch not in ("\r", "\n", "\t"))
        cleaned = cleaned.strip()
        if not cleaned:
            return False, "", "empty_input"
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len]
        if _PROMPT_INJECTION_RE.search(cleaned):
            return False, "", "blocked_unsafe_pattern"
        escaped = html.escape(cleaned, quote=True)
        return True, escaped, None

    def process_redemption(
        self,
        redemption_id: str,
        broadcaster_id: str,
        reward_id: str,
        raw_user_input: str,
    ) -> Dict[str, Any]:
        if broadcaster_id != self.broadcaster_id:
            raise PermissionError("Broadcaster ID mismatch for redemption.")
        if reward_id not in self.owned_reward_ids:
            raise PermissionError(f"Reward {reward_id} is not owned by this StreamPulse client.")
        if not redemption_id or not isinstance(redemption_id, str):
            raise ValueError("redemption_id is required.")

        with self._lock:
            existing = self._redemption_states.get(redemption_id)
            if existing is not None:
                return {
                    "redemption_id": redemption_id,
                    "status": existing,
                    "duplicate": True,
                    "sanitized_input": "",
                }

            ok, sanitized, reason = self.sanitize_viewer_input(raw_user_input)
            if not ok:
                self._redemption_states[redemption_id] = "rejected_refund_pending"
                return {
                    "redemption_id": redemption_id,
                    "status": "rejected_refund_pending",
                    "duplicate": False,
                    "reject_reason": reason,
                    "sanitized_input": "",
                }

            self._redemption_states[redemption_id] = "validated_pending_approval"
            return {
                "redemption_id": redemption_id,
                "status": "validated_pending_approval",
                "duplicate": False,
                "sanitized_input": sanitized,
            }


class ActionType:
    START_POLL = "start_poll"
    SPAWN_CHAOS_EVENT = "spawn_chaos_event"
    ANNOUNCE_CHAT = "announce_chat"
    FULFILL_REWARD = "fulfill_reward"
    ALL = frozenset({START_POLL, SPAWN_CHAOS_EVENT, ANNOUNCE_CHAT, FULFILL_REWARD})


@dataclass(slots=True)
class DirectorProposal:
    proposal_id: str
    action_type: str
    title: str
    options: Tuple[str, ...]
    duration_seconds: int
    source_mode: str  # "live" | "simulated"
    status: str = "pending_approval"  # "pending_approval" | "approved_human" | "approved_autopilot" | "rejected"
    approved_by: Optional[str] = None


class ApprovalGate:
    """
    Human-in-the-Loop & Bounded Autopilot Gate (P0 fix from REVIEW_LUNA56.md).
    - Autopilot is strictly disabled by default.
    - LLM/MCP callers cannot mutate Autopilot configuration.
    - Approving a proposal is atomic and idempotent (prevents double execution).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._autopilot_enabled: bool = False
        self._autopilot_allowed_actions: FrozenSet[str] = frozenset()
        self._proposals: Dict[str, DirectorProposal] = {}

    def configure_autopilot_from_deck(self, *, enabled: bool, allowed_actions: List[str], caller_role: str) -> None:
        if caller_role != "deck_operator":
            raise PermissionError("Only human deck_operator may modify Autopilot settings.")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        invalid = [a for a in allowed_actions if a not in ActionType.ALL]
        if invalid:
            raise ValueError(f"Unsupported action types: {invalid}")
        with self._lock:
            self._autopilot_enabled = enabled
            self._autopilot_allowed_actions = frozenset(allowed_actions)

    @staticmethod
    def validate_proposal_schema(
        proposal_id: str,
        action_type: str,
        title: str,
        options: List[str],
        duration_seconds: int,
        source_mode: str,
    ) -> DirectorProposal:
        if action_type not in ActionType.ALL:
            raise ValueError(f"Invalid action_type: {action_type}")
        if not isinstance(title, str) or not (1 <= len(title.strip()) <= 60):
            raise ValueError("Title must be 1..60 characters.")
        if _PROMPT_INJECTION_RE.search(title):
            raise ValueError("Unsafe pattern in proposal title.")
        if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or not (15 <= duration_seconds <= 300):
            raise ValueError("duration_seconds must be an int in 15..300.")
        if action_type == ActionType.START_POLL:
            if not (2 <= len(options) <= 4):
                raise ValueError("start_poll requires 2..4 options.")
            cleaned_opts = [html.escape(o.strip(), quote=True) for o in options if isinstance(o, str) and 1 <= len(o.strip()) <= 25]
            if len(cleaned_opts) != len(options) or len(set(cleaned_opts)) != len(cleaned_opts):
                raise ValueError("Poll options must be unique and 1..25 chars each.")
        else:
            cleaned_opts = [html.escape(str(o).strip()[:40], quote=True) for o in options[:4]]

        return DirectorProposal(
            proposal_id=proposal_id,
            action_type=action_type,
            title=html.escape(title.strip(), quote=True),
            options=tuple(cleaned_opts),
            duration_seconds=duration_seconds,
            source_mode=source_mode if source_mode in ("live", "simulated") else "simulated",
        )

    def submit_proposal(self, proposal: DirectorProposal) -> DirectorProposal:
        with self._lock:
            if self._autopilot_enabled and proposal.action_type in self._autopilot_allowed_actions:
                proposal.status = "approved_autopilot"
                proposal.approved_by = "autopilot_policy"
            self._proposals[proposal.proposal_id] = proposal
            return proposal

    def approve_proposal(self, proposal_id: str, *, operator_id: str = "streamer_deck") -> DirectorProposal:
        with self._lock:
            prop = self._proposals.get(proposal_id)
            if prop is None:
                raise KeyError(f"Unknown proposal: {proposal_id}")
            if prop.status != "pending_approval":
                raise RuntimeError(f"Proposal {proposal_id} already transitioned to {prop.status}")
            prop.status = "approved_human"
            prop.approved_by = operator_id
            return prop


@dataclass(slots=True)
class Opus55Review:
    score: float | None = None
    notes: str = ""
    reviewed_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Gpt56LunaReview:
    score: float | None = None
    notes: str = ""
    reviewed_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CodexSessionEntry:
    session_id: str
    created_at_utc: str
    opus_55: Opus55Review = field(default_factory=Opus55Review)
    gpt_56_luna: Gpt56LunaReview = field(default_factory=Gpt56LunaReview)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CodexSessionLedger:
    """Track OpenAI Codex Session IDs with Opus 5.5 and GPT-5.6 Luna review metadata."""

    def __init__(self) -> None:
        self._sessions: Dict[str, CodexSessionEntry] = {}
        self._lock = threading.RLock()

    def create_session(
        self,
        session_id: str,
        *,
        created_at_utc: str = "2026-10-27T14:15:02Z",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CodexSessionEntry:
        if not session_id or not isinstance(session_id, str):
            raise ValueError("session_id is required")
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"session already exists: {session_id}")
            entry = CodexSessionEntry(
                session_id=session_id,
                created_at_utc=created_at_utc,
                metadata=dict(metadata) if metadata else {},
            )
            self._sessions[session_id] = entry
            return entry

    def add_opus_55_review(
        self,
        session_id: str,
        *,
        score: float,
        notes: str,
        reviewed_at: str = "2026-10-27T14:13:51Z",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CodexSessionEntry:
        with self._lock:
            entry = self._sessions[session_id]
            entry.opus_55 = Opus55Review(
                score=score,
                notes=notes,
                reviewed_at=reviewed_at,
                metadata=dict(metadata) if metadata else {},
            )
            return entry

    def add_gpt_56_luna_review(
        self,
        session_id: str,
        *,
        score: float,
        notes: str,
        reviewed_at: str = "2026-10-27T14:15:02Z",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CodexSessionEntry:
        with self._lock:
            entry = self._sessions[session_id]
            entry.gpt_56_luna = Gpt56LunaReview(
                score=score,
                notes=notes,
                reviewed_at=reviewed_at,
                metadata=dict(metadata) if metadata else {},
            )
            return entry

    def export_public_provenance(self) -> Dict[str, Any]:
        with self._lock:
            sessions = []
            for s in self._sessions.values():
                sessions.append(
                    {
                        "codex_session_id": s.session_id,
                        "created_at_utc": s.created_at_utc,
                        "opus_55_design": {
                            "score": s.opus_55.score,
                            "notes": s.opus_55.notes,
                            "reviewed_at": s.opus_55.reviewed_at,
                            "metadata": s.opus_55.metadata,
                        },
                        "gpt_56_luna_review": {
                            "score": s.gpt_56_luna.score,
                            "notes": s.gpt_56_luna.notes,
                            "reviewed_at": s.gpt_56_luna.reviewed_at,
                            "metadata": s.gpt_56_luna.metadata,
                        },
                        "metadata": s.metadata,
                    }
                )
            return {"total_sessions": len(sessions), "sessions": sessions}
