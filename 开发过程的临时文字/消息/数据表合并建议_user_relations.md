# 数据表合并方案

本文档描述两个数据表合并方案：

1. **user_relations**：将 friends、blacklist、call_preferences 三张关系表合并为一张
2. **notifications**：将 friend_requests、chat_invites 以及 announcements 中的系统通知部分合并为一张通知表

---

## 一、user_relations：好友/黑名单/通话权限三表合一

### 现状

| 表 | 字段 | 示例 |
|---|---|---|
| `friends` | uid, friend_uid, created_at | (A, B, 时间) 表示 A 把 B 加为好友 |
| `blacklist` | uid, blocked_uid | (A, B) 表示 A 拉黑了 B |
| `call_preferences` | uid, target_uid, call_notify | (A, B, 1) 表示 A 允许 B 打电话来 |

三张表都是 `(uid, target_uid)` 单向关系结构，每次查询需要分别访问不同表。

### 表结构

```sql
CREATE TABLE user_relations (
    uid TEXT,                -- 我
    target_uid TEXT,         -- 对方
    is_friend INTEGER DEFAULT 0,     -- 我是否把对方加为好友
    is_blocked INTEGER DEFAULT 0,    -- 我是否拉黑了对方
    call_notify INTEGER DEFAULT 0,   -- 我是否接收对方的通话邀请
    created_at REAL,                 -- 成为好友的时间
    PRIMARY KEY (uid, target_uid)
);
```

### 设计要点

- **单向**：每行是"我→对方"的单向关系。如果 A 和 B 互为好友，需要两行：(A, B) 和 (B, A)
- **多字段合一**：同一对 uid 下的好友、拉黑、通话权限写在一行，查询时一次 WHERE 全拿
- **默认值**：`is_friend=0`, `is_blocked=0`, `call_notify=0`，无记录等价于全 0

### 数据迁移

```sql
-- 从 friends 表导入
INSERT OR REPLACE INTO user_relations (uid, target_uid, is_friend, created_at)
SELECT uid, friend_uid, 1, created_at FROM friends;

-- 从 blacklist 表导入
INSERT OR REPLACE INTO user_relations (uid, target_uid, is_blocked)
SELECT uid, blocked_uid, 1 FROM blacklist
ON CONFLICT(uid, target_uid) DO UPDATE SET is_blocked = 1;

-- 从 call_preferences 表导入
INSERT OR REPLACE INTO user_relations (uid, target_uid, call_notify)
SELECT uid, target_uid, call_notify FROM call_preferences
ON CONFLICT(uid, target_uid) DO UPDATE SET call_notify = excluded.call_notify;
```

### 废弃原表

```sql
DROP TABLE IF EXISTS friends;
DROP TABLE IF EXISTS blacklist;
DROP TABLE IF EXISTS call_preferences;
```

### API 与函数变动

#### 后端 app.py 变动

所有涉及 friends/blacklist/call_preferences 三张表的读写，改为操作 user_relations 表的对应字段。

