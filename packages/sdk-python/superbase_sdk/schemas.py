from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Task 交互模型 ──────────────────────────────────────────────────

class TaskConfig(BaseModel):
    timeout_seconds: int = 120
    streaming: bool = False
    priority: str = "normal"  # normal | high | critical
    metadata: dict[str, str] = Field(default_factory=dict)


class TaskRequest(BaseModel):
    task_id: str
    query: str
    context: dict[str, str] = Field(default_factory=dict)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    config: TaskConfig = Field(default_factory=TaskConfig)


class Artifact(BaseModel):
    type: str  # report | file | image | code_patch
    name: str
    url: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    task_id: str
    status: str  # completed | failed | partial
    output_payload: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    artifacts: list[Artifact] = Field(default_factory=list)


class TaskEvent(BaseModel):
    task_id: str
    event_type: str  # progress | token | completed | error
    data: dict[str, Any] = Field(default_factory=dict)


# ── 健康检查 ──────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "healthy"  # healthy | degraded | unhealthy
    version: str = "0.1.0"
    details: dict[str, str] = Field(default_factory=dict)


# ── Module Manifest 模型 ──────────────────────────────────────────

class ModuleCapability(BaseModel):
    intent: str
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    example_queries: list[str] = Field(default_factory=list)


class ModuleManifest(BaseModel):
    module_id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    capabilities: list[ModuleCapability] = Field(default_factory=list)
    protocol: str = "http"  # http | grpc
    port: int = 8000
    health_check_path: str = "/health"
    timeout_seconds: int = 120
    supports_streaming: bool = False


# ── Intent 识别结果 ────────────────────────────────────────────────

class Complexity(str, Enum):
    SINGLE = "single"
    PIPELINE = "pipeline"
    DAG = "dag"


class IntentResult(BaseModel):
    module_id: str
    confidence: float = 0.0
    query: str = ""
    entities: dict[str, Any] = Field(default_factory=dict)
    complexity: Complexity = Complexity.SINGLE
    reasoning: str = ""
