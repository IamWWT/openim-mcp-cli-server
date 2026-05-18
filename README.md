# openim-mcp+cli-server

> OpenIM MCP Server + CLI — 为 AI Agent 提供即时通讯能力的完整工具集

基于 [FastMCP](https://github.com/jlowin/fastmcp) 构建的 **OpenIM 即时通讯 MCP 服务**，为 AI Agent 提供完整的消息发送、用户管理、群组管理和会话查询能力，适用于 AIOps 告警派发、运维协作等场景。


[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

## 功能概览

### 消息管理 (Message)
- 📨 发送群聊文本消息（默认禁止私聊，可通过 ALLOW_PRIVATE_CHAT 开启）
- 🖼️ 发送图片消息
- 📢 群聊中 @ 指定成员
- 📡 发送业务通知（默认禁止，可通过 ALLOW_SEND_NOTIFICATION 开启）
- ↩️ 撤回已发送消息

### 用户管理 (User)
- 👤 获取用户详情（昵称、头像、注册时间）
- 🟢 获取用户在线状态（各终端状态、token）
- 📋 获取所有已注册用户（分页）

### 群组管理 (Group)
- 📊 获取群组详情（群名、人数、群主）
- 👥 获取群成员列表（分页，支持搜索）
- 🏗️ 创建群组（动态创建告警响应群）
- 📩 邀请用户进群
- 🚫 移除群成员

### 查询 (Lookup)
- 🔍 用户查询：userID → 昵称，或昵称 → userID
- 🔍 群组查询：groupID → 群名称

### 会话管理 (Conversation)
- 💬 获取排序后的会话列表

### 基础设施
- 🔄 自动缓存并刷新管理员 Token，网络异常自动重试
- 🚀 httpx 连接池复用 + 信号量并发控制
- 🔒 默认群聊安全策略（ALLOW_PRIVATE_CHAT 开关）
- 🛡️ 发送者身份绑定（OPENIM_SENDER_ID，防伪造）
- 🛡️ 危险操作默认关闭（ALLOW_CREATE_GROUP / ALLOW_SEND_NOTIFICATION 开关）
- 🖥️ CLI 命令行工具（无需启动 MCP 服务即可直接调用）

---

## 快速开始

### 1. 环境准备
- Python 3.12+
- 可访问的 OpenIM REST API 地址

### 2. 配置环境变量

创建 `.env` 文件：

```bash
# OpenIM 服务地址
OPENIM_API_ADDRESS=http://192.168.0.127:10002
OPENIM_ADMIN_SECRET="Pwd1Open2#IMD"
OPENIM_ADMIN_ID=imAdmin
OPENIM_SENDER_ID=bot001

# MCP 服务配置
MCP_TRANSPORT=http
MCP_HOST=0.0.0.0
MCP_PORT=8079
LOG_LEVEL=INFO

# 安全策略（默认禁止私聊，如需开启设为 true）
ALLOW_PRIVATE_CHAT=false
ALLOW_CREATE_GROUP=false
ALLOW_SEND_NOTIFICATION=false
```

### 3. 安装依赖并启动

```bash
# 安装
uv sync

# 启动 MCP 服务
uv run openim-mcp

# 或直接使用 CLI
uv run openim-cli --help
```

---

## 使用方式

### 方式一：MCP 服务（供 AI Agent 调用）

启动服务后，AI Agent 通过 MCP 协议发现并调用工具：

```bash
uv run openim-mcp
```

服务默认监听 `http://0.0.0.0:8079`，提供 13 个 MCP 工具。

### 方式二：CLI 命令行（直接调用）

无需启动服务，命令行直接操作 OpenIM：

```bash
# 查看所有命令
uv run openim-cli --help

# 发送文本
uv run openim-cli send-text \
  --recv-id user001 \
  --text "磁盘使用率超过 90%，请处理" \
  --session-type 1

# 发送群聊 @ 消息
uv run openim-cli send-group-at \
  --group-id 123456 \
  --text "@所有人 服务器 CPU 告警" \
  --at-user-ids user001,user002

# 发送业务通知（告警推送）
uv run openim-cli send-biz-notification \
  --send-user-id sys001 \
  --recv-user-id user001 \
  --key disk_alert \
  --data '{"host":"web01","usage":95,"severity":"critical"}'

# 查询用户在线状态
uv run openim-cli get-online-status --user-ids user001,user002

# 获取群组详情
uv run openim-cli get-group-info --group-ids 123456,789012

# 创建告警响应群
uv run openim-cli create-group \
  --owner-user-id user001 \
  --group-name "磁盘告警-2026-05-13" \
  --member-user-ids user002,user003,user004 \
  --introduction "磁盘告警应急响应群"

# 邀请成员加入告警群
uv run openim-cli invite-to-group \
  --group-id 123456 \
  --invited-user-ids user005 \
  --reason "加入告警处理"

# 用户查询：ID→昵称 / 昵称→ID
uv run openim-cli lookup-user --user-id user001
uv run openim-cli lookup-user --nickname "张三"

# 群组查询：groupID→群名称
uv run openim-cli lookup-group --group-id 123456

# 查看会话列表
uv run openim-cli list-conversations --user-id bot001
```

---

## AIOps 告警场景典型流程

```
1. 监控系统触发告警
2. AI Agent 收到告警 → 调用 MCP 工具
3. create_group 创建告警响应群
4. invite_to_group 拉入值班人员
5. send_group_at_message 发送告警详情并 @ 相关人员
6. send_business_notification 推送业务通知
7. get_users_online_status 检查人员在线状态
8. 告警解除后 kick_group_member 清理人员
```

---

## MCP 工具清单

| 工具名 | 分类 | 说明 |
|--------|------|------|
| `send_text_message` | 消息 | 发送文本消息（单聊/群聊） |
| `send_picture_message` | 消息 | 发送图片消息 |
| `send_group_at_message` | 消息 | 群聊 @ 消息 |
| `send_business_notification` | 消息 | 发送业务通知 |
| `revoke_message` | 消息 | 撤回消息 |
| `get_users_info` | 用户 | 获取用户详情 |
| `get_users_online_status` | 用户 | 获取在线状态 |
| `get_all_users` | 用户 | 获取所有注册用户 |
| `get_groups_info` | 群组 | 获取群组详情 |
| `get_group_member_list` | 群组 | 获取群成员列表 |
| `create_group` | 群组 | 创建群组 |
| `invite_to_group` | 群组 | 邀请进群 |
| `kick_group_member` | 群组 | 移除群成员 |
| `get_conversation_list` | 会话 | 获取会话列表 |
| `lookup_user` | 查询 | 用户查询：userID→昵称 / 昵称→userID |
| `lookup_group` | 查询 | 群组查询：groupID→群名称 |

---

## 项目结构

```
src/openim_mcp/
├── __init__.py          # 包入口
├── __main__.py          # python -m 入口
├── config.py            # 配置管理（环境变量）
├── openim_client.py     # OpenIM REST API 客户端
├── server.py            # MCP 服务（15 个工具）
└── cli.py               # CLI 命令行工具
```

---

## 开发

```bash
# 安装开发依赖
uv sync --group dev

# 运行测试
uv run pytest test/

# 代码检查
uv run ruff check src/
```

## 文档

- [部署指南](docs/deploy.md) — 快速部署、生产环境配置、容器化
- [安全操作梳理](docs/security-operations.md) — 工具风险评估、安全策略配置
- [CLI 认证排障](docs/troubleshooting-cli-auth-failure.md) — secret invalid 等常见问题

---

## License

Apache 2.0 — 详见 [LICENSE](LICENSE)

