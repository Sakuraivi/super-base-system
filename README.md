# Super Base Orchestration System

超级基座调度系统 — 以基座模型为中央大脑，动态调度多业务模块的可插拔架构。

## 系统能力

| 能力 | 说明 |
|------|------|
| **DAG 编排** | 串行/并行/条件分支任务编排，拓扑排序状态机执行 |
| **意图识别** | mimo-v2.5-pro LLM 意图分类 + 复杂度分级，准确率 100% |
| **容错** | 熔断器（三态）+ 死信队列 + 指数退避重试 + 全局降级 |
| **条件分支** | 基于 `ast` 的安全表达式求值，支持 `==` `>` `in` `contains` `and/or/not` |
| **人工介入** | Human Gate 暂停/恢复 + 超时策略 + approve/reject/modify 回调 |
| **记忆系统** | STM（Redis 滑动窗口）+ LTM（Qdrant 向量检索）+ Reranker + 智能晋升 |
| **持久化** | PostgreSQL（sessions/messages/dead_letters）+ 内存 fallback |
| **可观测性** | OpenTelemetry 追踪 + Prometheus `/metrics` + JSON 结构化日志 |
| **多租户** | `X-Tenant-ID` 隔离 + 滑动窗口限流 + DB/LTM tenant 过滤 |
| **LLM 模块** | Echo 上下文感知 / Weather 天气分析 / Code Review 代码审查 |
| **K8s 部署** | Helm Chart（Deployment + HPA + PDB + Ingress）|

## 快速启动

### 方式一：Docker Compose（推荐）

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API_KEY

# 2. 启动全栈（Gateway + PostgreSQL + Redis + Qdrant + 3 模块）
docker compose up --build
```

### 方式二：本地开发

```bash
# 1. 安装依赖
pip install -e packages/sdk-python -e gateway
pip install -e modules/echo -e modules/weather -e modules/code-review

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API_KEY

# 3. 启动服务（4 个终端窗口）
cd gateway && uvicorn app.main:app --port 8000
cd modules/echo && uvicorn main:app --port 8001
cd modules/weather && uvicorn main:app --port 8002
cd modules/code-review && uvicorn main:app --port 8003
```

> 无 PostgreSQL/Redis/Qdrant 时自动降级到内存模式（开发测试不受影响）。

### 方式三：Kubernetes

```bash
cd deploy/helm/superbase-gateway
helm dependency update .
helm install superbase . --set API_KEY=your-key
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `API_BASE_URL` | Anthropic 代理地址 | LLM API 端点 |
| `API_KEY` | - | LLM API Key |
| `MODEL_NAME` | `mimo-v2.5-pro` | 主模型 |
| `INTENT_MODE` | `mock` | 意图识别模式：`mock` / `cloud` |
| `DATABASE_URL` | 空 | PostgreSQL 连接串（空则内存 fallback） |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |
| `QDRANT_HOST` | `localhost` | Qdrant 主机 |
| `QDRANT_PORT` | `6333` | Qdrant 端口 |
| `STM_WINDOW_SIZE` | `10` | 短期记忆滑动窗口轮数 |
| `STM_MAX_TOKENS` | `2000` | 短期记忆 token 预算 |
| `LTM_EMBEDDING_DIMENSION` | `384` | 向量维度 |
| `LTM_CHUNK_SIZE` | `512` | 文本分块大小 |
| `LTM_SEARCH_TOP_K` | `5` | LTM 检索返回数 |
| `GATEWAY_HOST` | `0.0.0.0` | 监听地址 |
| `GATEWAY_PORT` | `8000` | 监听端口 |

## API 接口

### 核心接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/chat/completions` | POST | 核心调度接口（支持 SSE 流式） |
| `/api/v1/modules` | GET | 已注册模块列表 |
| `/api/v1/plan/dag` | POST | 手动创建 DAG 执行计划 |
| `/api/v1/sessions/{id}/human-callback` | POST | 人工介入回调（approve/reject/modify） |

### 运维接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/metrics` | GET | Prometheus 指标 |
| `/api/v1/modules/health` | GET | 模块健康状态 |
| `/api/v1/circuit-breaker` | GET | 熔断器状态 |
| `/api/v1/circuit-breaker/{id}/reset` | POST | 重置熔断器 |
| `/api/v1/dlq` | GET | 死信队列 |
| `/api/v1/dlq/{id}/replay` | POST | 重放死信任务 |

### 请求头

| 头 | 说明 |
|------|------|
| `X-Tenant-ID` | 租户标识（默认 `default`） |
| `X-Request-ID` | 请求追踪 ID（自动生成） |

