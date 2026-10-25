"""
Redis Job Coordination & Progress Queue Service with FakeRedis Fallback (Phase 11 & Section 17).
Handles asynchronous queueing, real-time stage progress updates, and distributed job locking.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class RedisQueueService:
    """Manages Redis progress caching, background queues, and task locking."""

    def __init__(self):
        self._client = None
        self._init_client()

    def _init_client(self):
        import redis
        try:
            r = redis.from_url(settings.redis_url, socket_timeout=1.0)
            r.ping()
            self._client = r
            logger.info("Connected to live Redis server")
        except Exception:
            try:
                import fakeredis
                self._client = fakeredis.FakeRedis()
                logger.info("Using FakeRedis for asynchronous queue coordination (in-memory)")
            except Exception as e:
                logger.warning(f"Could not initialize FakeRedis: {e}")
                self._client = None

    def update_job_progress(
        self,
        job_id: str,
        progress: int,
        stage: str,
        detail: str = "",
    ) -> None:
        """Cache real-time job progress in Redis."""
        if not self._client:
            return
        try:
            data = json.dumps({"progress": progress, "stage": stage, "detail": detail})
            self._client.set(f"job:progress:{job_id}", data, ex=3600)
        except Exception as e:
            logger.debug(f"Redis progress update error: {e}")

    def get_job_progress(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve real-time job progress from Redis."""
        if not self._client:
            return None
        try:
            raw = self._client.get(f"job:progress:{job_id}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    def acquire_lock(self, key: str, timeout: int = 60) -> bool:
        """Acquire a distributed idempotency/job execution lock."""
        if not self._client:
            return True
        try:
            return bool(self._client.set(f"lock:{key}", "1", nx=True, ex=timeout))
        except Exception:
            return True

    def release_lock(self, key: str) -> None:
        """Release a distributed lock."""
        if not self._client:
            return
        try:
            self._client.delete(f"lock:{key}")
        except Exception:
            pass
