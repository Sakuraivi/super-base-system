# 超级基座调度系统 — 工程化落地实施策略

> 基于技术方案 v1.0 的工程化实施思路
> 最后更新：2026-05-19

---

## 核心策略：自底向上验证，而非自顶向下铺开

核心假设：**基座模型能否可靠地将自然语言映射到正确的模块 + 正确的参数？**

如果这个假设不成立，后续所有 DAG 编排、消息总线、记忆系统都是空中楼阁。

---

## 实施进度总览

```
Phase 1: MVP（Step 0-1）               ██████████ 100%  ✅ 已完成
Phase 2: 功能完善（Step 2-3）           ██████████ 100%  ✅ 已完成
Phase 3: 生产级加固（Step 4-5）         ██████████ 100%  ✅ 已完成
```

---

## Phase 1：MVP（Step 0-1）✅ 已完成

### 交付物

| 组件 | 说明 | 状态 |
|------|------|------|
| 接口协议 | gRPC Proto + Pydantic schemas + Module Manifest JSON Schema | ✅ |
| Python SDK | `packages/sdk-python/`：schemas、manifest parser、ModuleServer 基类 | ✅ |
| Gateway 核心 | FastAPI + Intent Router（mock/cloud 双模式）+ Registry + Dispatcher + Session Manager | ✅ |
| 示例模块 | echo(8001) + weather(8002)，各带 manifest | ✅ |
| Docker Compose | 一键部署 | ✅ |
| 测试 | 12 单元测试 + 10 意图评估 + E2E 全链路 | ✅ |
| 意图识别 | mimo-v2.5-pro 通过 Anthropic API，准确率 100% | ✅ |

### 验收结果

- Mock 模式意图评估：10/10 通过
- Cloud 模式（mimo-v2.5-pro）：10/10 通过
- E2E 全链路：Gateway → Registry → Dispatcher → Module → Response 全部打通

---

## Phase 2：功能完善（Step 2-3）🟡 核心完成

### 已完成项

| 组件 | 说明 | 状态 |
|------|------|------|
| 复杂度分级器 | 自动判断 simple/pipeline/dag，路由到对应模型 | ✅ |
| Task Planner | 串行 pipeline、并行 fan-out/fan-in DAG 生成 | ✅ |
| DAG Executor | 拓扑排序状态机、barrier 并行、指数退避重试 | ✅ |
| SSE 流式输出 | plan_created → node_started/completed → done 全链路 | ✅ |
| NATS JetStream | 异步消息总线封装，不可用时自动降级 HTTP | ✅ |
| Code Review 模块 | 新模块(8003)，3 个 intent，演示多模块调度 | ✅ |
| 熔断器 | 三态（CLOSED/OPEN/HALF_OPEN），按模块独立管理 | ✅ |
| 死信队列 | 失败任务追踪、按模块过滤、支持重放 | ✅ |
| 全局降级 | 所有模块失败时返回友好提示 | ✅ |
| 模块健康检查 | /api/v1/modules/health 端点 | ✅ |
| 运维 API | 熔断器状态/重置、DLQ 查看/重放 | ✅ |
| 测试 | 32 单元测试 + 13 意图评估 + Phase 2 E2E | ✅ |
| **人工介入节点** | human_gate 节点暂停/恢复、超时策略、approve/reject/modify | ✅ |
| **条件分支执行** | ConditionEvaluator（ast 安全求值）+ 分支跳过 | ✅ |
| **PostgreSQL 持久化** | Session、Message、DeadLetter → PG + 内存 fallback | ✅ |
| **向量记忆** | Qdrant LTM + Embedding + RAG + Reranker + 智能晋升 | ✅ |

---

## Phase 3：生产级加固（Step 4-5）✅ 已完成

### P3-1 记忆子系统 ✅

