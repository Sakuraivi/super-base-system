import random
from superbase_sdk import ModuleServer, TaskRequest, TaskResponse, Artifact

server = ModuleServer("code_review", "0.1.0")

# Mock 代码审查结果
MOCK_FINDINGS = [
    {"severity": "high", "file": "auth.py", "line": 42, "message": "Potential SQL injection: string concatenation used in query", "suggestion": "Use parameterized queries"},
    {"severity": "medium", "file": "api/routes.py", "line": 15, "message": "Missing input validation on user_id parameter", "suggestion": "Add Pydantic schema validation"},
    {"severity": "low", "file": "utils.py", "line": 88, "message": "Unused import: os.path", "suggestion": "Remove unused import"},
    {"severity": "medium", "file": "db/models.py", "line": 23, "message": "N+1 query detected in get_user_posts()", "suggestion": "Use selectinload or joinedload"},
    {"severity": "high", "file": "auth.py", "line": 67, "message": "Hardcoded API key in source code", "suggestion": "Move to environment variables"},
]


@server.execute
async def handle(req: TaskRequest) -> TaskResponse:
    # Mock: 随机选取 2-4 个 findings
    count = random.randint(2, 4)
    findings = random.sample(MOCK_FINDINGS, min(count, len(MOCK_FINDINGS)))
    high_count = sum(1 for f in findings if f["severity"] == "high")

    summary = f"代码审查完成，发现 {len(findings)} 个问题（{high_count} 个高危）"
    if high_count > 0:
        summary += "，建议优先修复高危问题"

    return TaskResponse(
        task_id=req.task_id,
        status="completed",
        summary=summary,
        output_payload={
            "findings": findings,
            "total_issues": len(findings),
            "high_severity": high_count,
            "medium_severity": sum(1 for f in findings if f["severity"] == "medium"),
            "low_severity": sum(1 for f in findings if f["severity"] == "low"),
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
