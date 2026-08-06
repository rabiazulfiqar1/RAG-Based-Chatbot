"""
Redis-backed sliding-window rate limiter using sorted sets.
Atomic via Lua script — no fixed-window boundary exploit, no race conditions
between concurrent requests. Works on plain Redis (no RediSearch needed).
Supports both a per-user cap and a global cap (useful when protecting
personal API keys on a demo project).
"""
import time
import uuid
import asyncio
from fastapi import HTTPException, Request, Depends
from typing import Dict, Any, Optional

from app.core.connections import redis_client
from app.auth.supabase_auth import get_current_user


# Atomically: trim expired entries, count remaining, add current request if allowed.
# KEYS[1] = zset key
# ARGV[1] = current timestamp (float, seconds)
# ARGV[2] = window size (seconds)
# ARGV[3] = max requests allowed in window
# ARGV[4] = unique member id for this request (avoids score collisions)
_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

if count < max_requests then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, window)
    return count + 1
else
    return -1
end
"""


class RateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        prefix: str,
        global_max_requests: Optional[int] = None,
        global_window_seconds: Optional[int] = None,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.prefix = prefix
        self.global_max_requests = global_max_requests
        self.global_window_seconds = global_window_seconds or window_seconds
        self._script = None  # registered lazily against redis_client

    def _get_script(self):
        if self._script is None:
            self._script = redis_client.register_script(_SLIDING_WINDOW_SCRIPT)
        return self._script

    def _check(self, key: str, max_requests: int, window_seconds: int) -> int:
        if redis_client is None:
            return 1  # fail open — don't block requests if Redis is unavailable

        script = self._get_script()
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex}"  # unique even for same-millisecond requests

        return script(
            keys=[key],
            args=[now, window_seconds, max_requests, member],
        )

    async def __call__(
        self,
        request: Request,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        user_id = current_user.get("id")
        identifier = user_id or (request.client.host if request.client else "anonymous")

        # Global check first — protects your API keys regardless of how many
        # distinct users/IPs are hitting the endpoint
        if self.global_max_requests:
            global_key = f"{self.prefix}:global"
            global_result = await asyncio.to_thread(
                self._check, global_key, self.global_max_requests, self.global_window_seconds
            )
            if global_result == -1:
                raise HTTPException(
                    status_code=429,
                    detail="Service is at capacity right now — this is a demo project running on personal API keys. Please try again later.",
                    headers={"Retry-After": str(self.global_window_seconds)},
                )

        # Per-user check
        user_key = f"{self.prefix}:{identifier}"
        user_result = await asyncio.to_thread(
            self._check, user_key, self.max_requests, self.window_seconds
        )
        if user_result == -1:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self.max_requests} requests per {self.window_seconds}s.",
                headers={"Retry-After": str(self.window_seconds)},
            )

        return current_user