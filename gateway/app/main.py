from __future__ import annotations

from fastapi import FastAPI

from .api.chat import router as chat_router
from .registry.store import ModuleRegistry

app = FastAPI(
    title="Super Base Gateway",
    version="0.1.0",
    description="超级基座调度系统 - 调度层",
)

# 全局 Module Registry（启动时从 manifest 文件加载）
registry = ModuleRegistry()


@app.on_event("startup")
async def startup():
    registry.load_from_directory()


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "registered_modules": [
            m.module_id for m in registry.list_all()
        ],
    }


app.include_router(chat_router, prefix="/api/v1")
