 ```python
# chatpulse_codex/core.py
"""Core primitives for the ChatPulse Codex x TwitchCon hackathon integration.

Standard library only; Python 3.11+.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

__all__ = [
    "verify_eventsub_signature",
    "VALID_CHAOS_COMMANDS",
    "ChaosPollEngine",
    "CodexSessionLedger",
    "CodexSessionEntry",
    "Opus55Review",
    "Gpt56LunaReview",
]

# ---------------------------------------------------------------------------
# EventSub signature verification
# ---------------------------------------------------------------------------

_MAX_SEEN_MSG_IDS = 10_000
_DEFAULT_REPLAY_WINDOW_SECONDS = 600

_SEEN_MSG_IDS: OrderedDict[str, float] = OrderedDict()
_SEEN_LOCK = threading.Lock()


def _parse_timestamp(value: str | float | datetime) -> datetime:
    """Parse an EventSub message timestamp into an aware UTC datetime."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)

    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    return datetime.fromisoformat(cleaned).astimezone(timezone.utc)


def _timestamp_bytes(value: str | float | datetime) -> bytes:
    """Return the timestamp bytes used in the HMAC payload."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().encode("utf-8")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().encode("utf-8")
    return value.encode("utf-8")


def verify_eventsub_signature(
    secret: bytes | str,
    msg_id: str,
    msg_timestamp: str | float | datetime,
    raw_body: bytes,
    signature_header: str,
    *,
    replay_window_seconds: float = _DEFAULT_REPLAY_WINDOW_SECONDS,
    max_seen_ids: int = _MAX_SEEN_MSG_IDS,
) -> bool:
    """Verify a Twitch EventSub HMAC-SHA256 signature and reject replays.

    The signature is computed over ``message_id + message_timestamp + body``.
    For the HMAC to match Twitch's value, ``msg_timestamp`` should be the raw
    header string when possible.

    Parameters
    ----------
    secret:
        EventSub subscription secret. Strings are encoded as UTF-8.
    msg_id:
        Value of the ``Twitch-Eventsub-Message-Id`` header.
    msg_timestamp:
        Value of the ``Twitch-Eventsub-Message-Timestamp`` header. Accepts an
        RFC 3339 / ISO 8601 string, Unix timestamp, or datetime.
    raw_body:
        Exact request body bytes as received from Twitch.
    signature_header:
        Value of the ``Twitch-Eventsub-Message-Signature`` header
        (``sha256=<hex>``).
    replay_window_seconds:
        Maximum age of a message before it is rejected as a replay.
    max_seen_ids:
        Maximum number of message IDs to retain for LRU deduplication.

    Returns
    -------
    bool
        ``True`` if the signature is valid and the message is not a replay.
    """
    if not msg_id or not signature_header:
        return False

    # 1. Replay-window check (stateless).
    try:
        msg_dt = _parse_timestamp(msg_timestamp)
    except Exception:
        return False

    now = datetime.now(timezone.utc)
    if now - msg_dt > timedelta(seconds=replay_window_seconds):
        return False

    # 2. HMAC-SHA256 verification.
    if isinstance(secret, str):
        secret = secret.encode("utf-8")

    payload = msg_id.encode("utf-8") + _timestamp_bytes(msg_timestamp) + raw_body
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    expected_header = f"sha256={expected}"

    if not hmac.compare_digest(expected_header, signature_header):
        return False

    # 3. LRU message-ID deduplication (mutates state only after valid sig).
    with _SEEN_LOCK:
        if msg_id in _SEEN_MSG_IDS:
            return False
        _SEEN_MSG_IDS[msg_id] = time.monotonic()
        _SEEN_MSG_IDS.move_to_end(msg_id)
        while len(_SEEN_MSG_IDS) > max_seen_ids:
            _SEEN_MSG_IDS.popitem(last=False)

    return True


def _clear_seen_eventsub_ids() -> None:
    """Clear the EventSub message-ID deduplication cache. Test hook."""
    with _SEEN_LOCK:
        _SEEN_MSG_IDS.clear()


# ---------------------------------------------------------------------------
# Chaos poll engine
# ---------------------------------------------------------------------------

VALID_CHAOS_COMMANDS = frozenset(
    {"!gravity_low", "!spawn_boss", "!heal_party", "!invert_controls"}
)


class ChaosPollEngine:
    """Tally viewer chaos commands with per-user cooldowns."""

    def __init__(self, cooldown_seconds: float = 10.0) -> None:
        if cooldown_seconds < 0:
            raise ValueError("cooldown must be non-negative")
        self._cooldown_seconds = cooldown_seconds
        self._tallies: dict[str, int] = {cmd: 0 for cmd in VALID_CHAOS_COMMANDS}
        self._last_used: dict[str, dict[str, float]] = {}
        self._lock = threading.RLock()

    @property
    def cooldown_seconds(self) -> float:
        return self._cooldown_seconds

    def set_cooldown(self, seconds: float) -> None:
        """Update the global per-user command cooldown."""
        if seconds < 0:
            raise ValueError("cooldown must be non-negative")
        self._cooldown_seconds = seconds

    def vote(self, user_id: str, command: str) -> tuple[bool, str]:
        """Register a viewer command.

        Returns
        -------
        tuple[bool, str]
            ``(accepted, reason)``. ``reason`` is ``"accepted"`` on success,
            otherwise ``"invalid_command"``, ``"invalid_user"``, or
            ``"cooldown:<seconds>"``.
        """
        command = command.lower().strip()
        if command not in VALID_CHAOS_COMMANDS:
            return False, "invalid_command"

        user_id = user_id.strip()
        if not user_id:
            return False, "invalid_user"

        now = time.monotonic()
        with self._lock:
            user_cooldowns = self._last_used.setdefault(user_id, {})
            last = user_cooldowns.get(command, 0.0)
            if now - last < self._cooldown_seconds:
                remaining = self._cooldown_seconds - (now - last)
                return False, f"cooldown:{remaining:.1f}"

            user_cooldowns[command] = now
            self._tallies[command] += 1

        return True, "accepted"

    def get_tallies(self) -> dict[str, int]:
        """Return a snapshot of current command tallies."""
        with self._lock:
            return dict(self._tallies)

    def get_leader(self) -> tuple[str | None, int]:
        """Return the command with the most votes and its count."""
        with self._lock:
            if not any(self._tallies.values()):
                return None, 0
            leader = max(self._tallies, key=self._tallies.get)  # type: ignore[arg-type]
            return leader, self._tallies[leader]

    def get_user_cooldown_remaining(self, user_id: str, command: str) -> float:
        """Return remaining cooldown seconds for a user/command."""
        command = command.lower().strip()
        user_id = user_id.strip()
        with self._lock:
            last = self._last_used.get(user_id, {}).get(command, 0.0)
            return max(0.0, self._cooldown_seconds - (time.monotonic() - last))

    def reset(self) -> None:
        """Reset all tallies and cooldowns."""
        with self._lock:
            self._tallies = {cmd: 0 for cmd in VALID_CHAOS_COMMANDS}
            self._last_used.clear()


# ---------------------------------------------------------------------------
# Codex session ledger
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Opus55Review:
    score: float | None = None
    notes: str = ""
    reviewed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Gpt56LunaReview:
    score: float | None = None
    notes: str = ""
    reviewed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CodexSessionEntry:
    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    opus_55: Opus55Review = field(default_factory=Opus55Review)
    gpt_56_luna: Gpt56LunaReview = field(default_factory=Gpt56LunaReview)
    metadata: dict[str, Any] = field(default_factory=dict)


class CodexSessionLedger:
    """Track OpenAI Codex Session IDs with Opus 5.5 and GPT-5.6 Luna reviews."""

    def __init__(self) -> None:
        self._sessions: dict[str, CodexSessionEntry] = {}
        self._lock = threading.RLock()

    def create_session(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> CodexSessionEntry:
        """Create a new Codex session entry."""
        if not session_id:
            raise ValueError("session_id is required")
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"session already exists: {session_id}")
            entry = CodexSessionEntry(
                session_id=session_id,
                created_at=created_at or datetime.now(timezone.utc),
                metadata=dict(metadata) if metadata else {},
            )
            self._sessions[session_id] = entry
            return entry

    def get_session(self, session_id: str) -> CodexSessionEntry | None:
        """Retrieve a session entry by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def add_opus_55_review(
        self,
        session_id: str,
        *,
        score: float | None = None,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CodexSessionEntry:
        """Attach or update the Opus 5.5 review for a session."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                raise KeyError(f"session not found: {session_id}")
            entry.opus_55 = Opus55Review(
                score=score,
                notes=notes,
                reviewed_at=datetime.now(timezone.utc),
                metadata=dict(metadata) if metadata else {},
            )
            return entry

    def add_gpt_56_luna_review(
        self,
        session_id: str,
        *,
        score: float | None = None,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CodexSessionEntry:
        """Attach or update the GPT-5.6 Luna review for a session."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                raise KeyError(f"session not found: {session_id}")
            entry.gpt_56_luna = Gpt56LunaReview(
                score=score,
                notes=notes,
                reviewed_at=datetime.now(timezone.utc),
                metadata=dict(metadata) if metadata else {},
            )
            return entry

    def list_sessions(self) -> list[CodexSessionEntry]:
        """Return a snapshot of all sessions."""
        with self._lock:
            return list(self._sessions.values())

    def summarize(self) -> dict[str, Any]:
        """Return aggregate review statistics."""
        with self._lock:
            opus_scores = [
                e.opus_55.score for e in self._sessions.values() if e.opus_55.score is not None
            ]
            gpt_scores = [
                e.gpt_56_luna.score
                for e in self._sessions.values()
                if e.gpt_56_luna.score is not None
            ]

            def avg(scores: list[float]) -> float | None:
                return sum(scores) / len(scores) if scores else None

            return {
                "total_sessions": len(self._sessions),
                "opus_55": {
                    "reviewed": len(opus_scores),
                    "average_score": avg(opus_scores),
                },
                "gpt_56_luna": {
                    "reviewed": len(gpt_scores),
                    "average_score": avg(gpt_scores),
                },
            }
```