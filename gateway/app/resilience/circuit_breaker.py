"""熔断器：防止持续调用不可用的模块。

三态：CLOSED（正常）→ OPEN（熔断，拒绝调用）→ HALF_OPEN（试探恢复）
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"        # 正常：允许调用
    OPEN = "open"            # 熔断：拒绝调用
    HALF_OPEN = "half_open"  # 试探：允许少量调用


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5        # 连续失败 N 次触发熔断
    recovery_timeout: float = 30.0    # 熔断后等待 N 秒进入半开
    half_open_max_calls: int = 1      # 半开状态允许的试探调用数

    _state: CircuitState = field(default=CircuitState.CLOSED)
    _failure_count: int = field(default=0)
    _last_failure_time: float = field(default=0.0)
    _half_open_calls: int = field(default=0)

    def allow_request(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # 检查是否到了恢复时间
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                return True
            return False

        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

        return False

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._half_open_calls = 0

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count


class CircuitBreakerRegistry:
    """模块级熔断器注册表。"""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(self, module_id: str) -> CircuitBreaker:
        if module_id not in self._breakers:
            self._breakers[module_id] = CircuitBreaker()
        return self._breakers[module_id]

    def get_state(self, module_id: str) -> CircuitState:
        return self.get_or_create(module_id).state

    def reset(self, module_id: str) -> None:
        self._breakers.pop(module_id, None)
