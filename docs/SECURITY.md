# 危险操作安全梳理

**日期**：2026-05-18  
**目的**：识别 MCP 工具中所有可能被滥用的操作，记录安全控制措施和默认策略。

---

## 风险评估矩阵

| 风险等级 | 说明 |
|----------|------|
| 🔴 高危 | 可直接造成信息泄露、骚扰用户、破坏群组结构 |
| 🟡 中危 | 可间接影响用户体验，需配合其他操作才能造成危害 |
| 🟢 低危 | 只读操作，不会产生副作用 |

---

## 工具清单与风险评估

### 消息管理 (Message)

| 工具 | 风险 | 危险场景 | 控制措施 |
|------|------|----------|----------|
| `send_text_message` | 🟡 中危 | 伪造身份向用户发送骚扰/钓鱼消息 | **sender_id 由环境变量 `OPENIM_SENDER_ID` 强制指定**，调用方无法覆盖；私聊默认关闭（`ALLOW_PRIVATE_CHAT=false`），群聊需指定 groupID |
| `send_picture_message` | 🟡 中危 | 同上，且可发送恶意图片 | 同 `send_text_message` 控制链 |
| `send_group_at_message` | 🟡 中危 | 在群内 @ 骚扰用户 | **sender_id 由环境变量指定**；仅在群聊内生效，需 groupID |
| `send_business_notification` | 🔴 高危 | 推送虚假告警，干扰业务 | **默认关闭**（`ALLOW_SEND_NOTIFICATION=false`），需显式开启 |
| `revoke_message` | 🟡 中危 | 撤回他人正常消息 | **默认关闭**（`ALLOW_REVOKE_MESSAGE=false`），需显式开启；需要消息的 `conversationID` + `seq`，无法批量操作 |

### 用户管理 (User)

| 工具 | 风险 | 危险场景 | 控制措施 |
|------|------|----------|----------|
| `get_users_info` | 🟢 低危 | 查询用户信息 | 只读操作，无副作用 |
| `get_users_online_status` | 🟢 低危 | 查看在线状态 | 只读操作，无副作用 |
| `get_all_users` | 🟢 低危 | 遍历用户列表 | 只读操作，有分页限制 |

### 群组管理 (Group)

| 工具 | 风险 | 危险场景 | 控制措施 |
|------|------|----------|----------|
| `get_groups_info` | 🟢 低危 | 查询群信息 | 只读操作 |
| `get_group_member_list` | 🟢 低危 | 查看群成员 | 只读操作 |
| `create_group` | 🔴 高危 | 批量创建垃圾群组 | **默认关闭**（`ALLOW_CREATE_GROUP=false`），需显式开启 |
| `invite_to_group` | 🔴 高危 | 将用户拉入恶意群组 | **默认关闭**（`ALLOW_INVITE_TO_GROUP=false`），需显式开启 |
| `kick_group_member` | 🔴 高危 | 恶意移除群成员（含群主） | **默认关闭**（`ALLOW_KICK_MEMBER=false`），需显式开启 |

### 会话管理 (Conversation)

| 工具 | 风险 | 危险场景 | 控制措施 |
|------|------|----------|----------|
| `get_conversation_list` | 🟢 低危 | 查看会话历史 | 只读操作 |

### 查询 (Lookup)

| 工具 | 风险 | 危险场景 | 控制措施 |
|------|------|----------|----------|
| `lookup_user` | 🟢 低危 | userID↔昵称查询 | 只读操作 |
| `lookup_group` | 🟢 低危 | groupID→群名称 | 只读操作 |

---

## 安全控制层级

```
Layer 1: 身份绑定
   └─ sender_id 由 OPENIM_SENDER_ID 环境变量强制指定，MCP 工具不暴露该参数
      防止调用方冒充他人身份发送消息

Layer 2: 功能开关
   └─ ALLOW_PRIVATE_CHAT=false       → 禁止单聊
   └─ ALLOW_CREATE_GROUP=false       → 禁止建群
   └─ ALLOW_SEND_NOTIFICATION=false  → 禁止推送通知
   └─ ALLOW_INVITE_TO_GROUP=false    → 禁止邀请进群
   └─ ALLOW_KICK_MEMBER=false        → 禁止移除群成员
   └─ ALLOW_REVOKE_MESSAGE=false     → 禁止撤回消息
      高危操作默认关闭，需管理员显式开启

Layer 3: 参数校验
   └─ 群聊模式要求 groupID 非空
   └─ revoke 需要消息 seq（无法盲目撤回）
   └─ kick 需要群ID + userID（无法批量操作）
```

## 环境变量安全配置清单

```bash
# .env — 安全策略配置（生产环境推荐值）

# 身份绑定（必填）
OPENIM_SENDER_ID=<your_sender_id>    # 发送消息的固定身份，MCP 工具不可覆盖

# 操作开关（高危操作默认全部关闭）
ALLOW_PRIVATE_CHAT=false             # 私聊
ALLOW_CREATE_GROUP=false             # 建群
ALLOW_SEND_NOTIFICATION=false        # 业务通知
ALLOW_INVITE_TO_GROUP=false          # 邀请进群
ALLOW_KICK_MEMBER=false              # 移除群成员
ALLOW_REVOKE_MESSAGE=false           # 撤回消息
```

---

## 安全最佳实践

1. **最小权限原则**：仅开启业务必需的开关，默认全部关闭。
2. **sender_id 唯一绑定**：每个 MCP 实例使用独立的 sender_id，便于审计追溯。
3. **审计日志**：`openim_client.py` 中所有写操作均有 `logger` 记录，可配合集中日志系统做审计。
4. **网络隔离**：MCP 服务仅监听内网地址（如 `MCP_HOST=127.0.0.1`），不暴露到公网。
5. **定期轮换**：定期更换 `OPENIM_ADMIN_SECRET`，并同步更新 `.env`。
