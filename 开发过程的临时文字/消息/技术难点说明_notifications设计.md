# 技术难点说明：通知系统数据库设计

## 原有设计存在的问题

系统最初用三张独立表存储通知：`friend_requests`（好友申请）、`chat_invites`（聊天室邀请）、`announcements`（系统通知）。

**问题一：多表查询复杂。** 通知中心需要 UNION 三张表并在应用层合并排序。每增一种通知类型就多一张表。

**问题二：ID 前缀反模式。** 为区分来源，前端给 ID 加前缀（`fr_123`、`ci_456`、`sys_789`），到处是 `startsWith('fr_')` 这类判断。审批需路由到四个不同端点：

```
fr_ → POST /api/friend-requests/{id}/approve
ci_ → POST /api/chat-invites/{id}/approve
sys_ → 无审批功能
```

**问题三：不可扩展。** 新增通知类型需新建表、新加路由、新加前缀判断，遗漏任意一步都会出 Bug。

## 合表的难点

三种通知的业务逻辑完全不同：

| | 好友申请 | 聊天室邀请 | 系统通知 |
|---|---|---|---|
| **触发方式** | 用户主动发起 | 用户主动发起 | 系统自动触发 |
| **是否需要审批** | 是 | 是 | 否 |
| **审批后操作** | 双向写入好友关系 | 加入聊天室成员 + 发系统消息 | 无审批操作 |
| **专属数据** | 申请附言 message | 聊天室 ID、聊天室名称 | 无 |
| **能否删除** | 可删除 | 可删除 | 可锁定不可删除 |
| **生命周期** | 审批后完结 | 审批后完结 | 长期留存 |

如果简单合并成一张表不做额外设计，会导致行结构难以统一、代码中充满类型判断分支。

因此合并的核心问题不是"能不能放进去"，而是**如何设计表结构，让三种不同逻辑的通知既能共存于一张表，又不让代码复杂度爆炸**。最终的方案是在表中增加 `type` 字段做类型标识，各类型的专属数据存入 `extra` JSON 字段，使得查询统一、扩展灵活，同时避免了大量 NULL 列和巨型 if-else 分支。

## 合并方案：单表 + type + extra

受 IP 报文 "Protocol 字段 + Payload" 的设计启发，三表合一：

```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,        -- 'friend_request' / 'chat_invite' / 'system'
    sender_uid TEXT NOT NULL,
    receiver_uid TEXT,
    content TEXT,
    extra TEXT DEFAULT '{}',   -- JSON：各类型专有数据（申请附言、聊天室ID等）
    status TEXT DEFAULT '',    -- pending / approved / rejected
    is_read INTEGER DEFAULT 0
);
```

**效果：**
- 查询：3 次 SQL + 应用层合并 → 1 次 SQL + ORDER BY
- 审批端点：4 个 → 2 个，按 type 字段内部分发
- 前端标识：前缀硬编码 → type 字段判断
- 扩展性：增新类型只需加一个 type 枚举值

**为什么用 JSON extra 字段？** 各类型携带的数据不同（好友申请有附言、聊天室邀请有 chat_id），为每种类型加专用列会导致表结构膨胀且大量 NULL，JSON 字段灵活存储任意结构数据。
