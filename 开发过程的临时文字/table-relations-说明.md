# `user_groups`、`user_group_members`、`user_group_chats` 三表详解

## 架构总览

这三个表构成了系统的**群组容器模型**。与传统的"聊天室即群组"设计不同，本系统将**群组**（Group）和**聊天室**（Chat）解耦为两个概念，通过一个中间层实现灵活的多对多关系。

```
┌─────────────────────────────────────────────────────────────────────┐
│                         user_groups                                  │
│                    （群组容器 — 组织单元）                              │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  group_id  │  name  │  creator  │  type  │  category        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│           │                        │                                 │
│           ▼                        ▼                                 │
│  ┌──────────────┐      ┌──────────────────┐                         │
│  │user_group_    │      │user_group_       │                         │
│  │members        │      │chats             │                         │
│  │               │      │                  │                         │
│  │group_id       │      │group_id          │                         │
│  │uid            │      │chat_id           │                         │
│  │added_at       │      │chat_name         │                         │
│  └───────┬───────┘      └────────┬─────────┘                         │
│          │                       │                                    │
│          ▼                       ▼                                    │
│    ┌────────┐          ┌──────────────┐                              │
│    │ users  │          │ groups_chat  │                              │
│    │ (用户) │          │（聊天室）     │                              │
│    └────────┘          └──────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘
```

**核心思想**: 一个"群组"是一个容器，它包含一批**成员**（`user_group_members`）和一批**聊天室**（`user_group_chats`）。成员看到容器下的所有聊天室，就可以在里面聊天。

---

## 一、`user_groups` — 群组容器

### 建表语句（`app.py:63-65`）

```sql
CREATE TABLE user_groups (
    group_id   TEXT PRIMARY KEY,   -- 群组唯一 ID
    name       TEXT,               -- 群组名称
    creator    TEXT,               -- 创建者 UID
    created_at REAL,               -- 创建时间戳
    group_type TEXT DEFAULT 'custom',    -- custom（自定义）或 system（系统）
    category   TEXT DEFAULT '自定义'     -- 分类标签：自定义、即时聊天、私聊
);
```

### 功能与作用

| 方面 | 说明 |
|------|------|
| **本质** | 一个**逻辑容器**，本身不存储消息、不提供聊天功能 |
| **作用** | 把成员和聊天室组织在一起，供前端按群组维度展示和管理 |
| **类比** | 类似微信群聊列表中的一个条目 —— 它代表一个聊天单元，但实际的聊天发生在聊天室中 |

### 两种类型

| `group_type` | `category` | 创建方式 | 特点 |
|:---:|:---:|---|---|
| `system` | `即时聊天` | 用户注册/登录时自动创建 | 每个用户一个，成员动态计算（所有非好友用户） |
| `system` | `私聊` | 用户注册/登录时自动创建 | 每个用户一个，成员动态计算（所有好友） |
| `custom` | `自定义`（默认） | 用户手动创建 | 成员和聊天室由用户自行管理 |

### 相关 API

| 方法 | 路由 | 功能 |
|------|------|------|
| `GET` | `/api/user-groups` | 获取当前用户的所有群组（含成员数和聊天室数） |
| `POST` | `/api/user-groups` | 创建新群组（同时添加成员和关联聊天室） |
| `PUT` | `/api/user-groups/<id>` | 修改群组名称和分类 |
| `DELETE` | `/api/user-groups/<id>` | 删除群组（同时清理成员和聊天室关联） |
| `GET` | `/api/user-groups/<id>/detail` | 获取群组详情（成员列表 + 聊天室列表） |

### 前端展现

```
┌──────────────────────┐
│ 📁 即时聊天 · 系统    │  ← user_groups（group_type=system, category=即时聊天）
│    45 个成员 · 0 个聊天室 │
├──────────────────────┤
│ 📁 私聊 · 系统        │  ← user_groups（group_type=system, category=私聊）
│    12 个成员 · 0 个聊天室 │
├──────────────────────┤
│ 📁 项目开发 · 自定义   │  ← user_groups（group_type=custom, category=自定义）
│    5 个成员 · 3 个聊天室  │
└──────────────────────┘
```

---

## 二、`user_group_members` — 群组成员

### 建表语句（`app.py:66-68`）

```sql
CREATE TABLE user_group_members (
    group_id TEXT,        -- 群组 ID，FK → user_groups.group_id
    uid      TEXT,        -- 用户 ID，FK → users.uid
    added_at REAL,        -- 加入时间戳
    PRIMARY KEY(group_id, uid)   -- 一个用户在同一个群组只能有一条记录
);
```

### 功能与作用

| 方面 | 说明 |
|------|------|
| **本质** | 群组与用户之间的**多对多关联表** |
| **作用** | 记录"哪些人在哪个群组中" |
| **约束** | `PRIMARY KEY(group_id, uid)` 确保同一用户不会重复加入同一群组 |

