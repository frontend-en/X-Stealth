"""API error helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> HTTPException:
    """Create a stable API error envelope."""
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )
