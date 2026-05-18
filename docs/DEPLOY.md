# 部署指南 — openim-mcp+cli-server

本文档描述如何部署和运行 OpenIM MCP Server + CLI。

---

## 环境要求

| 组件 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.12+ | 推荐使用 uv 管理依赖 |
| uv | 0.5+ | Python 包管理器（推荐） |
| OpenIM | v3.8+ | REST API 可达（默认端口 10002） |
| 操作系统 | Linux / macOS | Windows 理论支持但未测试 |

---

## 快速部署（5 分钟）

### 1. 获取代码

```bash
git clone https://github.com/<your-org>/openim-mcp-cli-server.git
cd openim-mcp-cli-server
```

### 2. 配置环境变量

```bash
cp .env.templates .env   # 如果有模板文件
# 或直接编辑 .env
vim .env
```

**最小配置：**

```bash
# OpenIM 服务地址
OPENIM_API_ADDRESS=http://192.168.0.127:10002
OPENIM_ADMIN_SECRET="your-secret-here"
OPENIM_ADMIN_ID=imAdmin
OPENIM_SENDER_ID=bot001

# MCP 服务
MCP_TRANSPORT=http
MCP_HOST=0.0.0.0
MCP_PORT=8079
```

**安全策略（高危操作默认关闭）：**

```bash
ALLOW_PRIVATE_CHAT=false      # 私聊
ALLOW_CREATE_GROUP=false      # 建群
ALLOW_SEND_NOTIFICATION=false # 业务通知
```

详细配置说明见 [安全操作文档](docs/security-operations.md)。

### 3. 安装依赖

```bash
uv sync
```

### 4. 验证安装

```bash
# 验证 CLI 可用
uv run openim-cli --help

# 运行验证脚本（离线模式）
bash test/verify_tools.sh
```

---

## 运行模式

### 模式 A：MCP 服务（供 AI Agent 调用）

```bash
# 方式 1：uv 启动
uv run openim-mcp

# 方式 2：管理脚本
./start.sh start
```

服务默认监听 `http://0.0.0.0:8079/mcp`，提供 15 个 MCP 工具。

验证服务：

```bash
# 检查服务状态
./start.sh status

# 测试 MCP 接口
curl -X POST http://localhost:8079/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### 模式 B：CLI 命令行（管理员直接使用）

```bash
# 查看所有命令
uv run openim-cli --help

# 示例：获取用户信息
uv run openim-cli get-user-info --user-ids user001

# 示例：发送群消息
uv run openim-cli send-text \
  --recv-id 2137448827 \
  --text "服务部署完成" \
  --session-type 3
```

---

## 管理脚本 (start.sh)

```bash
./start.sh start      # 启动服务
./start.sh stop       # 停止服务
./start.sh restart    # 重启服务
./start.sh status     # 查看状态
./start.sh logs       # 查看日志（tail -f）
```

服务日志输出到 `logs/openim-mcp.log`，PID 文件在 `openim-mcp.pid`。

---

## 生产环境部署建议

### 1. 使用 systemd 管理服务

```ini
# /etc/systemd/system/openim-mcp.service
[Unit]
Description=OpenIM MCP Server
After=network.target

[Service]
Type=simple
User=openim
WorkingDirectory=/opt/openim-mcp-cli-server
EnvironmentFile=/opt/openim-mcp-cli-server/.env
ExecStart=/root/.local/bin/uv run openim-mcp
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now openim-mcp
systemctl status openim-mcp
```

### 2. 网络隔离

- **生产环境**：`MCP_HOST=127.0.0.1`，仅监听本地回环
- 若需外部访问，通过反向代理（nginx/haproxy）暴露，并配置 TLS

### 3. 日志与监控

```bash
# 日志级别
LOG_LEVEL=INFO              # 正常
LOG_LEVEL=DEBUG             # 排查问题时

# 集中日志（可选）
tail -f logs/openim-mcp.log | tee >(curl -s -X POST http://your-log-aggregator/ingest -d @-)
```

### 4. 定期维护

- **轮换 secret**：定期更新 `OPENIM_ADMIN_SECRET` 和 `OPENIM_SENDER_ID`
- **更新依赖**：`uv sync --upgrade` 获取安全补丁
- **审计日志**：检查 `logs/openim-mcp.log` 中的异常调用

---

## 容器化部署

### Dockerfile 示例

```dockerfile
FROM python:3.12-slim

RUN pip install uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY src/ src/
COPY .env LICENSE README.md ./

EXPOSE 8079

CMD ["uv", "run", "openim-mcp"]
```

### docker-compose 示例

```yaml
version: '3.8'
services:
  openim-mcp:
    build: .
    ports:
      - "8079:8079"
    env_file:
      - .env
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs
```

---

## 闭环验证

部署完成后运行验证脚本：

```bash
# 离线验证（检查代码和 CLI 接口）
bash test/verify_tools.sh

# 在线验证（需要 OpenIM 服务可达）
bash test/verify_tools.sh --online
```

验证覆盖：
- 代码语法完整性（4 个 Python 源文件）
- 关键文件存在性
- CLI 接口 16 个子命令
- 安全策略拦截面
- OpenIM API 在线调用（get-user-info, get-online-status, lookup-user）

---

## 常见问题

### Q: CLI 报 "secret invalid"
**.env 中 `OPENIM_ADMIN_SECRET` 与 OpenIM 服务端配置不一致。**
从 OpenIM Docker 部署的 `.env` 中获取实际 secret 值。

详见：[CLI 认证排障文档](docs/troubleshooting-cli-auth-failure.md)

### Q: 私聊被拦截
**默认禁止私聊，`ALLOW_PRIVATE_CHAT=false`。**
如需开启，在 `.env` 中设 `ALLOW_PRIVATE_CHAT=true` 并重启服务。

### Q: 创建群组被拦截
**默认禁止建群，`ALLOW_CREATE_GROUP=false`。**
在 `.env` 中设 `ALLOW_CREATE_GROUP=true`。

### Q: MCP 服务无法启动
1. 检查端口是否被占用：`ss -tlnp | grep 8079`
2. 检查 `.env` 配置是否正确
3. 查看日志：`./start.sh logs`