### 与系统群组的特殊关系

系统群组（即时聊天、私聊）虽然也在 `user_group_members` 中有一条**当前用户自己的记录**（由 `ensure_default_groups()` 插入），但它们的**成员列表在获取详情时是动态计算的**，并不从 `user_group_members` 读取完整列表：

| 系统群组类型 | 成员来源 | 计算逻辑（`app.py:792-825`） |
|:---:|---|---|
| `即时聊天` | `users` 表全部用户 | 排除当前用户 + 排除好友 → 所有"陌生人" |
| `私聊` | `friends` 表 | 当前用户的所有好友 |
| `custom`（普通） | `user_group_members` 表 | 直接查询该群组的记录 |

**这意味着**: 对于系统群组，`user_group_members` 表只起"占位"作用（证明用户有这个群组），真正的成员列表是运行时从其他表计算出来的。

### 成员操作 API

| 方法 | 路由 | 功能 |
|------|------|------|
| `POST` | `/api/user-groups/<id>/members` | 向群组添加成员（批量） |
| `DELETE` | `/api/user-groups/<id>/members/<uid>` | 从群组移除成员 |

**限制**: 系统群组（`group_type = 'system'`）不可通过这两个接口修改成员。

### 关键查询

```sql
-- 获取用户所在的所有群组（app.py:663-666）
SELECT g.* FROM user_groups g
JOIN user_group_members gm ON g.group_id = gm.group_id
WHERE gm.uid = ?
ORDER BY g.created_at DESC;

-- 获取群组成员数量（排除当前用户，app.py:674）
SELECT COUNT(*) FROM user_group_members
WHERE group_id = ? AND uid != ?;

-- 获取群组的完整成员信息（普通群组，app.py:819-823）
SELECT u.uid, u.name, u.role, gm.added_at
FROM user_group_members gm
JOIN users u ON gm.uid = u.uid
WHERE gm.group_id = ?
ORDER BY u.name;
```

---

## 三、`user_group_chats` — 群组-聊天室关联

### 建表语句（`app.py:69-71`）

```sql
CREATE TABLE user_group_chats (
    group_id TEXT,        -- 群组 ID，FK → user_groups.group_id
    chat_id  TEXT,        -- 聊天室 ID，FK → groups_chat.group_id
    chat_name TEXT,       -- 聊天室在此群组中的显示别名
    PRIMARY KEY(group_id, chat_id)  -- 同一聊天室在同一群组只能关联一次
);
```

### 功能与作用

| 方面 | 说明 |
|------|------|
| **本质** | 群组与聊天室之间的**多对多关联表** |
| **作用** | 记录"哪些聊天室属于哪个群组" |
| **额外字段** | `chat_name` 允许聊天室在不同群组中有不同的显示名称 |
| **约束** | `PRIMARY KEY(group_id, chat_id)` 防止重复关联 |

### 核心设计

这是实现群组-聊天室解耦的关键：一个**聊天室**（`groups_chat`）可以属于**多个群组**（`user_groups`）。例如：

```
群组 "项目A" ────┬─── 聊天室 "技术讨论" ───┬─── 群组 "项目B"
                 │                        │
                 └─── 聊天室 "休闲水群"     │
                                          └─── 群组 "全员大群"
```

### 关联时机

聊天室与群组的关联发生在以下场景：

| 场景 | 代码位置 |
|------|---------|
| **创建群组时同时关联**：前端创建群组时可以指定要关联的聊天室列表 | `app.py:719-728` |
| **将已有聊天室加入群组**：在群组详情页点击"添加聊天室" | `app.py:849-875` |
| **在群组内创建新聊天室**：新建聊天室并自动关联到当前群组 | `app.py:920-921` |

### 聊天室关联操作 API

| 方法 | 路由 | 功能 |
|------|------|------|
| `POST` | `/api/user-groups/<id>/chats` | 将已有聊天室关联到群组 |
| `DELETE` | `/api/user-groups/<id>/chats/<chat_id>` | 从群组移除聊天室关联 |
| `POST` | `/api/user-groups/<id>/create-chat` | 创建新聊天室并关联到群组 |

**限制**: 系统群组不可通过以上接口修改聊天室关联。

### 关键查询

```sql
-- 获取群组的聊天室数量（app.py:671）
SELECT COUNT(*) FROM user_group_chats WHERE group_id = ?;

-- 获取群组的聊天室列表（含实际聊天室名称，app.py:828-831）
SELECT ugc.*, gc.name as chat_room_name
FROM user_group_chats ugc
LEFT JOIN groups_chat gc ON ugc.chat_id = gc.group_id
WHERE ugc.group_id = ?;
```

`chat_room_name` 取自 `groups_chat.name`（聊天室真实名称），而 `chat_name` 是群组中的别名。如果聊天室已被删除，`chat_room_name` 为 `NULL`，前端会退而使用 `chat_name`。

