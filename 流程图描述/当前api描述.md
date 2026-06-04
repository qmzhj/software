3.2前端页面汇总

系统前端采用纯静态 HTML + CSS + JavaScript 实现，无前端框架或构建工具。所有页面通过 main.html 统一承载，左侧为导航菜单，右侧以 iframe 嵌入各功能页面。认证 Token 存储在 localStorage 中，API 请求通过封装的 fetch 包装函数发送。

## 页面列表

| 页面 | 文件名 | 功能说明 |
|------|--------|---------|
| 登录/注册 | login.html | 学号+姓名注册，密码登录，忘记密码 |
| 主框架 | main.html | 左侧导航菜单 + 右侧 iframe 容器 |
| 群组与聊天 | groups.html | 群组管理、聊天室、私聊、群聊、通话 |
| 公告 | announcements.html | 公告列表与查看 |
| 通知 | notifications.html | 好友申请、聊天室邀请、组队申请等审批 |
| 校园查询 | query.html | 用户搜索、赛事、课程表、空闲教室等 |
| 个人设置 | profile.html | 资料编辑、修改密码 |

## 3.2.1认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/register | 注册（验证学号+姓名，设置密码） |
| POST | /api/login | 登录（返回 token） |
| POST | /api/logout | 登出 |
| POST | /api/change_password | 忘记密码/修改密码 |

## 3.2.2私聊

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/messages?with=&lt;uid&gt; | 获取私聊历史 |
| POST | /api/send | 发送私聊消息（支持 multipart 文件上传） |
| POST | /api/messages/revoke/&lt;id&gt; | 撤回私聊消息 |

## 3.2.3群组容器

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/user-groups | 获取当前用户的群组列表 |
| POST | /api/user-groups | 创建自定义群组 |
| GET | /api/user-groups/&lt;id&gt;/detail | 群组详情（成员+关联聊天室） |

## 3.2.4聊天室

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/groups | 获取所有聊天室列表 |
| POST | /api/groups | 创建聊天室 |
| GET | /api/groups/&lt;id&gt;/messages | 聊天室消息历史 |
| POST | /api/groups/&lt;id&gt;/send | 发送群消息 |
| GET | /api/groups/&lt;id&gt;/detail | 聊天室详情（成员列表） |
| POST | /api/groups/&lt;id&gt;/kick | 踢出成员 |
| POST | /api/groups/&lt;id&gt;/admin | 设置/取消管理员 |
| POST | /api/groups/&lt;id&gt;/announcement | 发布公告 |
| POST | /api/groups/&lt;id&gt;/dissolve | 解散聊天室 |
| POST | /api/groups/&lt;id&gt;/invite | 邀请加入聊天室 |
| POST | /api/groups/&lt;id&gt;/leave | 退出聊天室 |
| POST | /api/groups/revoke/&lt;id&gt; | 撤回群消息 |

## 3.2.5通话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/call/invite | 发起通话邀请 |
| POST | /api/call/respond | 响应通话（接听/拒绝/挂断） |
| GET | /api/call/events | 通话事件 SSE 推送 |

## 3.2.6好友与黑名单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/friends | 好友列表 |
| POST | /api/friends/add | 添加好友 |
| POST | /api/friends/remove | 删除好友 |
| POST | /api/friend-request | 发送好友请求 |
| GET | /api/blacklist | 黑名单列表 |
| POST | /api/blacklist/add | 拉黑用户 |
| POST | /api/blacklist/remove | 移出黑名单 |

## 3.2.7系统通知

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/notifications | 获取通知列表 |
| POST | /api/notifications/&lt;id&gt;/approve | 审批同意 |
| POST | /api/notifications/&lt;id&gt;/reject | 审批拒绝 |

## 3.2.8实时推送

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/stream | SSE 长连接（参数：uid, token, mode, target, after） |

## 3.2.9用户

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/search/users?q= | 搜索用户 |
| GET | /api/search/users | 高级搜索（参数：name_or_id, course, class, position, event_id） |
| GET | /api/user/&lt;uid&gt; | 用户详情 |
| GET | /api/user/&lt;uid&gt;/tags | 用户身份标签 |

## 3.2.10校园查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/classrooms/free | 空闲教室查询 |
| GET | /api/events | 赛事列表 |
| GET | /api/course_schedule | 课程表 |
| GET | /api/tutor_duty | 辅导老师值班 |
| GET | /api/teacher_office | 办公室位置 |

## 3.2.11赛事组队

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/events | 发布赛事 |
| POST | /api/events/&lt;id&gt;/groups | 创建赛事小组 |
| GET | /api/events/&lt;id&gt;/groups?show_full= | 查看赛事下的小组列表 |
| PUT | /api/events/groups/&lt;gid&gt;/status | 设置满员/招募中 |
| POST | /api/events/groups/&lt;gid&gt;/apply | 申请加入小组 |
| DELETE | /api/events/groups/&lt;gid&gt;/members/&lt;uid&gt; | 退出小组 |
| GET | /api/events/groups/search?eid=&uid= | 搜索成员所在小组 |