### 响应头

| 头 | 说明 |
|------|------|
| `X-Tenant-ID` | 租户标识 |
| `X-Request-ID` | 请求追踪 ID |
| `X-RateLimit-Remaining` | 当前窗口剩余请求数 |

## 验证

```bash
# 健康检查
curl http://localhost:8000/health

# 测试 Echo（LLM 上下文感知回复）
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'

# 测试天气（LLM 天气分析）
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"message": "北京天气怎么样"}'

# 测试代码审查（LLM 代码分析）
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我审查这段代码：def foo(): return 1/0"}'

# 多租户（指定租户）
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: acme" \
  -d '{"message": "hello"}'

# SSE 流式
curl -N -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"message": "echo test", "options": {"stream": true}}'

# Prometheus 指标
curl http://localhost:8000/metrics
```

## 运行测试

```bash
# 全量测试（161 条）
pytest tests/ -v

# 意图识别评估（13 条）
INTENT_MODE=mock python evaluations/runners/intent_eval.py
```

## 项目结构

```
super-base-system/
├── gateway/app/                  # 调度层核心
│   ├── api/chat.py               # REST API 端点
│   ├── intent/                   # 意图识别 + 复杂度分级
│   ├── planner/                  # DAG 任务编排 + 条件表达式求值
│   ├── executor/                 # DAG 状态机执行引擎
│   ├── dispatcher/               # HTTP 模块调度器
│   ├── session/                  # 会话管理（内存 + PG）
│   ├── memory/                   # 记忆子系统
│   │   ├── stm.py                # 短期记忆（滑动窗口）
│   │   ├── redis_stm.py          # Redis STM 实现
│   │   ├── ltm.py                # 长期记忆（向量检索）
│   │   ├── embedding.py          # Embedding 客户端
│   │   ├── chunker.py            # 文本分块器
│   │   ├── rag.py                # Reranker + IntentFilter
│   │   ├── manager.py            # 统一记忆管理器
│   │   └── factory.py            # 工厂（Redis/Qdrant/内存）
│   ├── db/                       # 数据库层
│   │   ├── engine.py             # SQLAlchemy async engine
│   │   ├── models.py             # ORM models（RLS ready）
│   │   └── factory.py            # Session/DLQ 工厂
│   ├── tenant/                   # 多租户
│   │   └── middleware.py         # TenantMiddleware + RateLimiter
│   ├── observability/            # 可观测性
│   │   ├── tracing.py            # OpenTelemetry 初始化
│   │   └── metrics.py            # Prometheus 指标定义
│   ├── resilience/               # 熔断器 + 死信队列
│   └── transport/                # NATS + SSE 传输层
├── packages/sdk-python/          # Python SDK
│   ├── superbase_sdk/            # schemas + server + LLMClient
├── modules/
│   ├── echo/                     # Echo 模块 (port 8001, LLM)
│   ├── weather/                  # 天气模块 (port 8002, LLM)
│   └── code-review/              # 代码审查模块 (port 8003, LLM)
├── deploy/helm/                  # Helm Charts
│   └── superbase-gateway/        # Gateway Helm Chart（HPA + PDB）
├── evaluations/                  # 评估数据集 + 运行器
├── tests/                        # 161 条测试
└── docker-compose.yaml           # Docker 一键部署
```

## 意图识别模式

| 模式 | 配置 | 说明 |
|------|------|------|
| Mock | `INTENT_MODE=mock` | 规则匹配，零延迟，用于开发调试 |
| Cloud | `INTENT_MODE=cloud` | 调用 mimo-v2.5-pro LLM，真实意图识别 |

## Prometheus 指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `http_requests_total` | Counter | HTTP 请求总数 |
| `http_request_duration_seconds` | Histogram | 请求耗时 |
| `intent_classify_duration_seconds` | Histogram | 意图识别耗时 |
| `dag_execute_duration_seconds` | Histogram | DAG 执行耗时 |
| `dag_node_status_total` | Counter | 节点状态统计 |
| `module_dispatch_duration_seconds` | Histogram | 模块调用耗时 |
| `module_dispatch_errors_total` | Counter | 模块调用错误 |
| `memory_recall_duration_seconds` | Histogram | 记忆召回耗时 |
| `memory_promote_total` | Counter | LTM 晋升次数 |

## 技术文档

- [技术方案](super-base-orchestration-system.md)
- [落地实施策略](super-base-implementation-strategy.md)
- [项目构建难点解析](项目构建难点解析.md)
- [优化机制](优化机制.md)