| 路由 | 当前操作 | 改为 | 行号 |
|---|---|---|---|
| `GET /api/friends` | `SELECT ... FROM friends f JOIN users u ON f.friend_uid = u.uid WHERE f.uid=?` | `SELECT u.uid, u.name, u.role, r.created_at FROM user_relations r JOIN users u ON r.target_uid = u.uid WHERE r.uid=? AND r.is_friend=1` | 1246 |
| `POST /api/friends/add` | `INSERT INTO friends VALUES (?,?,?)` | `INSERT INTO user_relations (uid, target_uid, is_friend, created_at) VALUES (?,?,1,?) ON CONFLICT(uid,target_uid) DO UPDATE SET is_friend=1, created_at=?` | 1259 |
| `POST /api/friends/remove` | `DELETE FROM friends WHERE uid=? AND friend_uid=?`（双向两次） | `UPDATE user_relations SET is_friend=0 WHERE uid=? AND target_uid=?`（双向两次），并存 `created_at` 原值或置 NULL | 1284 |
| `GET /api/blacklist` | `SELECT ... FROM blacklist b JOIN users u ON b.blocked_uid = u.uid WHERE b.uid=?` | `SELECT u.uid, u.name, u.role FROM user_relations r JOIN users u ON r.target_uid = u.uid WHERE r.uid=? AND r.is_blocked=1` | 1536 |
| `POST /api/blacklist/add` | `INSERT OR IGNORE INTO blacklist VALUES (?,?)` | `INSERT INTO user_relations (uid, target_uid, is_blocked) VALUES (?,?,1) ON CONFLICT(uid,target_uid) DO UPDATE SET is_blocked=1` | 1545 |
| `POST /api/blacklist/remove` | `DELETE FROM blacklist WHERE uid=? AND blocked_uid=?` | `UPDATE user_relations SET is_blocked=0 WHERE uid=? AND target_uid=?` | 1570 |
| `GET /api/call/preference` | `SELECT call_notify FROM call_preferences WHERE uid=? AND target_uid=?` | `SELECT call_notify FROM user_relations WHERE uid=? AND target_uid=?` | 2148-2152 |
| `POST /api/call/preference` | `INSERT OR REPLACE INTO call_preferences (uid, target_uid, call_notify) VALUES (?,?,?)` | `INSERT INTO user_relations (uid, target_uid, call_notify) VALUES (?,?,?) ON CONFLICT(uid,target_uid) DO UPDATE SET call_notify=?` | 2161 |
| `POST /api/call/invite` | `SELECT call_notify FROM call_preferences WHERE uid=? AND target_uid=?` | `SELECT call_notify FROM user_relations WHERE uid=? AND target_uid=?` | 2190 |
| `POST /api/send`（黑名单检查） | `SELECT 1 FROM blacklist WHERE uid=? AND blocked_uid=?` | `SELECT 1 FROM user_relations WHERE uid=? AND target_uid=? AND is_blocked=1` | 739 |
| `POST /api/friend-request`（检查是否已是好友） | `SELECT 1 FROM friends WHERE uid=? AND friend_uid=?` | `SELECT 1 FROM user_relations WHERE uid=? AND target_uid=? AND is_friend=1` | 1322 |
| `GET /api/user-groups/<id>/detail`（即时聊天群组成员） | `SELECT friend_uid FROM friends WHERE uid=?` | `SELECT target_uid FROM user_relations WHERE uid=? AND is_friend=1` | 1027 |
| `GET /api/user-groups/<id>/detail`（私聊群组成员） | `SELECT ... FROM friends f JOIN users u ON f.friend_uid = u.uid WHERE f.uid=?` | `SELECT u.uid, u.name, u.role, r.created_at as added_at FROM user_relations r JOIN users u ON r.target_uid = u.uid WHERE r.uid=? AND r.is_friend=1 ORDER BY u.name` | 1042-1046 |
| `POST /api/friend-requests/<id>/approve`（双向加好友） | `INSERT OR IGNORE INTO friends VALUES (?,?,?)`（双向两次） | `INSERT INTO user_relations (uid,target_uid,is_friend,created_at) VALUES (?,?,1,?) ON CONFLICT DO UPDATE SET is_friend=1`（双向两次） | 1350-1351 |

#### 前端 groups.html 变动

| 函数 | 位置 | 改动内容 |
|---|---|---|
| `updateFriendBtn` | 1791 | `GET /api/friends` 的响应字段由 `uid` 变为 `uid, name, role`，判断逻辑改为检查 `friends` 数组中的 `uid`（字段名不变，不须改） |
| `memberInfoRemoveFriend` | 1817 | `POST /api/friends/remove` 不变 |
| `toggleFriend` | 1851 | `GET /api/friends` + `POST /api/friends/remove\|add` 不变 |
| `loadBlacklist` | 1755 | `GET /api/blacklist` 响应格式不变 |
| `memberInfoToggleBlock` | 1776 | `POST /api/blacklist/add\|remove` 不变 |

**前端总体影响很小**，因为 API 端点的 URL 和返回格式不变，只变了后端内部存储方式。

---

## 二、notifications：通知三表合一

### 现状

当前通知数据分散在三张表中，`GET /api/notifications` 需要在应用层 UNION 三张表：

| 表 | 用途 | 记录数维度 |
|---|---|---|
| `friend_requests` | 好友申请（需审批） | 每条申请一条记录 |
| `chat_invites` | 聊天室邀请（需审批） | 每条邀请一条记录 |
| `announcements`（unit='notification' 部分） | 系统通知（拉黑/取消好友等，无需审批） | 每条通知一条记录 |

前端返回的 `id` 带有前缀（`fr_`、`ci_`、`sys_`）以区分来源，审批/拒绝/删除操作需分别路由到不同的后端处理函数。

### 表结构

