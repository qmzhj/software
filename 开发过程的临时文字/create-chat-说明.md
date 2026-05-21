# 聊天室创建功能逻辑说明

## 概述

系统中有**两个层级**的聊天室创建方式，对应两张不同的表：

| 方式 | 后端接口 | 前端入口 | 写入的表 |
|------|---------|---------|---------|
| 独立创建聊天室 | `POST /api/groups` | `index.html`（旧版 UI） | `groups_chat` + `group_members` |
| 在群组内创建聊天室 | `POST /api/user-groups/<id>/create-chat` | `groups.html` → 群组详情 → 创建聊天室 | `groups_chat` + `group_members` + `user_group_chats` |

两者的核心区别：独立创建只生成聊天室本身；在群组内创建则额外将聊天室**关联到所属群组容器**。

---

## 一、独立创建聊天室

### 前端流程

**入口**: `groups.html` 中未直接暴露此功能，由 `index.html`（旧版 UI）或 API 调用触发。

### 后端逻辑（`app.py:1110-1138`）

```python
@app.route('/api/groups', methods=['POST'])
@token_required
def create_group():
    creator = g.current_user['uid']
    data = request.get_json()
    name = data.get('name','').strip()
    members = data.get('members',[])
    category = data.get('category','办公群')
    if not name or len(members) < 1:
        return jsonify({'error':'名称和成员不能为空'}),400
    group_id = secrets.token_hex(8)
    ...
```

### 执行步骤

```
POST /api/groups  { name, members, category }
  │
  ├─ 1. 校验参数
  │    名称非空 + 成员≥1
  │
  ├─ 2. 生成 ID
  │    group_id = secrets.token_hex(8)  →  16 位十六进制随机字符串
  │
  ├─ 3. 验证成员存在性
  │    FOR each member: SELECT uid FROM users WHERE uid=?
  │    有任一成员不存在则返回 404
  │
  ├─ 4. 写入 groups_chat 表
  │    INSERT INTO groups_chat
  │      (group_id, name, creator, created_at, group_type, category)
  │    VALUES (?, '聊天室名', '创建者uid', now, 'custom', '办公群')
  │
  └─ 5. 写入 group_members 表（逐一添加）
       INSERT INTO group_members (group_id, uid, role, joined_at)
       VALUES (?, '创建者uid', 'admin', now)    ← 创建者为 admin
       VALUES (?, '成员uid',   'member', now)   × N  ← 其他成员为 member
```

### 涉及的表

| 表 | 写入内容 | 作用 |
|----|---------|------|
| `groups_chat` | 聊天室基本信息（ID、名称、创建者、时间、类型） | 定义聊天室 |
| `group_members` | 聊天室成员（ID、用户ID、角色、加入时间） | 记录谁在聊天室中 |

**注意**: 独立创建不会将聊天室关联到任何 `user_groups` 容器，因此它在群组列表页中不可见，只能通过聊天室列表直接访问。

---

## 二、在群组内创建聊天室（核心流程）

这是 `groups.html` 中的主要创建方式。

### 前端入口

**文件**: `groups.html:293-306`（模态框）、`groups.html:727-745`（JS 逻辑）

#### 模态框 HTML

```html
<!-- groups.html:293-306 -->
<div class="modal-overlay" id="createChatModal">
  <div class="modal">
    <h3>💬 创建聊天室</h3>
    <input id="newChatName" placeholder="聊天室名称" />
    <p style="...">在当前群组内创建一个新的聊天室</p>
    <div class="btn-row">
      <button class="btn-cancel" onclick="closeModal('createChatModal')">取消</button>
      <button class="btn-primary" onclick="createChatInGroup()">创建</button>
    </div>
  </div>
</div>
```

#### JavaScript 逻辑

```javascript
// groups.html:727-731 — 显示模态框
async function showCreateChatModal() {
  if (!selectedGroup) return;
  document.getElementById("newChatName").value = "";
  showModal("createChatModal");
}

// groups.html:733-745 — 创建聊天室
async function createChatInGroup() {
  if (!selectedGroup) return;
  const name = document.getElementById("newChatName").value.trim();
  if (!name) { alert("请输入聊天室名称"); return; }
  try {
    await api("/api/user-groups/" + selectedGroup.group_id + "/create-chat", {
      method: "POST",
      body: JSON.stringify({ name })
    });
    closeModal("createChatModal");
    enterGroup(selectedGroup.group_id);  // ← 刷新当前群组详情
  } catch (e) { alert(e.message); }
}
```

### 后端逻辑（`app.py:913-943`）

```python
@app.route('/api/user-groups/<group_id>/create-chat', methods=['POST'])
@token_required
def create_chat_in_group(group_id):
    uid = g.current_user['uid']
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '聊天室名称不能为空'}), 400

    conn = get_db()
    group = conn.execute('SELECT * FROM user_groups WHERE group_id=?',
                         (group_id,)).fetchone()
    if not group:
        return jsonify({'error': '群组不存在'}), 404

    try:
        now = time.time()
        chat_id = secrets.token_hex(8)
        category = group.get('category', '自定义')
        # ① 创建聊天室
        conn.execute('INSERT INTO groups_chat VALUES (?,?,?,?,?,?)',
                     (chat_id, name, uid, now, 'custom', category))
        # ② 创建者加入聊天室
        conn.execute('INSERT INTO group_members VALUES (?,?,?,?)',
                     (chat_id, uid, 'admin', now))
        # ③ 关联到群组容器
        conn.execute('INSERT INTO user_group_chats VALUES (?,?,?)',
                     (group_id, chat_id, name))
        conn.commit()
        return jsonify({'message': '聊天室创建成功', 'chat_id': chat_id}), 201
    except Exception as e:
        return jsonify({'error': f'创建失败: {str(e)}'}), 500
    finally:
        conn.close()
```

