from __future__ import annotations

from typing import Any, Callable, Awaitable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .schemas import TaskRequest, TaskResponse, HealthResponse, Artifact


ExecuteFunc = Callable[[TaskRequest], Awaitable[TaskResponse]]


class ModuleServer:
    """业务模块标准化 FastAPI Server 基类。

    用法:
        server = ModuleServer("echo", "0.1.0")

        @server.execute
        async def handle(req: TaskRequest) -> TaskResponse:
            return TaskResponse(task_id=req.task_id, status="completed", summary="done")

        server.run(port=8001)
    """

    def __init__(self, module_id: str, version: str = "0.1.0"):
        self.module_id = module_id
        self.version = version
        self.app = FastAPI(title=module_id, version=version)
        self._execute_fn: ExecuteFunc | None = None
        self._register_routes()

    def _register_routes(self) -> None:
        @self.app.get("/health")
        async def health():
            return HealthResponse(
                status="healthy",
                version=self.version,
                details={"module_id": self.module_id},
            ).model_dump()

        @self.app.post("/execute")
        async def execute(req: TaskRequest):
            if self._execute_fn is None:
                return JSONResponse(
                    status_code=501,
                    content={"error": "No execute handler registered"},
                )
            try:
                result = await self._execute_fn(req)
                return result.model_dump()
            except Exception as e:
                return TaskResponse(
                    task_id=req.task_id,
                    status="failed",
                    summary=f"Module error: {e}",
                ).model_dump()

    def execute(self, fn: ExecuteFunc) -> ExecuteFunc:
        """装饰器：注册任务执行处理函数。"""
        self._execute_fn = fn
        return fn

    def run(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)
