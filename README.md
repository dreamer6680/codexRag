# Local RAG Workspace

一个完全本地运行的中文知识库 RAG 骨架：Next.js 前端、Spring Boot 认证/资料服务、FastAPI + LangGraph RAG 服务、MinerU 解析、Ollama、Qdrant、MinIO、MySQL 和 PostgreSQL。

## 快速开始

只启动 Python RAG API（会在缺少依赖时自动安装；Ollama 使用本机服务）：

```powershell
python start_rag.py --with-infra
```

开发模式可使用 `python start_rag.py --with-infra --reload`。启动后访问
`http://127.0.0.1:8001/docs`，健康检查为 `http://127.0.0.1:8001/health`。

如果 Qdrant、Ollama、MinerU 已经运行，只需执行 `python start_rag.py`。

完整前后端环境：

1. 复制 `.env.example` 为 `.env`，并设置强 JWT 密钥及数据库密码。
2. 启动：`docker compose --env-file .env.local up --build`。
3. 在本机 Ollama 中下载模型（首次且网络可用时）：

```powershell
ollama pull qwen3:14b
ollama pull qwen3:8b
ollama pull bge-m3
ollama pull qllama/bge-reranker-v2-m3
```

4. 打开 `http://localhost:3000`。所有端口均绑定到 `127.0.0.1`。

## 用户登录与个人数据隔离

应用使用 Supabase Auth 提供邮箱密码注册、登录、会话刷新和退出；Supabase 不保存文档或聊天业务数据。请在 Supabase 项目中启用 Email provider，并在 `.env` 中配置：

```dotenv
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-publishable-key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_JWT_AUDIENCE=authenticated
```

RAG API 会使用 Supabase JWKS 再次验证访问令牌。令牌的 `sub` 是本地数据唯一的所有者 ID：

- 本地 PostgreSQL 保存用户映射、文档元数据、聊天、消息、滚动摘要和会话文档范围。
- MinIO 对象键以 `users/{user_id}/documents/` 开头。
- Qdrant 向量 payload 保存 `owner_id`，每次检索都强制按该字段过滤。
- 不属于当前用户的文档或会话统一返回 404，未登录 API 返回 401。

首次访问受保护接口时，服务会自动执行 `services/python-rag/migrations/001_user_chat.sql`。迁移前没有 `owner_id` 的旧文档会保留为不可见数据，不会自动归属给任何新用户；开发环境可清理旧数据后重新上传。

聊天默认检索当前用户的全部已就绪文档，也可为每个会话选择文档子集。上下文保留最近 6 轮原文，更早内容压缩为滚动摘要，并保存每条回答当时使用的引用快照。

## 开发模式

- 前端：`cd apps/web; npm install; npm run dev`
- RAG 服务：仓库根目录执行 `python start_rag.py --reload`，或进入 `services/python-rag` 执行 `python -m app`
- Java：`cd services/java-core; ./mvnw spring-boot:run`（首次可使用系统 Maven 运行 `mvn spring-boot:run`）

`MinerU` 运行于独立本地容器。`services/mineru` 将其 CLI 包装为内部 HTTP 服务；生产前请依据 GPU/CUDA 与 MinerU 版本锁定镜像及模型缓存。

`rag-api` 容器通过 `http://host.docker.internal:11434` 连接本机 Ollama。若健康检查显示
Ollama 不可用，请确认本机 Ollama 已启动并允许 Docker 访问；必要时将 Ollama 的监听地址
设置为 `0.0.0.0:11434` 后重启 Ollama。

## RAG API

- `POST /rag/index`：写入已经解析、切块后的文档片段。
- `POST /rag/upload`：上传 PDF、TXT 或 Markdown；PDF 由 MinerU 解析并自动写入向量库。

PDF 上传前，Next.js 上传代理会使用
[`@firecrawl/pdf-inspector`](https://github.com/firecrawl/pdf-inspector) 在本地检测 PDF
类型、页数、置信度和需要 OCR 的页码，并在“我的文档”页面展示结果。文本型 PDF
直接用 PDF Inspector 提取 Markdown；扫描型和混合型 PDF 才交给 MinerU OCR。
- `POST /rag/query`：检索并生成带引用的答案；`strategy` 可取 `vector`、`mqe`、`hyde`、`hybrid`。
- `GET /health`：检查 Ollama、Qdrant 与 MinerU。

详细分层与扩展方式见 [RAG 服务设计](./services/python-rag/ARCHITECTURE.md)。
