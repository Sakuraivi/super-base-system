from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.responses import Response


class SSEManager:
    """SSE 流式推送管理器。"""

    @staticmethod
    def create_stream_response(generator):
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @staticmethod
    def format_event(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def format_done() -> str:
        return "event: done\ndata: [DONE]\n\n"
