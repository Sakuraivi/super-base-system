"""Code Review module: LLM-powered code analysis."""
import json
from superbase_sdk import ModuleServer, TaskRequest, TaskResponse, Artifact, LLMClient

server = ModuleServer("code_review", "0.2.0")
llm = LLMClient()

SYSTEM_PROMPT = """你是一个专业的代码审查专家。请分析用户提供的代码或代码描述，返回 JSON 格式的审查结果。

输出格式：
{
  "findings": [
    {"severity": "high|medium|low", "file": "文件名", "line": 行号, "message": "问题描述", "suggestion": "修复建议"}
  ],
  "summary": "一句话总结"
}

重点关注：安全漏洞、性能问题、代码规范、潜在 bug、可维护性。
如果用户没有提供具体代码，根据描述分析可能的问题。"""


@server.execute
async def handle(req: TaskRequest) -> TaskResponse:
    prompt = (
        f"请对以下代码/需求进行代码审查：\n\n"
        f"{req.query}\n\n"
        f"返回 JSON 格式的审查结果。"
    )

    try:
        result = await llm.complete_json(prompt, system=SYSTEM_PROMPT, max_tokens=2048)
        findings = result.get("findings", [])
        llm_summary = result.get("summary", "")
    except (json.JSONDecodeError, Exception) as e:
        # LLM 返回非 JSON 时降级
        text = await llm.complete(prompt, system=SYSTEM_PROMPT, max_tokens=1024)
        findings = []
        llm_summary = text

    high_count = sum(1 for f in findings if f.get("severity") == "high")
    summary = llm_summary or f"代码审查完成，发现 {len(findings)} 个问题（{high_count} 个高危）"

    return TaskResponse(
        task_id=req.task_id,
        status="completed",
        summary=summary,
        output_payload={
            "findings": findings,
            "total_issues": len(findings),
            "high_severity": high_count,
            "medium_severity": sum(1 for f in findings if f.get("severity") == "medium"),
            "low_severity": sum(1 for f in findings if f.get("severity") == "low"),
        },
        artifacts=[
            Artifact(
                type="report",
                name="code_review_report.md",
                metadata={"format": "markdown"},
            )
        ],
    )


app = server.app

if __name__ == "__main__":
    server.run(port=8003)
