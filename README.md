# Super Base Orchestration System

超级基座调度系统 — 以基座模型为中央大脑，动态调度多业务模块的可插拔架构。

## 快速启动

### 方式一：本地开发

```bash
# 1. 创建 conda 环境
conda create -n super-base python=3.11 -y
conda activate super-base

# 2. 安装依赖
pip install pydantic fastapi uvicorn httpx anthropic pyyaml python-dotenv redis pytest

# 3. 安装本地包
pip install -e packages/sdk-python -e gateway -e modules/echo -e modules/weather -e modules/code-review

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API_KEY

# 5. 启动服务（4 个终端窗口）
uvicorn app.main:app --port 8000          # Gateway
uvicorn modules.echo.main:app --port 8001 # Echo 模块
uvicorn modules.weather.main:app --port 8002 # Weather 模块
uvicorn modules.code_review.main:app --port 8003 # Code Review 模块
```

### 方式二：Docker Compose

```bash
docker compose up --build
```

## 验证

```bash
# 健康检查
curl http://localhost:8000/health

# 测试 Echo
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'

# 测试天气
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"message": "北京天气"}'

# 测试代码审查
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我审查代码"}'

# SSE 流式
curl -N -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"message": "echo test", "options": {"stream": true}}'

# 查看已注册模块
curl http://localhost:8000/api/v1/modules

# 模块健康检查
curl http://localhost:8000/api/v1/modules/health

# 熔断器状态
curl http://localhost:8000/api/v1/circuit-breaker

# 死信队列
curl http://localhost:8000/api/v1/dlq
```

## 运行测试

```bash
# 单元测试（32 条）
pytest tests/ -v

# 意图识别评估（13 条，Mock 模式）
INTENT_MODE=mock python evaluations/runners/intent_eval.py

# 意图识别评估（Cloud 模式，需要 API Key）
INTENT_MODE=cloud python evaluations/runners/intent_eval.py
```

## 项目结构

```
super-base-system/
├── proto/module/v1/              # gRPC 协议定义
├── packages/sdk-python/          # Python SDK (schemas/server/manifest)
├── gateway/app/                  # 调度层核心
│   ├── api/chat.py               # REST API 端点
│   ├── intent/                   # 意图识别 + 复杂度分级
│   ├── planner/                  # DAG 任务编排
│   ├── executor/                 # DAG 状态机执行引擎
│   ├── dispatcher/               # HTTP 模块调度器
│   ├── session/                  # 会话管理
│   ├── transport/                # NATS + SSE 传输层
│   ├── resilience/               # 熔断器 + 死信队列
│   └── prompts/                  # Prompt 模板
├── modules/
│   ├── echo/                     # Echo 回显模块 (port 8001)
│   ├── weather/                  # 天气查询模块 (port 8002)
│   └── code-review/              # 代码审查模块 (port 8003)
├── evaluations/                  # 评估数据集 + 运行器
├── tests/                        # 单元测试 + E2E 测试
└── docker-compose.yaml           # Docker 一键部署
```

## 意图识别模式

| 模式 | 配置 | 说明 |
|------|------|------|
| Mock | `INTENT_MODE=mock` | 规则匹配，零延迟，用于开发调试 |
| Cloud | `INTENT_MODE=cloud` | 调用 mimo-v2.5-pro LLM，真实意图识别 |

## 运维 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | Gateway 健康检查 |
| `/api/v1/modules` | GET | 已注册模块列表 |
| `/api/v1/modules/health` | GET | 模块健康状态 |
| `/api/v1/circuit-breaker` | GET | 熔断器状态 |
| `/api/v1/circuit-breaker/{id}/reset` | POST | 重置熔断器 |
| `/api/v1/dlq` | GET | 死信队列 |
| `/api/v1/dlq/{id}/replay` | POST | 重放死信任务 |
| `/api/v1/plan/dag` | POST | 手动创建 DAG |
| `/api/v1/chat/completions` | POST | 核心调度接口 |
| `/api/v1/sessions/{id}/human-callback` | POST | 人工介入回调 |

## 技术文档

- [技术方案](super-base-orchestration-system.md)
- [落地实施策略](super-base-implementation-strategy.md)
- [项目构建难点解析](项目构建难点解析.md)
- [优化机制](优化机制.md)