| 组件 | 说明 | 状态 |
|------|------|------|
| 短期记忆（Redis） | 会话历史、滑动窗口、token 预算、TTL 过期 | ✅ |
| 长期记忆（Qdrant） | 用户画像、任务知识、跨会话语义检索 | ✅ |
| Embedding Pipeline | MockEmbeddingClient（可替换真实模型）+ TextChunker | ✅ |
| RAG 检索 | Reranker 混合评分 + IntentFilter 意图过滤 + 去重 | ✅ |
| 记忆晋升/淘汰 | 智能晋升（长度+关键词）、会话摘要 | ✅ |

### P3-2 多租户隔离 ✅

| 组件 | 说明 | 状态 |
|------|------|------|
| 数据隔离 | PostgreSQL tenant_id 列 + 索引（RLS ready） | ✅ |
| 租户识别 | X-Tenant-ID 请求头 + TenantMiddleware | ✅ |
| LTM 隔离 | Qdrant tenant_id filter | ✅ |
| 资源限流 | 滑动窗口 RateLimiter（60 req/60s per tenant） | ✅ |

### P3-3 可观测性 ✅

| 组件 | 说明 | 状态 |
|------|------|------|
| 分布式追踪 | OpenTelemetry 全链路 trace（Console + OTLP） | ✅ |
| 指标监控 | Prometheus `/metrics` 端点，10 个指标 | ✅ |
| 结构化日志 | JSON 格式 + request_id 关联 | ✅ |
| 请求中间件 | 耗时 + 状态码 + tenant_id | ✅ |

### P3-4 K8s 生产部署 ✅

| 组件 | 说明 | 状态 |
|------|------|------|
| Helm Charts | 一键部署全栈（含 PostgreSQL/Redis/Qdrant 子图表） | ✅ |
| HPA | CPU/Memory 双指标自动扩缩容（2-10 replicas） | ✅ |
| PDB | Pod Disruption Budget（minAvailable: 1） | ✅ |
| Ingress | 可选 NGINX Ingress | ✅ |

### P3-5 安全加固

| 组件 | 说明 |
|------|------|
| Prompt 注入防护 | 输入净化 + Prompt 隔离 + 输出审计 |
| mTLS 模块鉴权 | 模块间双向认证 |
| RBAC | 角色权限控制 |
| 审计日志 | 全操作记录，90 天保留 |

---

## 与技术方案（v1.0）的关键差异

| 方面 | 技术方案 | 实际落地 |
|------|----------|----------|
| **模型选型** | Claude Opus / GPT-4o | mimo-v2.5-pro（小米 MiMo） |
| **MVP 范围** | 6 周，含 Docker Compose + CI/CD | 2 个会话完成，先验证核心假设 |
| **消息总线** | Phase 1 就用 NATS | Phase 1 同步 HTTP，Phase 2 加 NATS（降级模式） |
| **Module Registry** | Phase 1 用 Redis | 内存 dict + manifest 文件扫描 |
| **容错机制** | 技术方案未详细展开 | 独立实现了熔断器 + DLQ + 全局降级（超出原方案） |
| **记忆晋升** | LLM 评估（Haiku） | 待实现（计划初期用规则，后期加 LLM） |

---

## 测试策略

| 测试层级 | 覆盖范围 | 当前状态 |
|----------|----------|----------|
| 单元测试 | Intent、Session、Registry、DAG、Complexity、Resilience | 32 条 ✅ |
| 意图评估 | Mock + Cloud 模式，13 条标注数据 | ✅ |
| E2E 测试 | 完整请求链路、DAG 调度、SSE 流式 | ✅ |
| 集成测试 | 消息总线、数据库读写 | ⬜ 待实现 |
| 性能测试 | 并发吞吐、延迟分布 | ⬜ 待实现 |
| 混沌工程 | 模块宕机、网络分区 | ⬜ 待实现 |
| 安全测试 | Prompt 注入、越权访问 | ⬜ 待实现 |

---

## 项目仓库

- GitHub: https://github.com/Sakuraivi/super-base-system
- Conda 环境: `super-base` (Python 3.11)
- 意图识别模型: mimo-v2.5-pro (小米 MiMo, Anthropic API)