```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
        -- 'friend_request'  好友申请（需审批）
        -- 'chat_invite'     聊天室邀请（需审批）
        -- 'system'          系统通知（拉黑/取消好友/管理员手动发送等，无需审批）
    sender_uid TEXT NOT NULL,      -- 发送者uid，系统自动发送固定为 "system"
    receiver_uid TEXT,             -- 通知目标用户
    content TEXT,                  -- 通知内容
    extra TEXT DEFAULT '{}',       -- JSON，存各类型专有数据
        -- friend_request: {"message": "你好我想加你为好友"}
        -- chat_invite: {"chat_id": "xxx", "chat_name": "xxx"}
        -- system: {} 或空
    status TEXT DEFAULT '',        -- 需审批的类型：pending / approved / rejected
    is_read INTEGER DEFAULT 0,
    is_locked INTEGER DEFAULT 0,
    created_at REAL
);
```

### 设计要点

- 所有通知在一张表，`type` 区分类型，查询 `/api/notifications` 无需 UNION
- 需审批的类型（friend_request/chat_invite）用 `status` 跟踪状态
- 各类型的特有数据统一存入 `extra` JSON 字段，表结构精简
- 通知 ID 不再需要前缀，统一为数字 ID
- `announcements` 表保持不变，继续承担官方公告职能

### 数据迁移

```sql
-- 从 friend_requests 表导入
INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, status, is_read, created_at)
SELECT 'friend_request', from_uid, to_uid, message, '{}', status, is_read, created_at FROM friend_requests;

-- 从 chat_invites 表导入
INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, status, is_read, created_at)
SELECT 'chat_invite', from_uid, to_uid, '', json_object('chat_id', chat_id, 'chat_name', chat_name), status, is_read, created_at FROM chat_invites;

-- 从 announcements（仅通知部分，unit='notification'）导入
INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, is_read, is_locked, created_at)
SELECT 'system', publisher, target_uid, content, '{}', is_read, is_locked, created_at
FROM announcements WHERE target_uid IS NOT NULL AND target_uid != '';
```

### 废弃原表

```sql
DROP TABLE IF EXISTS friend_requests;
DROP TABLE IF EXISTS chat_invites;
-- announcements 表保留（仅清理通知数据），后续可考虑：
DELETE FROM announcements WHERE target_uid IS NOT NULL AND target_uid != '';
```

### 后端 app.py 变动

#### 2.1 新增/修改通知（写入）

| 路由 | 当前操作 | 改为 | 行号 |
|---|---|---|---|
| `POST /api/friend-request` | `INSERT INTO friend_requests (from_uid, to_uid, message, status, created_at)` | `INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, status, created_at) VALUES ('friend_request', ?, ?, ?, json_object('message',?), 'pending', ?)` | 1326 |
| `POST /api/user-groups/<id>/create-chat`（邀请成员） | `INSERT INTO chat_invites (chat_id, chat_name, from_uid, to_uid, status, created_at)` | `INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, status, created_at) VALUES ('chat_invite', ?, ?, '', json_object('chat_id',?, 'chat_name',?), 'pending', ?)` | 1159 |
| `POST /api/groups/<id>/invite` | `INSERT INTO chat_invites (chat_id, chat_name, from_uid, to_uid, status, created_at)` | 同上 | 1867 |
| `POST /api/notifications/system` | `INSERT INTO announcements (publisher, unit, title, content, target_uid, is_read, created_at) VALUES (?, 'notification', '', ?, ?, 0, ?)` | `INSERT INTO notifications (type, sender_uid, receiver_uid, content, created_at) VALUES ('system', ?, ?, ?, ?)` | 1407 |
| `POST /api/friends/remove`（给对方的通知） | `INSERT INTO announcements (...)` 同上 | 改为写 notifications 表，type='system' | 1301 |
| `POST /api/blacklist/add`（给对方的通知） | `INSERT INTO announcements (...)` 同上 | 改为写 notifications 表，type='system' | 1561 |

#### 2.2 查询通知（读取）

