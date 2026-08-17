# Supabase 身份、本地数据隔离与持久化聊天设计

## 目标

为现有本地 RAG 应用补齐邮箱密码注册、登录、退出、用户文档隔离、聊天会话历史、新建聊天和连续上下文问答。Supabase 仅承担身份认证及轻量用户资料；文档、解析产物、聊天和索引关联继续保存在本地基础设施。

## 职责边界

- Supabase Auth：邮箱密码注册、登录、刷新会话、退出和稳定的用户 UUID。
- Supabase 用户资料：昵称、头像等轻量资料，可使用 `user_metadata`；第一版不依赖独立资料表。
- Next.js：登录界面、受保护页面、服务端会话读取、同源 API 网关和交互状态。
- 本地 PostgreSQL：本地用户映射、文档元数据、聊天会话、聊天消息、会话文档筛选和滚动摘要。
- 本地 MinIO：原始文件和解析后的 Markdown。
- 本地 Qdrant：文档向量；每个点携带 `owner_id`，所有检索同时过滤 `owner_id` 与可选 `document_ids`。
- Python RAG：再次验证 Supabase JWT、执行授权查询、文档处理、上下文组装、检索与回答生成。
- Spring Boot：本阶段不进入认证和聊天主链路，避免为已有直连链路增加无必要的网关层。

## 身份与信任边界

浏览器使用 Supabase 会话。Next.js 受保护页面和 API 从服务端会话读取访问令牌；未登录请求返回 401。代理到 Python 时转发原始 Bearer 令牌。Python 使用 Supabase 项目的 JWKS 验证签名、签发者、受众和过期时间，并只使用 JWT `sub` 作为 `owner_id`。

任何业务请求体、查询参数或自定义请求头中的用户 ID 都不可信。文档、聊天和向量访问必须把令牌中的 `owner_id` 放入数据库或向量过滤条件。文档详情和原文读取先执行所有权查询，再访问 MinIO 对象键。

## 本地数据模型

### `app_users`

- `id uuid primary key`：等于 Supabase 用户 UUID。
- `email text`：用于本地展示和审计，不作为授权依据。
- `display_name text null`。
- `created_at`、`updated_at`。

首次成功访问受保护 API 时执行幂等 upsert，避免依赖 Supabase webhook。

### `rag_documents`

在现有表增加 `owner_id uuid references app_users(id)`，并建立 `(owner_id, updated_at desc)` 索引。新写入记录强制提供非空 `owner_id`；迁移前的空值记录仅作为不可见遗留数据保留。所有列表、详情和原文查询都要求 `document_id + owner_id`。MinIO 对象键改为 `users/{owner_id}/documents/{document_id}/v{version}/...`。

### `chat_conversations`

- `id uuid primary key`。
- `owner_id uuid not null references app_users(id)`。
- `title text not null`，初始标题由第一条用户消息截取生成。
- `summary text not null default ''`。
- `summarized_through_message_id uuid null`。
- `created_at`、`updated_at`。

列表按 `updated_at desc` 返回当前用户会话。新建聊天先创建空会话；如果用户在空白页直接发送，也允许服务端原子创建会话。

### `chat_messages`

- `id uuid primary key`。
- `conversation_id uuid not null references chat_conversations(id) on delete cascade`。
- `owner_id uuid not null references app_users(id)`，用于明确隔离并简化授权索引。
- `role text`：仅允许 `user`、`assistant`。
- `content text not null`。
- `status text`：`pending`、`completed`、`failed`。
- `citations jsonb not null default '[]'`：保存当轮引用快照。
- `error text null`。
- `created_at`。

发送问题时先保存用户消息和 pending 助手消息；生成成功后完成助手消息，失败则标记 failed。这样刷新页面后不会丢失已发送问题，也能显示失败并重试。

### `conversation_documents`

- `conversation_id uuid`。
- `document_id text`。
- `owner_id uuid`。
- 联合主键 `(conversation_id, document_id)`。

空集合表示检索当前用户全部已就绪文档；非空集合表示仅检索选中文档。写入关联前同时验证会话和文档均属于当前用户。

## API 设计

