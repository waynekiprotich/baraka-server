"""Rate limiting, counted in PostgreSQL.

Two properties this has to keep:

1. Counts are written on their own connection, committed immediately. A
   request that is *rejected* -- or one whose own transaction rolls back --
   still counts, which is the whole point when the endpoint being protected is
   a failing login.
2. It fails open. If the table is missing (a fresh database before `db
   upgrade`) the limiter degrades to "no limiting" rather than to a dead API.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from flask import current_app
from sqlalchemy import delete, func, insert, select

from ..errors import RateLimitedError
from ..extensions import db
from ..models import RateLimitHit, utcnow

logger = logging.getLogger(__name__)

# How far past its window a row is kept before the sweep removes it.
SWEEP_MULTIPLIER = 4


def enforce(bucket: str, identifier: str) -> None:
    """Count this attempt and raise RATE_LIMITED once the allowance is spent."""
    limits = current_app.config.get("RATE_LIMITS", {})
    if bucket not in limits:
        return
    max_attempts, window_seconds = limits[bucket]
    now = utcnow()
    window_start = now - timedelta(seconds=window_seconds)

    try:
        engine = db.session.get_bind()
        with engine.connect() as connection:
            connection.execute(
                insert(RateLimitHit).values(
                    bucket=bucket, identifier=identifier, created_at=now
                )
            )
            connection.commit()

            attempts = connection.execute(
                select(func.count())
                .select_from(RateLimitHit)
                .where(
                    RateLimitHit.bucket == bucket,
                    RateLimitHit.identifier == identifier,
                    RateLimitHit.created_at >= window_start,
                )
            ).scalar_one()

            if attempts % 25 == 0:
                connection.execute(
                    delete(RateLimitHit).where(
                        RateLimitHit.created_at
                        < now - timedelta(seconds=window_seconds * SWEEP_MULTIPLIER)
                    )
                )
                connection.commit()
    except RateLimitedError:
        raise
    except Exception:  # noqa: BLE001 - deliberate fail-open
        logger.warning("Rate limiting unavailable for bucket=%s; allowing request", bucket,
                       exc_info=True)
        return

    if attempts > max_attempts:
        raise RateLimitedError(
            "Too many attempts. Please wait a few minutes and try again.",
            headers={"Retry-After": str(window_seconds)},
        )


def reset(bucket: str, identifier: str) -> None:
    """Clear an identifier's counter -- called after a successful login."""
    try:
        engine = db.session.get_bind()
        with engine.connect() as connection:
            connection.execute(
                delete(RateLimitHit).where(
                    RateLimitHit.bucket == bucket, RateLimitHit.identifier == identifier
                )
            )
            connection.commit()
    except Exception:  # noqa: BLE001 - deliberate fail-open
        logger.warning("Could not reset rate limit bucket=%s", bucket, exc_info=True)