| 路由 | 当前操作 | 改为 | 行号 |
|---|---|---|---|
| `GET /api/notifications` | UNION 三张表 + 应用层合并排序 | `SELECT n.*, u.name as sender_name FROM notifications n LEFT JOIN users u ON n.sender_uid = u.uid WHERE n.receiver_uid=? ORDER BY n.created_at DESC`。返回格式简化：`{id, type, sender_uid, sender_name, content, extra, status, is_read, is_locked, created_at}`，不再需要 `fr_`/`ci_`/`sys_` 前缀 | 1370 |
| `GET /api/notifications/unread-count` | `SELECT COUNT(*) FROM announcements WHERE target_uid=? AND ...` | `SELECT COUNT(*) FROM notifications WHERE receiver_uid=? AND (is_read=0 OR is_read IS NULL)` | 1440 |
| `GET /api/friend-requests`（独立好友申请列表） | `SELECT ... FROM friend_requests WHERE to_uid=? AND status='pending'` | `SELECT n.id, n.sender_uid as from_uid, u.name as from_name, n.extra->>'message' as message, n.created_at FROM notifications n JOIN users u ON n.sender_uid=u.uid WHERE n.receiver_uid=? AND n.type='friend_request' AND n.status='pending' ORDER BY n.created_at DESC` | 1336 |
| `POST /api/friend-request`（重复检查） | `SELECT 1 FROM friend_requests WHERE from_uid=? AND to_uid=? AND status="pending"` | `SELECT 1 FROM notifications WHERE sender_uid=? AND receiver_uid=? AND type='friend_request' AND status='pending'` | 1324 |

#### 2.3 审批操作（状态变更）

| 路由 | 当前操作 | 改为 | 行号 |
|---|---|---|---|
| `POST /api/friend-requests/<id>/approve` | `SELECT * FROM friend_requests WHERE id=? AND to_uid=? AND status="pending"` → `UPDATE friend_requests SET status="approved"` → 双向写 friends | `SELECT * FROM notifications WHERE id=? AND receiver_uid=? AND type='friend_request' AND status='pending'` → `UPDATE notifications SET status='approved' WHERE id=?` → 双向写 user_relations（is_friend=1） | 1341-1353 |
| `POST /api/friend-requests/<id>/reject` | `SELECT * FROM friend_requests WHERE id=? ...` → `UPDATE friend_requests SET status="rejected"` | `SELECT * FROM notifications WHERE id=? ...` → `UPDATE notifications SET status='rejected' WHERE id=?` | 1355-1365 |
| `POST /api/chat-invites/<id>/approve` | `SELECT * FROM chat_invites WHERE id=? ...` → `UPDATE chat_invites SET status="approved"` → 写 group_members | `SELECT * FROM notifications WHERE id=? AND receiver_uid=? AND type='chat_invite' AND status='pending'` → `UPDATE notifications SET status='approved' WHERE id=?` → 从 extra 解析 `chat_id`、`chat_name`，写 group_members + group_messages | 1503-1519 |
| `POST /api/chat-invites/<id>/reject` | `SELECT * FROM chat_invites ...` → `UPDATE chat_invites SET status="rejected"` | `SELECT * FROM notifications WHERE id=? ...` → `UPDATE notifications SET status='rejected' WHERE id=?` | 1521-1531 |

#### 2.4 通知状态管理（已读/删除/锁定）

| 路由 | 当前操作 | 改为 | 行号 |
|---|---|---|---|
| `POST /api/notifications/read` | 根据前缀（`sys_`/`fr_`/`ci_`）路由到三张表分别 UPDATE | `UPDATE notifications SET is_read=1 WHERE id=? AND receiver_uid=?`（统一处理，不再需要前缀判断） | 1412 |
| `POST /api/notifications/read-all` | `UPDATE announcements SET is_read=1 WHERE target_uid=?`（仅 announcements） | `UPDATE notifications SET is_read=1 WHERE receiver_uid=? AND (is_read=0 OR is_read IS NULL)`（覆盖所有类型） | 1431 |
| `POST /api/notifications/delete` | 根据前缀路由到三张表分别 DELETE（sys_ 需检查 is_locked） | `SELECT is_locked FROM notifications WHERE id=? AND receiver_uid=?` → 若 locked 则拒绝 → `DELETE FROM notifications WHERE id=? AND receiver_uid=?`（统一处理） | 1449 |
| `POST /api/notifications/delete-read` | 分别 DELETE 三张表 | `DELETE FROM notifications WHERE receiver_uid=? AND is_read=1 AND (is_locked=0 OR is_locked IS NULL)`（统一处理） | 1475 |
| `POST /api/notifications/lock` | `UPDATE announcements SET is_locked=? WHERE id=? AND target_uid=?`（仅系统通知） | `UPDATE notifications SET is_locked=? WHERE id=? AND receiver_uid=? AND type='system'`（仅 system 类型支持锁定） | 1486 |