### 执行步骤

```
POST /api/user-groups/{group_id}/create-chat  { name }
  │
  ├─ 1. 校验参数
  │    聊天室名称非空
  │
  ├─ 2. 检查群组存在
  │    SELECT * FROM user_groups WHERE group_id = ?
  │    不存在 → 404
  │
  ├─ 3. 生成 ID
  │    chat_id = secrets.token_hex(8)  →  16 位十六进制随机字符串
  │
  ├─ 4. 写入 groups_chat 表（创建聊天室）
  │    INSERT INTO groups_chat
  │      (group_id, name, creator, created_at, group_type, category)
  │    VALUES (chat_id, name, 当前用户uid, now, 'custom', 群组的category)
  │
  ├─ 5. 写入 group_members 表（创建者自动加入）
  │    INSERT INTO group_members
  │      (group_id, uid, role, joined_at)
  │    VALUES (chat_id, 当前用户uid, 'admin', now)
  │
  └─ 6. 写入 user_group_chats 表（关联到群组）
       INSERT INTO user_group_chats
         (group_id, chat_id, chat_name)
       VALUES (群组ID, chat_id, 聊天室名称)
```

### 涉及的表

| 表 | 写入内容 | 作用 |
|----|---------|------|
| `groups_chat` | 聊天室基本信息 | 定义聊天室本体 |
| `group_members` | 创建者以 admin 身份加入 | 确保创建者能进入聊天室 |
| `user_group_chats` | 群组ID + 聊天室ID + 别名 | 将聊天室关联到所属群组容器 |

---

## 三、两种创建方式的对比

| 对比项 | 独立创建 (`POST /api/groups`) | 群组内创建 (`POST .../create-chat`) |
|-------|------------------------------|-----------------------------------|
| **前端触发** | `index.html`（旧版 UI） | `groups.html` 群组详情页 |
| **所需参数** | `name` + `members[]` | `name`（群组 ID 来自 URL） |
| **校验要求** | 成员数 ≥ 1 | 群组必须存在 |
| **创建者角色** | `admin` | `admin` |
| **其他成员** | 需前端传入 | 不自动添加，仅创建者自己加入 |
| **关联群组容器** | ❌ 不关联 | ✅ 自动关联到当前群组 |
| **group_type** | `custom` | `custom` |
| **category** | 前端传入（默认`办公群`） | 继承自所属群组的 category |
| **ID 生成** | `secrets.token_hex(8)` | `secrets.token_hex(8)` |

---

## 四、在群组列表页中的可见性

| 场景 | 在群组列表页可见？ | 说明 |
|------|-----------------|------|
| 独立创建的聊天室 | ❌ 不可见 | 没有关联 `user_groups`，不出现在任何群组容器下 |
| 群组内创建的聊天室 | ✅ 可见 | 通过 `user_group_chats` 关联到特定群组 |
| 将独立聊天室关联到群组 | ✅ 变为可见 | 通过 `添加聊天室` 功能写入 `user_group_chats` |

---

## 五、数据流示意图

```
                           创建聊天室
                              │
               ┌──────────────┴──────────────┐
               │                             │
        独立创建方式                    群组内创建方式
               │                             │
               ▼                             ▼
     POST /api/groups           POST /api/user-groups/{id}/create-chat
               │                             │
               │                             ├─ 校验群组是否存在
               │                             │
               ├─ 校验名称+成员               │
               │                             │
               └─ ① INSERT groups_chat       ├─ ① INSERT groups_chat
                  (group_id, name,           │   (chat_id, name,
                   creator, created_at,       │    creator, created_at,
                   group_type, category)      │    group_type, category)
                              │               │
               ┌──────────────┘               │
               ▼                              │
        ② INSERT group_members                ├─ ② INSERT group_members
           (group_id, uid, role,              │   (chat_id, uid,
            joined_at)                        │    'admin', now)
           创建者→admin                        │
           成员  →member                       │
                                              └─ ③ INSERT user_group_chats
                                                (群组ID, chat_id, chat_name)
                                                ← 关键区别：关联到群组

  完成后用户可通过                              完成后在群组详情页
  /api/groups 列表看到                         直接看到新聊天室
```

---

## 六、注意事项

1. **`groups_chat` 表的主键字段名是 `group_id` 而非 `chat_id`**，代码中两种变量名混用，需注意区分。

2. **群组内创建的聊天室只有创建者一人**（以 admin 身份加入），其他群组成员需要**手动加入**聊天室才能发言。

3. **创建成功后前端自动刷新群组详情**（调用 `enterGroup()`），以显示新的聊天室。

4. **独立创建的聊天室可以通过"关联聊天室"功能加入群组**——在群组详情页点击"关联聊天室"选择已有聊天室，会写入 `user_group_chats` 表建立关联。

5. **删除群组时，其下的聊天室不会被删除**——`DELETE /api/user-groups/<id>` 只删除 `user_group_chats` 中的关联记录和 `user_group_members` 中的成员记录，`groups_chat` 中的聊天室本身不受影响。
