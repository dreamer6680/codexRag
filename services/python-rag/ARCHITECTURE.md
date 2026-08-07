# Python RAG 服务设计

该服务参考 HelloAgents 的分层方式，但按当前仓库已有的 FastAPI、LangGraph、
Ollama、Qdrant 和 MinerU 组件做了收敛。

```text
API / 编排层
├── main.py               FastAPI 接口、健康检查
├── graph.py              检索 → 证据门控 → 生成/拒答
└── pipeline.py           文档入库与检索的统一门面

文档处理层
├── models.Document       标准文档与元数据
└── DocumentProcessor     文本归一化、重叠切块；复杂格式交给 MinerU

嵌入表示层
├── BaseEmbedding         可替换的统一接口
└── OllamaEmbedding       当前本地实现（bge-m3）

检索与上下文层
├── MultiStrategyRetriever 向量、MQE、HyDE、混合检索与 RRF 融合
└── ContextBuilder          去重、编号、字符预算截断

存储与模型适配层
├── VectorStore           Qdrant 集合、命名过滤、可信度过滤
└── OllamaClient          模型发现、生成、嵌入
```

## 请求流程

1. `/rag/index` 接收切块数据，通过统一嵌入接口生成向量并写入 Qdrant。
2. `/rag/query` 根据 `strategy` 生成一个或多个检索查询。
3. 多路结果使用 Reciprocal Rank Fusion 去重与排序。
4. `ContextBuilder` 在上下文预算内组装证据。
5. 没有证据时直接拒答；有证据时才调用 Ollama，并返回引用。

## 与记忆系统的边界

RAG 知识库保存经过审核、可引用的文档事实；记忆系统保存会话工作状态、用户事件和
抽象语义关系。两者共享 `BaseEmbedding`，未来可共享 Qdrant 客户端，但应使用不同集合
或租户命名空间，避免会话记忆污染正式知识库。

推荐后续按需求增加：

- `DashScopeEmbedding`、`LocalTransformerEmbedding` 和 `TFIDFEmbedding` 适配器；
- SQLite 文档元数据与版本状态，保证旧版本向量可追踪和删除；
- Neo4j 图谱检索，作为混合检索的另一条召回通道；
- 真正的 reranker 服务。目前实现的是多路召回融合，配置中的 rerank 模型尚未接入打分；
- 租户字段与 Qdrant payload 强制过滤，用于生产环境数据隔离。

## 配置

所有配置均可通过环境变量覆盖，主要包括：

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `RETRIEVAL_STRATEGY` | `vector` | 默认检索策略 |
| `RETRIEVAL_TOP_K` | `12` | 最终召回数量 |
| `RETRIEVAL_SCORE_THRESHOLD` | `0.35` | Qdrant 相似度门槛 |
| `CONTEXT_MAX_CHARS` | `12000` | 发送给生成模型的最大证据字符数 |
| `RAG_HOST` / `RAG_PORT` | `127.0.0.1` / `8001` | API 监听地址 |

生产环境应优先使用 `vector` 或 `hybrid`，并在自己的文档集上评测阈值。MQE/HyDE
会增加模型调用次数与延迟，在 Ollama 不可用时会自动降级为普通向量检索。