#### 2.5 审批端点 URL 变更

当前审批端点映射到旧表的数字 ID：

| 当前 URL | 改为 |
|---|---|
| `POST /api/friend-requests/<int:req_id>/approve` | `POST /api/notifications/<int:notif_id>/approve` |
| `POST /api/friend-requests/<int:req_id>/reject` | `POST /api/notifications/<int:notif_id>/reject` |
| `POST /api/chat-invites/<int:invite_id>/approve` | 统一为 `POST /api/notifications/<int:notif_id>/approve`（type 区分） |
| `POST /api/chat-invites/<int:invite_id>/reject` | 统一为 `POST /api/notifications/<int:notif_id>/reject` |

新端点（合并后）：

```python
@app.route('/api/notifications/<int:notif_id>/approve', methods=['POST'])
@token_required
def approve_notification(notif_id):
    uid = g.current_user['uid']
    conn = get_db()
    n = conn.execute('SELECT * FROM notifications WHERE id=? AND receiver_uid=? AND status="pending"', (notif_id, uid)).fetchone()
    if not n:
        return jsonify({'error': '通知不存在或已处理'}), 404
    if n['type'] == 'friend_request':
        # 双向加好友
        extra = json.loads(n['extra'])
        now = time.time()
        conn.execute("INSERT INTO user_relations (uid,target_uid,is_friend,created_at) VALUES (?,?,1,?) ON CONFLICT(uid,target_uid) DO UPDATE SET is_friend=1, created_at=?",
                     (n['sender_uid'], uid, now, now))
        conn.execute("INSERT INTO user_relations (uid,target_uid,is_friend,created_at) VALUES (?,?,1,?) ON CONFLICT(uid,target_uid) DO UPDATE SET is_friend=1, created_at=?",
                     (uid, n['sender_uid'], now, now))
        conn.execute("UPDATE notifications SET status='approved' WHERE id=?", (notif_id,))
        conn.commit(); conn.close()
        return jsonify({'message': '已同意好友申请'})
    elif n['type'] == 'chat_invite':
        extra = json.loads(n['extra'])
        chat_id = extra.get('chat_id', '')
        chat_name = extra.get('chat_name', '')
        now = time.time()
        conn.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?)', (chat_id, uid, 'member', now))
        conn.execute("UPDATE notifications SET status='approved' WHERE id=?", (notif_id,))
        user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
        user_name = user['name'] if user else uid
        conn.execute("INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)",
                     (chat_id, 'system', f'{user_name} 接受了邀请加入聊天室', 'system', now))
        conn.commit(); conn.close()
        return jsonify({'message': '已接受邀请', 'chat_id': chat_id, 'chat_name': chat_name})
    else:
        return jsonify({'error': '该类型通知不支持审批操作'}), 400
```

拒绝端点：

```python
@app.route('/api/notifications/<int:notif_id>/reject', methods=['POST'])
@token_required
def reject_notification(notif_id):
    uid = g.current_user['uid']
    conn = get_db()
    n = conn.execute('SELECT * FROM notifications WHERE id=? AND receiver_uid=? AND status="pending"', (notif_id, uid)).fetchone()
    if not n:
        return jsonify({'error': '通知不存在或已处理'}), 404
    conn.execute("UPDATE notifications SET status='rejected' WHERE id=?", (notif_id,))
    conn.commit(); conn.close()
    return jsonify({'message': '已拒绝'})
```

#### 2.6 可删除的后端函数

合并后可删除以下函数和路由：

| 函数/路由 | 原因 |
|---|---|
| `POST /api/friend-requests/<int:req_id>/approve` | 替换为 `POST /api/notifications/<int:notif_id>/approve` |
| `POST /api/friend-requests/<int:req_id>/reject` | 替换为 `POST /api/notifications/<int:notif_id>/reject` |
| `POST /api/chat-invites/<int:invite_id>/approve` | 替换为 `POST /api/notifications/<int:notif_id>/approve`（内部按 type 分支） |
| `POST /api/chat-invites/<int:invite_id>/reject` | 替换为 `POST /api/notifications/<int:notif_id>/reject` |
| `GET /api/friend-requests` | 可由前端在读通知时通过 type 过滤替代，如仍需独立接口可改为查 notifications 表 |
| `POST /api/friends/add`（原始直接加好友接口） | 改为操作 user_relations |

### 前端 groups.html 变动

