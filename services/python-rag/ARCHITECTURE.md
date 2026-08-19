# Python RAG 服务设计

该服务参考 HelloAgents 的分层方式，但按当前仓库已有的 FastAPI、LangGraph、
Ollama、Qdrant 和 MinerU 组件做了收敛。

```text
API / 编排层
├── main.py               FastAPI 接口、健康检查
├── graph.py              检索 → 证据门控 → 生成/拒答
└── pipeline.py           文档入库与检索的统一门面

文档处理层
├── layout_parser         PDF 坐标提取、栏位检测与阅读顺序重建
├── markdown_parser       Markdown/TXT 标题、列表、表格结构解析
├── resume_enricher       公司、岗位、项目、职责关系增强
├── structure_chunker     语义单元切块与父级上下文继承
└── ingestion             原始文件解析、索引和版本重建编排

嵌入表示层
├── BaseEmbedding         可替换的统一接口
└── OllamaEmbedding       当前本地实现（bge-m3）

检索与上下文层
├── LexicalRetriever       用户范围内的 BM25、精确实体和关系召回
├── MultiStrategyRetriever 向量/关键词双路召回与 RRF 融合
├── EvidencePolicy         实体、关系、解析质量和向量分综合门控
└── ContextBuilder          去重、编号、字符预算截断

存储与模型适配层
├── VectorStore           Qdrant 集合、命名过滤、可信度过滤
└── OllamaClient          模型发现、生成、嵌入
```

## 请求流程

1. `/rag/upload` 保存原文件。文本 PDF 直接读取文字坐标，扫描型 PDF 才调用 MinerU。
2. 解析器统一输出标题、段落、列表、表格、页码和坐标；简历增强器进一步形成“公司—岗位—项目—职责”单元。
3. 结构切块器只在语义边界拆分，拆分后的子块重复必要父级关系。
4. 索引同时保存稠密向量、关键词、实体、章节路径和解析置信度。
5. `/rag/query` 分别执行 Qdrant 向量召回和应用内 BM25 召回，再使用 Reciprocal Rank Fusion 去重排序。
6. 精确实体与所问关系位于同一结构块时，可以补救较低的向量分；普通词面重合不能绕过证据门控。
7. `ContextBuilder` 在预算内组装通过门控的证据。没有可靠证据时直接拒答，有证据时才调用 Ollama。

## 索引重建

`POST /rag/documents/rebuild` 只处理当前登录用户的文档。每份文档从 MinIO 原文件生成
一个新版本，先写入全部新向量并切换 PostgreSQL 目录中的活动版本，成功后再删除旧版本
向量。解析或嵌入失败不会撤下旧版本，也不会阻塞批次内其他文档。

当前项目处于 Demo 阶段，不兼容旧分块 payload。升级后应在“我的文档”页面执行一次
“重建全部索引”。

## Demo 规模限制

关键词通道通过 Qdrant `scroll` 读取当前用户、活动版本和所选文档范围内的 Chunk，并在
Python 服务中计算 BM25，当前上限为 10000 个 Chunk。该方案适合本地 Demo，能可靠处理
中文二元词、英文标识符和实体短语；生产规模应把 `LexicalRetriever` 替换为 Qdrant
稀疏向量、Elasticsearch/OpenSearch 或专用倒排索引，融合与证据门控接口无需改变。

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
| `RETRIEVAL_STRATEGY` | `hybrid` | 默认使用向量与 BM25 双路召回 |
| `RETRIEVAL_TOP_K` | `12` | 最终召回数量 |
| `RETRIEVAL_SCORE_THRESHOLD` | `0.35` | Qdrant 初召回相似度门槛 |
| `RETRIEVAL_MIN_EVIDENCE_SCORE` | `0.52` | 允许进入回答节点的最低证据分数 |
| `RETRIEVAL_MAX_EVIDENCE` | `6` | 最终发送给模型的最大证据数 |
| `CONTEXT_MAX_CHARS` | `12000` | 发送给生成模型的最大证据字符数 |
| `RAG_HOST` / `RAG_PORT` | `127.0.0.1` / `8001` | API 监听地址 |

`hybrid` 不依赖问答模型，Ollama 问答模型不可用时仍能完成检索与证据门控，但无法生成
最终自然语言答案。MQE/HyDE 是显式可选的纯向量查询扩写策略，会增加模型调用次数与延迟。
