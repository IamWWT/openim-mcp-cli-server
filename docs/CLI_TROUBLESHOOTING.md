# CLI 调用失败排障记录

**日期**：2026-05-13  
**现象**：`uv run openim-cli list-conversations --user-id 6122258426` 执行失败  
**容器**：`565e998e8dfa`（Rocky Linux 8 镜像构建的容器）

---

## 错误信息

```
2026-05-13 19:01:55.409 | ERROR | openim_mcp.openim_client:_refresh_token:91 - Failed to refresh admin token: get_admin_token failed: {'errCode': 1002, 'errMsg': 'NoPermissionError', 'errDlt': 'secret invalid'}
{"success": false, "error": "get_admin_token failed: {'errCode': 1002, 'errMsg': 'NoPermissionError', 'errDlt': 'secret invalid'}"}
```

## 调用链分析

```
openim-cli
  └─ OpenIMClient.ensure_token()
       └─ POST /auth/get_admin_token
            payload: {"secret": "wrong_secret", "userID": "imAdmin"}
                                               ↓
                              OpenIM 服务端校验 secret → ❌ 不匹配
                                               ↓
                                   errCode: 1002, secret invalid
```

## 根因定位

1. **API 可达**。错误码是 1002（NoPermissionError），不是连接超时或 4xx/5xx，说明 API 地址 `http://192.168.0.127:10002` 是通的。

2. **secret 不匹配**。项目 `.env` 中：
   ```
   OPENIM_ADMIN_SECRET=wrong_secret
   ```

3. **实际 secret**。OpenIM Docker 部署配置位于 `/home/wwt/repo/jk/my/im/openim-docker-v0408/.env`，其中：
   ```
   OPENIM_SECRET=OpenIM123
   ```

**结论**：`.env` 中的 `OPENIM_ADMIN_SECRET` 值与 OpenIM 服务端实际配置不一致。

## 修复步骤

### 1. 更新 `.env`

```diff
-OPENIM_ADMIN_SECRET=wrong_secret
+OPENIM_ADMIN_SECRET=OpenIM123
```

### 2. 同步更新 `config.py` 默认值

```diff
     openim_admin_secret: str = Field(
-        default="wrong_secret",
+        default="OpenIM123",
```

### 3. 同步更新 `README.md` 示例

```diff
-OPENIM_ADMIN_SECRET=wrong_secret
+OPENIM_ADMIN_SECRET=OpenIM123
```

### 4. 修复 `pyproject.toml` deprecation warning（附带）

```diff
-[tool.uv]
-dev-dependencies = []
+[dependency-groups]
+dev = []
```

> `tool.uv.dev-dependencies` 已被 uv 标记为废弃，迁移到 `dependency-groups.dev`。

## 验证

```python
from dotenv import dotenv_values
values = dotenv_values('.env')
secret = values.get('OPENIM_ADMIN_SECRET')
# → 'OpenIM123' ✅
```

## 涉及的配置文件对应关系

| 文件 | 变量名 | 说明 |
|------|--------|------|
| `wwt-openim-mcp-server/.env` | `OPENIM_ADMIN_SECRET` | MCP Server 使用的 admin secret |
| `openim-docker-v0408/.env` | `OPENIM_SECRET` | OpenIM 服务端的 secret |

两个变量必须一致，MCP Server 才能通过 `/auth/get_admin_token` 获取 admin token。

## 经验教训

- `.env` 中 `#` 开头的行是注释，但 `VAR=value#text` 中的 `#text` 也会被截断。含特殊字符的值必须加引号。
- 配置文件中的 secret 与部署端的实际值不一致是 MCP 工具调用失败的常见原因。
- 错误码 `1002 NoPermissionError` 的语义很明确：权限不足 → 检查认证凭证。