---

## 四、三表协作的数据流

### 创建群组流程

```
前端 POST /api/user-groups
  │
  ├→ 1. INSERT INTO user_groups           ← 写入群组基本信息
  │    (group_id, name, creator, ...)
  │
  ├→ 2. INSERT INTO user_group_members    ← 添加创建者自己到成员表
  │    (group_id, creator_uid, now)
  │
  ├→ 3. INSERT INTO user_group_members    ← 逐一添加其他成员
  │    (group_id, member_uid, now) (×N)
  │
  └→ 4. INSERT INTO user_group_chats      ← 逐一关联已有聊天室
       (group_id, chat_id, chat_name) (×N)
```

### 获取群组列表流程

```
前端 GET /api/user-groups
  │
  ├→ 1. SELECT user_groups.*
  │       JOIN user_group_members
  │       WHERE uid = ?                    ← 查用户所在的所有群组
  │
  ├→ 2. FOR each group:
  │       SELECT COUNT(*) FROM user_group_chats WHERE group_id = ?
  │                                       ← 获取聊天室数
  │
  └→ 3. FOR each group:
          SELECT COUNT(*) FROM user_group_members
          WHERE group_id = ? AND uid != ?
                                          ← 获取其他成员数
```

### 获取群组详情流程

```
前端 GET /api/user-groups/<id>/detail
  │
  ├→ 1. SELECT * FROM user_groups WHERE group_id = ?   ← 群组基本信息
  │
  ├→ 2. 检查 user_group_members 是否有当前用户记录      ← 权限验证
  │
  ├→ 3. 获取成员列表:
  │     如果是 system + 即时聊天 → 从 users 表动态计算（排除好友）
  │     如果是 system + 私聊    → 从 friends 表查询
  │     如果是 custom           → 从 user_group_members JOIN users 查询
  │
  └→ 4. 获取聊天室列表:
         SELECT FROM user_group_chats LEFT JOIN groups_chat
         WHERE group_id = ?
```

### 删除群组流程

```
前端 DELETE /api/user-groups/<id>
  │
  ├→ 1. DELETE FROM user_group_chats     ← 先删聊天室关联
  ├→ 2. DELETE FROM user_group_members   ← 再删成员记录
  └→ 3. DELETE FROM user_groups          ← 最后删群组本身
```

---

## 五、前端交互对照

### groups.html 中对应关系

| 前端操作 | 涉及表 | API 路由 |
|---------|--------|---------|
| 查看群组列表 | `user_groups` + `user_group_members` | `GET /api/user-groups` |
| 新建群组 | `user_groups` + `user_group_members` + `user_group_chats` | `POST /api/user-groups` |
| 进入群组详情 | `user_groups` + `user_group_members` / `friends` / `users` + `user_group_chats` | `GET /api/user-groups/<id>/detail` |
| 添加成员 | `user_group_members` | `POST /api/user-groups/<id>/members` |
| 移除成员 | `user_group_members` | `DELETE /api/user-groups/<id>/members/<uid>` |
| 添加聊天室 | `user_group_chats` | `POST /api/user-groups/<id>/chats` |
| 移除聊天室 | `user_group_chats` | `DELETE /api/user-groups/<id>/chats/<chat_id>` |
| 在群组内创建聊天室 | `groups_chat` + `user_group_chats` | `POST /api/user-groups/<id>/create-chat` |

### 前端关键代码片段

```javascript
// groups.html:344 — 加载群组列表（遍历三表聚合数据）
const groups = await api("/api/user-groups");

// groups.html:371 — 进入群组详情（获取成员+聊天室）
const detail = await api(`/api/user-groups/${groupId}/detail`);
```

---

## 六、总结

| 表 | 角色 | 对应实体 | 数据来源 | 特点 |
|----|------|---------|---------|------|
| `user_groups` | **容器定义** | 群组本身 | 用户创建或系统自动生成 | 两种类型（system/custom），定义了群组元数据 |
| `user_group_members` | **成员关系** | 群组与用户的多对多 | 用户添加或系统自动加入 | 系统群组只存当前用户，其他成员动态计算 |
| `user_group_chats` | **聊天室关系** | 群组与聊天室的多对多 | 用户关联或创建时绑定 | 实现群组与聊天室解耦，支持同一聊天室属于多个群组 |

**设计模式**: 这是一个典型的**容器-内容**模式 —— `user_groups` 是容器，`user_group_members` 和 `user_group_chats` 是两个维度的关联表，分别将"人"和"聊天室"组织到容器中。这种设计的优势在于：

1. **灵活组织**：同一聊天室可以出现在多个群组中，同一用户可以在不同群组中拥有不同角色
2. **关注点分离**：群组的成员管理与聊天室的成员管理相互独立
3. **系统/自定义统一**：系统群组（即时聊天、私聊）和自定义群组共用同一套表结构，只是成员来源不同
