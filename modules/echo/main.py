from superbase_sdk import ModuleServer, TaskRequest, TaskResponse

server = ModuleServer("echo", "0.1.0")


@server.execute
async def handle(req: TaskRequest) -> TaskResponse:
    return TaskResponse(
        task_id=req.task_id,
        status="completed",
        summary=f"Echo: {req.query}",
        output_payload={
            "original_query": req.query,
            "context_received": req.context,
        },
    )


app = server.app

if __name__ == "__main__":
    server.run(port=8001)
