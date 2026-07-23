"""Password authentication for the dashboard API."""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone


class DashboardAuth:
    """Keeps short-lived dashboard sessions in memory.

    The configured password is never stored in a browser or returned by the
    API. Restarting the API deliberately invalidates every existing session.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, datetime] = {}

    @staticmethod
    def password_matches(candidate: str, expected: str | None) -> bool:
        if not candidate or not expected:
            return False
        return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))

    def create_session(self, ttl_minutes: int) -> str:
        self._remove_expired()
        token = secrets.token_urlsafe(32)
        self._sessions[token] = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        return token

    def is_valid_session(self, token: str | None) -> bool:
        if not token:
            return False
        expires_at = self._sessions.get(token)
        if expires_at is None:
            return False
        if expires_at <= datetime.now(timezone.utc):
            self._sessions.pop(token, None)
            return False
        return True

    def revoke_session(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def _remove_expired(self) -> None:
        now = datetime.now(timezone.utc)
        for token, expires_at in tuple(self._sessions.items()):
            if expires_at <= now:
                self._sessions.pop(token, None)