Next.js 提供同源接口并统一转发认证：

- `POST /api/auth/sign-up`、`POST /api/auth/sign-in`、`POST /api/auth/sign-out`。
- `GET /api/conversations`、`POST /api/conversations`。
- `GET /api/conversations/{id}`：返回会话、消息和已选文档。
- `PATCH /api/conversations/{id}`：修改标题或文档筛选。
- `POST /api/conversations/{id}/messages`：保存问题、组装上下文、检索并生成回答。
- 现有文档列表、上传、详情和原文 API 保留路径，但全部要求登录并向 Python 转发令牌。

Python 对应接口只接受已验证身份。未登录返回 401；资源不属于当前用户时统一返回 404，避免泄露资源是否存在；输入无效返回 400/422；上游模型不可用时消息标记 failed 并返回可展示的错误。

## 上下文管理

每次回答由四部分组成：稳定系统规则、滚动摘要、最近原始消息、本轮检索证据。

- 最近原始消息默认保留 6 轮，最多 12 条 user/assistant 消息。
- 更早内容在超出预算时压缩为 600–1000 中文字的滚动摘要，只保留目标、事实、约束、决定、未解决问题和引用文档。
- 检索查询由当前问题、摘要和最近两条用户消息改写为可独立理解的问题。
- 上下文预算按系统规则 5%、对话 20%、检索证据 50%、回答 25% 分配。
- 超限时先移除低相关证据，再裁剪最老的原始消息；当前问题和授权约束永不裁剪。
- 摘要只在历史超过预算后更新，并记录已摘要到哪条消息，避免重复摘要。
- 助手消息保存当轮引用 JSON 快照，历史查看不重新计算引用。

## 前端交互

未登录用户只看到登录/注册页。登录后进入应用：

- 左侧导航增加会话区，按更新时间列出当前用户历史聊天。
- “新建聊天”创建并打开空会话；空会话不显示演示问答。
- 发送时立即把用户消息追加到列表并清空输入框，显示 pending 助手消息，防止当前实现中单个 `result` 被清空造成交互断裂。
- 请求成功后用真实回答替换 pending；失败时保留用户消息并显示可重试错误。
- 当前会话消息按时间顺序恢复，切换会话不会混合状态。
- 文档筛选器默认表示“全部我的已就绪文档”，用户可为当前会话选择子集。
- 文档列表和资料数量只展示当前用户的真实数据，移除生产界面的演示文档与演示回答。
- 退出后清除本地交互状态并回到登录页。

## 迁移与兼容

本地 PostgreSQL 使用显式 SQL 迁移。现有无 `owner_id` 的开发数据无法可靠判断归属，迁移后保留为 `owner_id is null` 的不可见记录；本地开发者可自行清理后重新上传。所有新写入路径在应用层和 SQL 约束触发器中拒绝空 `owner_id`。第一版不提供管理员认领旧数据功能。

Qdrant 现有不带 `owner_id` 的点不会被新过滤条件命中，因此天然隔离；用户重新上传后生成带所有者的新点。MinIO 旧对象继续保留但没有授权记录指向时不可访问。

## 测试与验收

- JWT：有效、过期、错误签发者、缺失令牌。
- 文档：A 用户不能列出、读取、下载或检索 B 用户文档。
- 上传：PostgreSQL 记录、MinIO 键和 Qdrant payload 使用同一个 `owner_id`。
- 会话：用户只能创建、列出和打开自己的会话；新聊天为空；历史消息可恢复。
- 发送：用户消息先持久化；成功保存回答与引用；失败保留问题并记录失败状态。
- 上下文：最近 6 轮保留原文，较老内容进入摘要，检索查询包含必要指代信息且不包含无关完整历史。
- 筛选：默认检索全部个人文档；选择子集后只允许命中该子集；伪造他人文档 ID 返回 404。
- 前端：登录保护、发送状态、快速重复点击、切换会话和退出流程。
- 完整构建与现有 Python 测试必须通过。

## 第一版明确不做

短信登录、OAuth、找回密码、管理员后台、共享文档、团队空间、会话删除、消息编辑、流式输出和跨用户协作均不在本次范围。
