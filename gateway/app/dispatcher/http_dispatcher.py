from __future__ import annotations

from typing import Any

import httpx

from superbase_sdk.schemas import ModuleManifest


class HttpDispatcher:
    """通过 HTTP 同步调用业务模块，支持可配置超时。"""

    def __init__(self, default_timeout: float = 60.0):
        self._client = httpx.AsyncClient(timeout=default_timeout)

    async def dispatch(
        self, module: ModuleManifest, task_request: dict[str, Any]
    ) -> dict[str, Any]:
        url = f"http://localhost:{module.port}/execute"
        timeout = float(module.timeout_seconds)

        try:
            resp = await self._client.post(url, json=task_request, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            return {
                "task_id": task_request.get("task_id", ""),
                "status": "failed",
                "summary": f"模块 {module.module_id} 执行超时（{timeout}s）",
            }
        except httpx.ConnectError:
            return {
                "task_id": task_request.get("task_id", ""),
                "status": "failed",
                "summary": f"模块 {module.module_id} 无法连接（端口 {module.port} 未监听）",
            }
        except httpx.HTTPStatusError as e:
            return {
                "task_id": task_request.get("task_id", ""),
                "status": "failed",
                "summary": f"模块 {module.module_id} 返回 HTTP {e.response.status_code}",
            }
        except Exception as e:
            return {
                "task_id": task_request.get("task_id", ""),
                "status": "failed",
                "summary": f"模块 {module.module_id} 调用异常: {type(e).__name__}: {e}",
            }

    async def health_check(self, module: ModuleManifest) -> bool:
        """检查模块是否存活。"""
        try:
            resp = await self._client.get(
                f"http://localhost:{module.port}/health",
                timeout=5.0,
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self._client.aclose()
