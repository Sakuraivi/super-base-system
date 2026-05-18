from __future__ import annotations

from typing import Any

import httpx

from superbase_sdk.schemas import ModuleManifest


class HttpDispatcher:
    """通过 HTTP 同步调用业务模块。"""

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=120.0)

    async def dispatch(
        self, module: ModuleManifest, task_request: dict[str, Any]
    ) -> dict[str, Any]:
        url = f"http://localhost:{module.port}/execute"
        try:
            resp = await self._client.post(url, json=task_request)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            return {
                "task_id": task_request.get("task_id", ""),
                "status": "failed",
                "summary": f"模块 {module.module_id} 执行超时",
            }
        except httpx.HTTPStatusError as e:
            return {
                "task_id": task_request.get("task_id", ""),
                "status": "failed",
                "summary": f"模块 {module.module_id} 返回错误: {e.response.status_code}",
            }
        except Exception as e:
            return {
                "task_id": task_request.get("task_id", ""),
                "status": "failed",
                "summary": f"模块 {module.module_id} 调用失败: {e}",
            }

    async def close(self):
        await self._client.aclose()
