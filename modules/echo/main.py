"""Echo module: LLM-powered conversational echo with context awareness."""
from superbase_sdk import ModuleServer, TaskRequest, TaskResponse, LLMClient

server = ModuleServer("echo", "0.2.0")
llm = LLMClient()


@server.execute
async def handle(req: TaskRequest) -> TaskResponse:
    # 判断是否有对话历史（有则做上下文感知回复，无则简单回应）
    history = req.context.get("conversation_history", [])

    if history:
        # 有上下文：用 LLM 生成有上下文感知的回复
        history_text = "\n".join(
            f"[{m['role']}] {m['content']}" for m in history[-6:]
        )
        prompt = (
            f"基于以下对话历史，对用户的最新消息给出简洁有帮助的回复。\n\n"
            f"对话历史：\n{history_text}\n\n"
            f"用户最新消息：{req.query}\n\n"
            f"请直接给出回复，不要重复用户的问题。"
        )
        summary = await llm.complete(prompt, max_tokens=512, temperature=0.7)
    else:
        # 无上下文：简单回应
        prompt = f"对以下消息给出简洁友好的回复：\n{req.query}"
        summary = await llm.complete(prompt, max_tokens=256, temperature=0.7)

    return TaskResponse(
        task_id=req.task_id,
        status="completed",
        summary=summary,
        output_payload={
            "original_query": req.query,
            "has_context": bool(history),
            "history_turns": len(history) // 2 if history else 0,
        },
    )


app = server.app

if __name__ == "__main__":
    server.run(port=8001)
