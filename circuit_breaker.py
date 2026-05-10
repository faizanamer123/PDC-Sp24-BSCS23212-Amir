import time
import asyncio
import logging
from enum import Enum
from functools import wraps
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 3,
        recovery_timeout: float = 10.0,
        expected_exception: type = Exception,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                logger.info("[CB:%s] Recovery timeout elapsed -> HALF_OPEN", self.name)
                self._state = CircuitState.HALF_OPEN
        return self._state

    async def call(self, func: Callable, *args, fallback: Any = None, **kwargs) -> Any:
        async with self._lock:
            current_state = self.state

        if current_state == CircuitState.OPEN:
            logger.warning("[CB:%s] Circuit OPEN -- fast-fail", self.name)
            if fallback is not None:
                return fallback
            raise CircuitBreakerOpenError(f"Circuit '{self.name}' is OPEN")

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except self.expected_exception as exc:
            await self._on_failure(exc)
            if fallback is not None:
                logger.info("[CB:%s] Returning fallback response", self.name)
                return fallback
            raise

    async def _on_success(self):
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("[CB:%s] Probe succeeded -> CLOSED", self.name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None

    async def _on_failure(self, exc: Exception):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            logger.warning("[CB:%s] Failure #%d: %s", self.name, self._failure_count, exc)
            if self._failure_count >= self.failure_threshold:
                logger.error("[CB:%s] Threshold reached (%d) -> OPEN", self.name, self.failure_threshold)
                self._state = CircuitState.OPEN

    def protect(self, fallback: Any = None):
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await self.call(func, *args, fallback=fallback, **kwargs)
            return wrapper
        return decorator

    def status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout,
        }