#### 2.7 通知中心相关改动

前端不再需要处理 `fr_`、`ci_`、`sys_` 前缀：

| 改动点 | 说明 |
|---|---|
| 通知 ID 解析 | 所有 `notif.id.startsWith('fr_')` / `startsWith('ci_')` / `startsWith('sys_')` 的判断逻辑改为检查 `notif.type` 字段 |
| 标记已读 | `POST /api/notifications/read` 的 body 直接传 `{id: notif.id}`，不再需要解析前缀 |
| 删除通知 | 同上，直接传数字 ID |
| 锁定通知 | `POST /api/notifications/lock` 仅对 `type='system'` 生效 |
| 审批/拒绝（好友申请） | URL 从 `POST /api/friend-requests/${reqId}/approve` 改为 `POST /api/notifications/${notifId}/approve` |
| 审批/拒绝（聊天邀请） | URL 从 `POST /api/chat-invites/${invId}/approve` 改为 `POST /api/notifications/${notifId}/approve` |

需要在 `notifications.html` 中搜索以下前端代码模式并修改：

```javascript
// 旧模式：前缀判断
// ❌ 删除以下模式
if (notif.id.startsWith('fr_')) { ... }
if (notif.id.startsWith('ci_')) { ... }
if (notif.id.startsWith('sys_')) { ... }

// 新模式：type 判断
// ✅ 改为
if (notif.type === 'friend_request') { ... }
if (notif.type === 'chat_invite') { ... }
if (notif.type === 'system') { ... }
```

```javascript
// 旧模式：带前缀的 ID
await api('/api/notifications/read', { method: 'POST', body: JSON.stringify({ id: notif.id }) });

// ✅ 新模式不变（API 不再解析前缀，直接按数字 ID 操作）
```

```javascript
// 旧模式：不同审批端点
await api('/api/friend-requests/' + reqId + '/approve', { method: 'POST' });
await api('/api/chat-invites/' + invId + '/approve', { method: 'POST' });

// ✅ 新模式：统一端点
await api('/api/notifications/' + notifId + '/approve', { method: 'POST' });
```

#### 2.8 chat_invite 相关通知的 extra 解析

前端在渲染聊天室邀请通知时，需要从 `extra` 字段解析 `chat_id` 和 `chat_name`：

```javascript
// 旧模式：直接取字段
const chatId = notif.chat_id;
const chatName = notif.chat_name;

// ✅ 新模式：从 extra JSON 解析
const extra = JSON.parse(notif.extra || '{}');
const chatId = extra.chat_id;
const chatName = extra.chat_name;
```

#### 2.9 friend_request 相关通知的 content/extra

```javascript
// 旧模式：直接取 message 字段
const message = notif.message;

// ✅ 新模式：从 content 或 extra.message 取
const message = notif.content || (JSON.parse(notif.extra || '{}').message || '');
```

---

## 三、双写迁移策略

两个合并方案都采用相同的三步迁移策略，确保安全过渡：

### 第 1 步：建新表 + 双写

1. 创建 `user_relations` 和 `notifications` 新表
2. 修改所有写操作，同时写入新表和旧表（双写）
3. 修改所有读操作，优先读新表，回退读旧表
4. 部署上线，观察运行状态

### 第 2 步：数据迁移 + 验证

1. 运行迁移脚本，将存量数据从旧表导入新表
2. 对比新表和旧表的数据量、关键字段
3. 在测试环境完整验证所有通知和好友功能

### 第 3 步：清理

1. 确认新表运行正常后，删除旧表
2. 从代码中移除所有双写逻辑和旧表引用
3. 清理 `announcements` 表中残留的通知数据（`target_uid IS NOT NULL` 的记录）

---

## 四、影响范围汇总

| 维度 | user_relations | notifications |
|---|---|---|
| 涉及旧表 | friends, blacklist, call_preferences | friend_requests, chat_invites, announcements（通知部分） |
| 新建表 | user_relations | notifications |
| 涉及后端函数 | 约 12 个 | 约 18 个 |
| 涉及前端文件 | groups.html | notifications.html（主要），groups.html（部分） |
| API 端点变化 | 内部 SQL，URL 不变 | 审批端点 URL 变更（需前端配合） |
| 前端 ID 前缀 | 无影响 | 去掉 fr_/ci_/sys_ 前缀，改用 type 字段 |
| 数据迁移复杂度 | 低（直接映射） | 中（需解析 extra JSON） |
