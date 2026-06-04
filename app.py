import sqlite3, hashlib, secrets, re, time, os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g, send_from_directory, Response
from functools import wraps
from werkzeug.utils import secure_filename
import json
import uuid
import os
app = Flask(__name__, static_folder='static', static_url_path='')
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

SALT = "CampusFakeSalt2024!"
tokens = {}
# 内存存储验证码和过期时间
verification_codes = {}

# ---------- 数据库初始化 ----------
def init_db():
    conn = sqlite3.connect('campus.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (uid TEXT PRIMARY KEY, name TEXT, password TEXT, role TEXT,
                  locked INTEGER DEFAULT 0, unlock_time TEXT, login_fails INTEGER DEFAULT 0, registed INTEGER DEFAULT 0,phone TEXT )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sender TEXT, receiver TEXT, content TEXT, msg_type TEXT DEFAULT 'text',
                  file_path TEXT, file_name TEXT, file_size INTEGER,
                  status TEXT DEFAULT 'sent', timestamp REAL, revoked INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS groups_chat
                 (group_id TEXT PRIMARY KEY, name TEXT, creator TEXT, created_at REAL,
                  group_type TEXT DEFAULT 'custom', category TEXT DEFAULT '办公群')''')
    c.execute('''CREATE TABLE IF NOT EXISTS group_members
                 (group_id TEXT, uid TEXT, role TEXT DEFAULT 'member', joined_at REAL,
                  PRIMARY KEY(group_id, uid))''')
    c.execute('''CREATE TABLE IF NOT EXISTS group_messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  group_id TEXT, sender TEXT, content TEXT, msg_type TEXT DEFAULT 'text',
                  file_path TEXT, file_name TEXT, file_size INTEGER,
                  status TEXT DEFAULT 'sent', timestamp REAL, revoked INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS announcements
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, publisher TEXT, unit TEXT,
                  title TEXT, content TEXT, attachments TEXT, created_at REAL,
                  modified_at REAL, modifier TEXT)''')
    # Migration: add notification columns if not present
    try:
        c.execute('ALTER TABLE announcements ADD COLUMN is_read INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE announcements ADD COLUMN target_uid TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE announcements ADD COLUMN is_locked INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE friend_requests ADD COLUMN is_read INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE chat_invites ADD COLUMN is_read INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE group_members ADD COLUMN call_notify INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE events ADD COLUMN creator_uid TEXT')
    except:
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS call_preferences
                 (uid TEXT NOT NULL, target_uid TEXT NOT NULL,
                  call_notify INTEGER DEFAULT 0,
                  PRIMARY KEY (uid, target_uid))''')
    c.execute('''CREATE TABLE IF NOT EXISTS classrooms
                 (id TEXT PRIMARY KEY, building TEXT, floor INTEGER, seats INTEGER,
                  has_media INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS course_schedule
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, course_name TEXT, teacher TEXT,
                  classroom_id TEXT, day_of_week INTEGER, start_time TEXT, end_time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT,
                  start_time TEXT, end_time TEXT, location TEXT, target TEXT,
                  organizer TEXT, description TEXT, creator_uid TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tutor_duty
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_name TEXT, teacher_uid TEXT,
                  college TEXT, duty_date TEXT, start_time TEXT, end_time TEXT,
                  location TEXT, contact TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS teacher_office
                 (uid TEXT PRIMARY KEY, name TEXT, college TEXT, title TEXT,
                  office TEXT, phone TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_groups
                 (group_id TEXT PRIMARY KEY, name TEXT, creator TEXT, created_at REAL,
                  group_type TEXT DEFAULT 'custom', category TEXT DEFAULT '自定义')''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_group_members
                 (group_id TEXT, uid TEXT, added_at REAL,
                  PRIMARY KEY(group_id, uid))''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_group_chats
                 (group_id TEXT, chat_id TEXT, chat_name TEXT,
                  PRIMARY KEY(group_id, chat_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_relations
                 (uid TEXT, target_uid TEXT,
                  is_friend INTEGER DEFAULT 0,
                  is_blocked INTEGER DEFAULT 0,
                  call_notify INTEGER DEFAULT 0,
                  created_at REAL,
                  PRIMARY KEY(uid, target_uid))''')
    c.execute('''CREATE TABLE IF NOT EXISTS friends
                 (uid TEXT, friend_uid TEXT, created_at REAL,
                  PRIMARY KEY(uid, friend_uid))''')
    c.execute('''CREATE TABLE IF NOT EXISTS lesson
                 (lesson_id TEXT PRIMARY KEY, lesson_name TEXT, teacher_uid TEXT,
                  schedule_weekday TEXT, schedule_period TEXT, schedule_weeks TEXT,
                  location TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS lesson_stu
                 (lesson_id TEXT, stu_uid TEXT,
                  PRIMARY KEY(lesson_id, stu_uid))''')
    # ===== 身份系统：班级/职位/课程职位 =====
    c.execute('''CREATE TABLE IF NOT EXISTS classes
                 (class_id TEXT PRIMARY KEY,
                  class_name TEXT, grade TEXT, major TEXT, department TEXT,
                  level TEXT DEFAULT 'class')''')
    c.execute('''CREATE TABLE IF NOT EXISTS class_positions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  class_id TEXT NOT NULL, uid TEXT NOT NULL, position_name TEXT NOT NULL,
                  FOREIGN KEY (class_id) REFERENCES classes(class_id),
                  FOREIGN KEY (uid) REFERENCES users(uid))''')
    c.execute('''CREATE TABLE IF NOT EXISTS lesson_positions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  lesson_id TEXT NOT NULL, uid TEXT NOT NULL, position_name TEXT NOT NULL,
                  FOREIGN KEY (lesson_id) REFERENCES lesson(lesson_id),
                  FOREIGN KEY (uid) REFERENCES users(uid))''')
    c.execute('''CREATE TABLE IF NOT EXISTS class_stu
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  class_id TEXT NOT NULL, uid TEXT NOT NULL,
                  FOREIGN KEY (class_id) REFERENCES classes(class_id),
                  FOREIGN KEY (uid) REFERENCES users(uid))''')
    # 兼容旧数据库：添加 description 列（如果不存在）
    try:
        c.execute("ALTER TABLE users ADD COLUMN description TEXT DEFAULT ''")
    except Exception:
        pass  # 列已存在
    c.execute('''CREATE TABLE IF NOT EXISTS blacklist
                 (uid TEXT, blocked_uid TEXT,
                  PRIMARY KEY(uid, blocked_uid))''')
    c.execute('''CREATE TABLE IF NOT EXISTS friend_requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  from_uid TEXT, to_uid TEXT, message TEXT,
                  status TEXT DEFAULT 'pending', created_at REAL,
                  is_read INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_invites
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  chat_id TEXT, chat_name TEXT, from_uid TEXT, to_uid TEXT,
                  status TEXT DEFAULT 'pending', created_at REAL,
                  is_read INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  type TEXT NOT NULL,
                  sender_uid TEXT NOT NULL,
                  receiver_uid TEXT,
                  content TEXT,
                  extra TEXT DEFAULT '{}',
                  status TEXT DEFAULT '',
                  is_read INTEGER DEFAULT 0,
                  is_locked INTEGER DEFAULT 0,
                  created_at REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS events_groups
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id INTEGER NOT NULL, group_name TEXT NOT NULL,
                  leader_uid TEXT NOT NULL, status TEXT DEFAULT 'recruiting',
                  max_members INTEGER DEFAULT 4, description TEXT,
                  created_at TEXT DEFAULT (datetime('now', 'localtime')),
                  FOREIGN KEY (event_id) REFERENCES events(id),
                  FOREIGN KEY (leader_uid) REFERENCES users(uid))''')
    c.execute('''CREATE TABLE IF NOT EXISTS events_groups_members
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  group_id INTEGER NOT NULL, member_uid TEXT NOT NULL,
                  joined_at TEXT DEFAULT (datetime('now', 'localtime')),
                  FOREIGN KEY (group_id) REFERENCES events_groups(id),
                  FOREIGN KEY (member_uid) REFERENCES users(uid),
                  UNIQUE(group_id, member_uid))''')
    # 数据迁移：notifications（存量数据导入）
    row = c.execute("SELECT COUNT(*) FROM notifications").fetchone()
    if row and row[0] == 0:
        c.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, status, is_read, created_at) SELECT 'friend_request', from_uid, to_uid, message, '{}', status, is_read, created_at FROM friend_requests")
        c.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, status, is_read, created_at) SELECT 'chat_invite', from_uid, to_uid, '', json_object('chat_id', chat_id, 'chat_name', chat_name), status, is_read, created_at FROM chat_invites")
        c.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, is_read, is_locked, created_at) SELECT 'system', publisher, target_uid, content, '{}', is_read, is_locked, created_at FROM announcements WHERE target_uid IS NOT NULL AND target_uid != ''")
    # 数据迁移：friends/blacklist/call_preferences → user_relations
    row = c.execute("SELECT COUNT(*) FROM user_relations").fetchone()
    if row and row[0] == 0:
        c.execute("INSERT OR IGNORE INTO user_relations (uid, target_uid, is_friend, created_at) SELECT uid, friend_uid, 1, created_at FROM friends")
        for buid, btarget in c.execute("SELECT uid, blocked_uid FROM blacklist").fetchall():
            c.execute("INSERT INTO user_relations (uid, target_uid, is_blocked) VALUES (?,?,1) ON CONFLICT(uid,target_uid) DO UPDATE SET is_blocked=1", (buid, btarget))
        for puid, ptarget, pnotify in c.execute("SELECT uid, target_uid, call_notify FROM call_preferences").fetchall():
            c.execute("INSERT INTO user_relations (uid, target_uid, call_notify) VALUES (?,?,?) ON CONFLICT(uid,target_uid) DO UPDATE SET call_notify=?", (puid, ptarget, pnotify, pnotify))
    conn.commit()
    _seed_data(conn)
    conn.close()
def _load_users_from_json(filepath):
    """
    从JSON文件加载用户数据
    users:(uid,name,password,role,locked)
    """
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            users_data = []
            for user in data:
                uid = user.get('uid', '')
                name = user.get('name', '')
                if uid and name:  # 确保必需字段存在
                    # 密码默认为123456，角色默认为student
                    password=hash_password('123456')
                    role = get_role_by_uid(uid)
                    users_data.append((uid, name, password, role,0,0,'',0,''))
            return users_data
        else:
            print(f"警告: 文件 {filepath} 不存在，将使用默认数据")
            return None
    except Exception as e:
        print(f"加载用户数据时出错: {e}")
        return None

def _load_lessons_from_json(filepath, conn):
    """
    从lessons.json加载课程数据，自动生成课程uid，插入到lesson和lesson_stu表
    """
    try:
        if not os.path.exists(filepath):
            print(f"警告: 文件 {filepath} 不存在")
            return
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        c = conn.cursor()
        for lesson in data:
            lesson_id = 'lesson_' + secrets.token_hex(8)
            lesson_name = lesson.get('lesson_name', '')
            teacher_uid = lesson.get('teacher_uid', '')
            schedule_weekday = lesson.get('schedule_weekday', '')
            schedule_period = lesson.get('schedule_period', '')
            schedule_weeks = lesson.get('schedule_weeks', '')
            location = lesson.get('location', '')
            stu_uids = lesson.get('stu_uids', [])
            c.execute('INSERT INTO lesson VALUES (?,?,?,?,?,?,?)',
                      (lesson_id, lesson_name, teacher_uid,
                       schedule_weekday, schedule_period, schedule_weeks, location))
            for stu_uid in stu_uids:
                c.execute('INSERT OR IGNORE INTO lesson_stu VALUES (?,?)',
                          (lesson_id, str(stu_uid)))
        print(f"已从 {filepath} 导入 {len(data)} 门课程数据")
    except Exception as e:
        print(f"加载课程数据时出错: {e}")

def _load_classes_from_json(filepath, conn):
    """从 class.json 加载班级数据，写入 classes / class_positions / class_stu 表"""
    try:
        if not os.path.exists(filepath):
            print(f"警告: 文件 {filepath} 不存在")
            return
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        c = conn.cursor()
        for cls in data:
            class_id = cls.get('class_name', '')
            grade = cls.get('grade', '')
            major = cls.get('major', '')
            department = cls.get('department', '')
            level = 'grade' if '级' in class_id else 'class'
            c.execute('INSERT OR IGNORE INTO classes VALUES (?,?,?,?,?,?)',
                      (class_id, class_id, grade, major, department, level))
            cadre = cls.get('class_cadre', {})
            for position_name, uid in cadre.items():
                c.execute('INSERT OR IGNORE INTO class_positions (class_id, uid, position_name) VALUES (?,?,?)',
                          (class_id, uid, position_name))
            for uid in cls.get('class_member', []):
                c.execute('INSERT OR IGNORE INTO class_stu (class_id, uid) VALUES (?,?)',
                          (class_id, uid))
        conn.commit()
        print(f"已从 {filepath} 导入班级数据")
    except Exception as e:
        print(f"加载班级数据时出错: {e}")

def _load_events_from_json(filepath, conn):
    """从 events.json 加载赛事数据，插入 events 表"""
    try:
        if not os.path.exists(filepath):
            print(f"警告: 文件 {filepath} 不存在")
            return
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        c = conn.cursor()
        for ev in data:
            c.execute('INSERT INTO events (id, name, type, start_time, end_time, location, target, organizer, description, creator_uid) VALUES (?,?,?,?,?,?,?,?,?,?)',
                      (None,
                       ev.get('name', ''),
                       ev.get('type', ''),
                       ev.get('start_time', ''),
                       ev.get('end_time', ''),
                       ev.get('location', ''),
                       ev.get('target', ''),
                       ev.get('organizer', ''),
                       ev.get('description', ''),
                       ev.get('creator_uid', '')))
        conn.commit()
        print(f"已从 {filepath} 导入赛事数据")
    except Exception as e:
        print(f"加载赛事数据时出错: {e}")

def _seed_event_groups(conn):
    """为每个赛事创建 1-2 个示例小组，方便演示"""
    c = conn.cursor()
    events = c.execute('SELECT id, name FROM events').fetchall()
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for ev in events:
        eid = ev[0]
        ename = ev[1]
        if 'ROBOTAC' in ename:
            c.execute("INSERT INTO events_groups (event_id, group_name, leader_uid, status, max_members, description, created_at) VALUES (?,?,?,?,?,?,?)",
                      (eid, '空地协同组', '202421326577', 'recruiting', 4, '专注Sim2Real仿真策略，有ROS经验优先', now))
            gid1 = c.lastrowid
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid1, '202421326577', now))
            c.execute("INSERT INTO events_groups (event_id, group_name, leader_uid, status, max_members, description, created_at) VALUES (?,?,?,?,?,?,?)",
                      (eid, '硬件先锋队', '202421324917', 'recruiting', 4, '负责机器人硬件搭建与调试', now))
            gid2 = c.lastrowid
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid2, '202421324917', now))
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid2, '202421326351', now))
        elif '创新大赛' in ename:
            c.execute("INSERT INTO events_groups (event_id, group_name, leader_uid, status, max_members, description, created_at) VALUES (?,?,?,?,?,?,?)",
                      (eid, '智联校园团队', '202421324906', 'recruiting', 5, '基于IoT的智慧校园解决方案，招募后端开发', now))
            gid3 = c.lastrowid
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid3, '202421324906', now))
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid3, '202421324921', now))
            c.execute("INSERT INTO events_groups (event_id, group_name, leader_uid, status, max_members, description, created_at) VALUES (?,?,?,?,?,?,?)",
                      (eid, 'AI教育创新', '202421326580', 'recruiting', 5, 'AI赋能基础教育，需要擅长PPT和路演的同学', now))
            gid4 = c.lastrowid
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid4, '202421326580', now))
        elif '三下乡' in ename:
            c.execute("INSERT INTO events_groups (event_id, group_name, leader_uid, status, max_members, description, created_at) VALUES (?,?,?,?,?,?,?)",
                      (eid, '筑梦支教队', '202421324916', 'recruiting', 6, '前往梅州开展暑期支教，招募授课志愿者', now))
            gid5 = c.lastrowid
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid5, '202421324916', now))
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid5, '202421327193', now))
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid5, '202421327006', now))
            c.execute("INSERT INTO events_groups (event_id, group_name, leader_uid, status, max_members, description, created_at) VALUES (?,?,?,?,?,?,?)",
                      (eid, '乡村振兴调研团', '202411310530', 'recruiting', 6, '赴清远调研乡村振兴成果，招募摄影和文案', now))
            gid6 = c.lastrowid
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid6, '202411310530', now))
        elif '挑战杯' in ename:
            c.execute("INSERT INTO events_groups (event_id, group_name, leader_uid, status, max_members, description, created_at) VALUES (?,?,?,?,?,?,?)",
                      (eid, '社科调研组', '202421324925', 'recruiting', 4, '社会调查报告方向，招募问卷设计与数据分析', now))
            gid7 = c.lastrowid
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid7, '202421324925', now))
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid7, '202421326643', now))
            c.execute("INSERT INTO events_groups (event_id, group_name, leader_uid, status, max_members, description, created_at) VALUES (?,?,?,?,?,?,?)",
                      (eid, '科技发明小队', '202421326577', 'full', 4, '已完成组队（示例：已满员小组）', now))
            gid8 = c.lastrowid
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid8, '202421326577', now))
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid8, '202421324917', now))
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid8, '202421326351', now))
            c.execute("INSERT OR IGNORE INTO events_groups_members (group_id, member_uid, joined_at) VALUES (?,?,?)", (gid8, '202421327546', now))
    conn.commit()
    print(f"已创建赛事示例小组")

def _create_event_chat_rooms(conn):
    """初始化时创建所有赛事聊天室，将赛事发布者和参与小组的成员加入"""
    c = conn.cursor()
    events = c.execute('SELECT id, name, creator_uid FROM events').fetchall()
    now = time.time()
    count = 0
    for ev in events:
        eid = ev[0]
        ename = ev[1]
        creator_uid = ev[2]
        chat_id = 'chat_event_' + str(eid)
        c.execute('INSERT OR IGNORE INTO groups_chat VALUES (?,?,?,?,?,?)',
                  (chat_id, ename + '聊天室', 'system', now, 'system', '赛事'))
        # 赛事发布者设为管理员
        if creator_uid:
            c.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)',
                      (chat_id, creator_uid, 'admin', now, 0))
        # 查出该赛事所有小组的所有成员
        members = c.execute('''SELECT DISTINCT egm.member_uid
                               FROM events_groups_members egm
                               JOIN events_groups eg ON egm.group_id = eg.id
                               WHERE eg.event_id=?''', (eid,)).fetchall()
        for m in members:
            c.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)',
                      (chat_id, m[0], 'member', now, 0))
        count += 1
    conn.commit()
    print(f"已创建 {count} 个赛事聊天室")

def _create_course_chat_rooms(conn):
    """初始化时创建所有课程聊天室，将该课程的所有学生和教师加入"""
    c = conn.cursor()
    lessons = c.execute('SELECT * FROM lesson').fetchall()
    now = time.time()
    for lesson in lessons:
        lesson_id = lesson[0]
        lesson_name = lesson[1]
        teacher_uid = lesson[2]
        chat_id = 'chat_' + lesson_id
        # 创建课程聊天室
        c.execute('INSERT OR IGNORE INTO groups_chat VALUES (?,?,?,?,?,?)',
                  (chat_id, lesson_name + '聊天室', 'system', now, 'system', '课程'))
        # 加入该课程所有学生
        stus = c.execute('SELECT stu_uid FROM lesson_stu WHERE lesson_id=?', (lesson_id,)).fetchall()
        for stu in stus:
            c.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)',
                      (chat_id, stu[0], 'member', now, 0))
        # 将教师设为管理员
        if teacher_uid:
            c.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)',
                      (chat_id, teacher_uid, 'admin', now, 0))
    conn.commit()
    print(f"已创建 {len(lessons)} 个课程聊天室")

def _create_class_chat_rooms(conn):
    """创建班级/年级聊天室，将班级成员和班干部加入"""
    c = conn.cursor()
    classes = c.execute('SELECT * FROM classes').fetchall()
    now = time.time()
    for cls in classes:
        class_id = cls[0]        # class_name 即为 class_id
        level = cls[5]           # 'class' 或 'grade'
        chat_id = 'chat_class_' + class_id
        suffix = '年级群' if level == 'grade' else '聊天室'
        c.execute('INSERT OR IGNORE INTO groups_chat VALUES (?,?,?,?,?,?)',
                  (chat_id, class_id + suffix, 'system', now, 'system', '班级'))
        # 先加管理员（班干部），再加普通成员（避免 INSERT OR IGNORE 冲突）
        for pos_row in c.execute('SELECT uid FROM class_positions WHERE class_id=? AND position_name IN (\'班长\',\'兼班\',\'兼助\',\'辅导员\')', (class_id,)).fetchall():
            c.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)',
                      (chat_id, pos_row[0], 'admin', now, 0))
        # 再加入所有班级成员
        for stu in c.execute('SELECT uid FROM class_stu WHERE class_id=?', (class_id,)).fetchall():
            c.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)',
                      (chat_id, stu[0], 'member', now, 0))
    conn.commit()
    print(f"已创建 {len(classes)} 个班级/年级聊天室")

def _seed_data(conn):
    c = conn.cursor()
    if c.execute('SELECT COUNT(*) FROM classrooms').fetchone()[0] == 0:
        c.executemany('INSERT INTO classrooms VALUES (?,?,?,?,?)', [
            ('A101','教学楼A',1,60,1), ('A102','教学楼A',1,80,0),
            ('B201','教学楼B',2,40,1), ('B202','教学楼B',2,120,1),
            ('C301','教学楼C',3,30,0), ('C302','教学楼C',3,50,1)
        ])
    if c.execute('SELECT COUNT(*) FROM course_schedule').fetchone()[0] == 0:
        c.executemany('INSERT INTO course_schedule (course_name,teacher,classroom_id,day_of_week,start_time,end_time) VALUES (?,?,?,?,?,?)', [
            ('高等数学','王老师','A101',1,'08:00','09:40'),
            ('数据结构','李老师','B201',1,'10:00','11:40'),
            ('大学英语','张老师','C301',2,'08:00','09:40'),
            ('软件工程','赵老师','B202',3,'14:00','15:40')
        ])
    if c.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0:
        _load_events_from_json('events.json', conn)
        _seed_event_groups(conn)
        _create_event_chat_rooms(conn)
    if c.execute('SELECT COUNT(*) FROM tutor_duty').fetchone()[0] == 0:
        c.executemany('INSERT INTO tutor_duty VALUES (?,?,?,?,?,?,?,?,?)', [
            (1,'李明','TE2023001','计算机学院','2026-05-01','08:00','12:00','教学楼A301','123456789'),
            (2,'王芳','TE2023002','计算机学院','2026-05-01','14:00','18:00','教学楼B205','987654321')
        ])
    if c.execute('SELECT COUNT(*) FROM teacher_office').fetchone()[0] == 0:
        c.executemany('INSERT INTO teacher_office VALUES (?,?,?,?,?,?)', [
            ('TE2023001','李明','计算机学院','教授','教学楼A栋301室','123456789'),
            ('TE2023002','王芳','计算机学院','副教授','教学楼B栋205室','987654321'),
            ('TE2023003','张强','数学学院','讲师','教学楼C栋102室','1122334455')
        ])
    if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        users_data = _load_users_from_json('users.json')
        if users_data:
            c.executemany('INSERT INTO users (uid,name,password,role,locked,unlock_time, login_fails,registed,phone) VALUES (?,?,?,?,?,?,?,?,?)', users_data)
    if c.execute('SELECT COUNT(*) FROM lesson').fetchone()[0] == 0:
        _load_lessons_from_json('lessons.json', conn)
        _create_course_chat_rooms(conn)
    if c.execute('SELECT COUNT(*) FROM classes').fetchone()[0] == 0:
        _load_classes_from_json('class.json', conn)
        _create_class_chat_rooms(conn)
    conn.commit()

# ---------- 辅助函数 ----------
def send_sms(phone, code):
    """
    发送短信验证码函数
    这里暂时空置，验证码默认发送123456
    """
    # 这里应该是您实现的短信发送逻辑
    return True


def hash_password(password):
    return hashlib.sha256((password + SALT).encode()).hexdigest()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or token not in tokens:
            return jsonify({'error': '登录已过期'}), 401
        uid = tokens[token]
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE uid=?', (uid,)).fetchone()
        if not user:
            return jsonify({'error': '用户不存在'}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated

def get_db():
    conn = sqlite3.connect('campus.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_role_by_uid(uid: str) -> str:
    """
    根据用户ID判断角色
    
    Args:
        uid: 用户ID（学号/工号）
    
    Returns:
        str: 角色
            - 'student': 学生
            - 'teacher': 教师
            - 'manager': 管理员
    """
    uid = uid.strip()
    
    # 1. 学生学号判断（华南师范大学格式）
    # 本科生：12位，202开头
    if re.match(r'^202\d{9}$', uid):
        return 'student'
    
    # 研究生：11位，以2开头（硕士）或1开头（博士）
    elif re.match(r'^[12][0-9]{10}$', uid):
        return 'student'
    
    # 2. 教师工号判断
    # 教师：以TE/T/JG开头，或纯数字工号
    elif (re.match(r'^TE\d{7}$', uid) or    # 专任教师
          re.match(r'^T\d{8}$', uid) or      # 兼职教师
          re.match(r'^JG\d{6}$', uid) or     # 教工
          re.match(r'^\d{6,8}$', uid)):      # 纯数字工号
        return 'teacher'
    
    # 3. 管理员账号
    elif (re.match(r'^ADMIN\d{3}$', uid) or
          re.match(r'^MGR\d{4}$', uid) or
          uid.lower() in ['admin', 'administrator']):
        return 'manager'
    
    # 4. 默认返回teacher（兼容原有逻辑）
    else:
        return 'teacher'

def get_user_info_by_uid(uid):
    """根据uid查找用户完整信息"""
    conn = sqlite3.connect('campus.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT uid, name, password, role, locked,unlock_time, login_fails,registed FROM users WHERE uid = ?", (uid,))
    
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        # 将结果转为字典
        user_info = {
            'uid': result[0],
            'name': result[1],
            'password': result[2],
            'role': result[3],
            'locked': bool(result[4]),
            'unlock_time':result[5] , 
            'login_fails':result[6],
            'registed':bool(result[7])
        }
        return user_info
    else:
        return None

# ---------- 路由 ----------
@app.route('/')
def index():
    return app.send_static_file('login.html')

@app.route('/main')
def main_page():
    return app.send_static_file('main.html')

@app.route('/groups')
def groups_page():
    return app.send_static_file('groups.html')

@app.route('/announcements')
def announcements_page():
    return app.send_static_file('announcements.html')

@app.route('/query')
def query_page():
    return app.send_static_file('query.html')

@app.route('/profile')
def profile_page():
    return app.send_static_file('profile.html')

@app.route('/notifications')
def notifications_page():
    return app.send_static_file('notifications.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---------- 认证 ----------
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    uid = data.get('uid','').strip()
    name = data.get('name','').strip()
    password = data.get('password','').strip()
    confirm = data.get('confirm','').strip()
    phone = data.get('phone','').strip()
    if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$', password):
        return jsonify({'error':'密码需包含大小写字母和数字，至少8位'}),400
    
    if password != confirm:
        return jsonify({'error':'两次密码不一致'}),400
    
    conn = get_db()
    info = conn.execute('SELECT * FROM users WHERE uid=?',(uid,)).fetchone()

    # 检查用户信息
    if info is None:
        return jsonify({'error': '无该学工号'}), 409

    if info['name'] != name:
        return jsonify({'error': '学工号与姓名不匹配!'}), 409
    
    if info['registed']:  # 使用get方法避免KeyError
        return jsonify({'error': '该用户已注册!'}), 409
    
    # 所有检查通过后，再连接数据库进行更新
    try:
        cursor = conn.cursor()
        
        # 修正的SQL语句
        hashed_pwd = hash_password(password)  # 确保有hash_password函数
        cursor.execute('UPDATE users SET password = ?,phone=?, registed = 1 WHERE uid = ?', 
                     (hashed_pwd, phone,uid))
        
        conn.commit()
        conn.close()
        ensure_default_groups(uid)
        return jsonify({'message': '注册成功'}), 201
        
    except Exception as e:
        # 记录错误以便调试
        print(f"注册错误: {e}")
        return jsonify({'error': '系统繁忙'}), 500
        
    finally:
        if conn:
            conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    uid = data.get('uid','').strip()
    password = data.get('password','').strip()
    conn = get_db()
    try:
        user = conn.execute('SELECT * FROM users WHERE uid=?',(uid,)).fetchone()
        if not user: return jsonify({'error':'账号不存在'}),404
        if not user['registed']: return jsonify({'error':'账号未注册'}),404

        if user['locked']:
            unlock = datetime.fromisoformat(user['unlock_time'])
            if datetime.now() < unlock:
                return jsonify({'error':f'账户已锁定，请于{unlock.strftime("%Y-%m-%d %H:%M")}后重试'}),403
            else:
                conn.execute('UPDATE users SET locked=0, login_fails=0 WHERE uid=?',(uid,))
                conn.commit()
        if hash_password(password) != user['password']:
            fails = user['login_fails'] + 1
            if fails >= 5:
                conn.execute('UPDATE users SET locked=1, unlock_time=?, login_fails=? WHERE uid=?',
                             ((datetime.now()+timedelta(minutes=30)).isoformat(), fails, uid))
                conn.commit()
                return jsonify({'error':'账户已锁定，请30分钟后重试'}),403
            else:
                conn.execute('UPDATE users SET login_fails=? WHERE uid=?',(fails,uid))
                conn.commit()
                return jsonify({'error':f'密码错误，还可尝试{5-fails}次'}),401
        token = secrets.token_hex(16)
        tokens[token] = uid
        conn.execute('UPDATE users SET login_fails=0, locked=0 WHERE uid=?',(uid,))
        conn.commit()
        conn.close()
        ensure_default_groups(uid)
        return jsonify({'message':'登录成功','token':token,'name':user['name'],'role':user['role']}),200
    except:
        return jsonify({'error':'系统繁忙'}),500
    finally:
        conn.close()


@app.route('/api/change_password', methods=['POST'])
def change_password():
    """
    处理密码修改请求
    支持两种操作：
    1. send_code: 发送验证码
    2. reset_password: 重置密码
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求数据为空"}), 400
        
        action = data.get('action')
        
        if action == 'send_code':
            return handle_send_code(data)
        elif action == 'reset_password':
            return handle_reset_password(data)
        else:
            return jsonify({"error": "无效的操作类型"}), 400
            
    except Exception as e:
        return jsonify({"error": f"服务器内部错误: {str(e)}"}), 500

def handle_send_code(data):
    """处理发送验证码请求"""
    phone = data.get('phone')
    uid=data.get('uid')
    if not phone:
        return jsonify({"error": "手机号不能为空"}), 400
    
    # 验证手机号格式
    if not phone.startswith('1') or len(phone) != 11 or not phone.isdigit():
        return jsonify({"error": "手机号格式不正确"}), 400
    
    # 检查手机号是否在系统中注册
    conn = get_db()
    
    
    try:
        user = conn.execute('SELECT * FROM users WHERE uid=?',(uid,)).fetchone()        
        if not user:
            return jsonify({"error": "该账号不存在"}), 404
        if not user['phone']==phone:
            return jsonify({"error": "学号/工号与手机号不匹配"}), 404

        # 生成6位随机验证码
        code = "123456"
        
        # 调用短信发送函数
        send_result = send_sms(phone, code)
        
        if not send_result:
            return jsonify({"error": "短信发送失败，请稍后重试"}), 500
        
        # 存储验证码和相关信息（5分钟有效期）
        verification_codes[phone] = {
            'code': code,
            'expires_at': time.time() + 300,  # 5分钟后过期
            'attempts': 0,  # 验证尝试次数
        }
        
        # 清理过期的验证码
        current_time = time.time()
        expired_phones = [
            p for p, info in verification_codes.items() 
            if info['expires_at'] < current_time
        ]
        for p in expired_phones:
            del verification_codes[p]
        
        return jsonify({
            "success": True,
            "message": "验证码已发送"
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"发送验证码失败: {str(e)}"}), 500
    finally:
        conn.close()

def handle_reset_password(data):
    """处理重置密码请求"""
    phone = data.get('phone')
    code = data.get('code')
    new_password = data.get('new_password')
    uid = data.get('uid')  # 从验证码信息中获取uid，或从前端传入
    
    if not all([phone, code, new_password]):
        return jsonify({"error": "请填写完整信息"}), 400
    
    # 验证密码强度
    if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$', new_password):
        return jsonify({'error':'密码需包含大小写字母和数字，至少8位'}),400    
    # 检查验证码
    if phone not in verification_codes:
        return jsonify({"error": "验证码已过期，请重新获取"}), 400
    
    verification_info = verification_codes[phone]
    
    # 检查验证码是否过期
    if time.time() > verification_info['expires_at']:
        del verification_codes[phone]
        return jsonify({"error": "验证码已过期，请重新获取"}), 400
    
    # 检查验证码是否正确
    if verification_info['code'] != code:
        verification_info['attempts'] += 1
        
        # 如果尝试次数过多，清除验证码
        if verification_info['attempts'] >= 5:
            del verification_codes[phone]
            return jsonify({"error": "验证失败次数过多，请重新获取验证码"}), 400
        
        return jsonify({"error": "验证码不正确"}), 400    
    
    conn = get_db()
    
    try:
        # 验证uid和手机号的对应关系
        user = conn.execute('SELECT * FROM users WHERE uid=?',(uid,)).fetchone()
        if not user['phone']==phone:
            return jsonify({"error": "学号/工号与手机号不匹配"}), 404
        
        # 更新密码
        hashed_password = hash_password(new_password)
        
        conn.execute(
            "UPDATE users SET password = ? WHERE uid = ?",
            (hashed_password, uid)
        )
        
        conn.commit()
        
        # 清除已使用的验证码
        if phone in verification_codes:
            del verification_codes[phone]
        
        return jsonify({
            "success": True,
            "message": "密码修改成功"
        }), 200
        
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": f"数据库错误: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"重置密码失败: {str(e)}"}), 500
    finally:
        conn.close()

# 可选的定时清理任务（如果需要）
def cleanup_expired_codes():
    """清理过期的验证码"""
    current_time = time.time()
    expired_phones = [
        p for p, info in verification_codes.items() 
        if info['expires_at'] < current_time
    ]
    for phone in expired_phones:
        if phone in verification_codes:
            del verification_codes[phone]




@app.route('/api/logout', methods=['POST'])
@token_required
def logout():
    token = request.headers.get('Authorization')
    if token in tokens: del tokens[token]
    return jsonify({'message':'已登出'})

@app.route('/api/userinfo', methods=['GET'])
@token_required
def userinfo():
    u = g.current_user
    return jsonify({
        'uid': u['uid'],
        'name': u['name'],
        'role': u['role'],
        'phone': u['phone'],
        'description': u['description'] if u['description'] else ''
    })

# 个人资料修改
@app.route('/api/userinfo', methods=['PUT'])
@token_required
def update_userinfo():
    data = request.get_json()
    new_phone = data.get('phone', '').strip()
    new_password = data.get('password', '').strip()
    new_description = (data.get('description') or '').strip()
    conn = get_db()
    try:
        if new_password:
            if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$', new_password):
                return jsonify({'error': '密码需包含大小写字母和数字，至少8位'}), 400
            conn.execute('UPDATE users SET password=? WHERE uid=?',
                         (hash_password(new_password), g.current_user['uid']))
        if new_phone:
            conn.execute('UPDATE users SET phone=? WHERE uid=?',
                         (new_phone, g.current_user['uid']))
        if new_description is not None:
            conn.execute('UPDATE users SET description=? WHERE uid=?',
                         (new_description, g.current_user['uid']))
        conn.commit()
        return jsonify({'message': '修改成功'})
    except:
        return jsonify({'error': '系统繁忙'}), 500
    finally:
        conn.close()

@app.route('/api/user/<uid>', methods=['GET'])
@token_required
def get_user_info(uid):
    conn = get_db()
    user = conn.execute('SELECT uid, name, role, description FROM users WHERE uid=?',
                        (uid,)).fetchone()
    conn.close()
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    return jsonify({
        'uid': user['uid'],
        'name': user['name'],
        'role': user['role'],
        'description': user['description'] if user['description'] else ''
    })

@app.route('/api/user/<uid>/tags', methods=['GET'])
@token_required
def get_user_tags(uid):
    conn = get_db()
    tags = []
    # 班干部职位
    cp_rows = conn.execute('''SELECT DISTINCT cp.position_name, c.class_name
                               FROM class_positions cp
                               JOIN class_stu cs ON cp.class_id=cs.class_id AND cp.uid=cs.uid
                               JOIN classes c ON cp.class_id=c.class_id
                               WHERE cs.uid=?''', (uid,)).fetchall()
    for r in cp_rows:
        tags.append({"type": "class", "label": f"{r['class_name']} {r['position_name']}"})
    # 课代表职位
    lp_rows = conn.execute('''SELECT DISTINCT lp.position_name, l.lesson_name
                               FROM lesson_positions lp
                               JOIN lesson l ON lp.lesson_id=l.lesson_id
                               WHERE lp.uid=?''', (uid,)).fetchall()
    for r in lp_rows:
        tags.append({"type": "lesson", "label": f"{r['lesson_name']} {r['position_name']}"})
    # 参赛标签
    ev_rows = conn.execute('''SELECT DISTINCT e.name
                               FROM events_groups_members egm
                               JOIN events_groups eg ON egm.group_id=eg.id
                               JOIN events e ON eg.event_id=e.id
                               WHERE egm.member_uid=?''', (uid,)).fetchall()
    for r in ev_rows:
        tags.append({"type": "event", "label": f"参赛-{r['name']}"})
    conn.close()
    return jsonify(tags)

# ---------- 私聊 ----------
@app.route('/api/users', methods=['GET'])
@token_required
def user_list():
    conn = get_db()
    users = conn.execute('SELECT uid, name, role FROM users WHERE uid != ?', (g.current_user['uid'],)).fetchall()
    conn.close()
    return jsonify([{'uid':u['uid'],'name':u['name'],'role':u['role']} for u in users])

@app.route('/api/messages', methods=['GET'])
@token_required
def get_messages():
    peer = request.args.get('with','')
    if not peer: return jsonify([])
    uid = g.current_user['uid']
    conn = get_db()
    msgs = conn.execute('''SELECT * FROM messages WHERE
        ((sender=? AND receiver=?) OR (sender=? AND receiver=?)) ORDER BY timestamp ASC''',
        (uid, peer, peer, uid)).fetchall()
    # 标记对方消息为已读
    conn.execute('UPDATE messages SET status="read" WHERE sender=? AND receiver=? AND status!="read"', (peer, uid))
    conn.commit()
    conn.close()
    return jsonify([{'id':m['id'],'sender':m['sender'],'receiver':m['receiver'],
                     'content':m['content'],'msg_type':m['msg_type'],
                     'file_path':m['file_path'],'file_name':m['file_name'],
                     'file_size':m['file_size'],'status':m['status'],
                     'timestamp':m['timestamp'],'revoked':m['revoked']} for m in msgs])

@app.route('/api/send', methods=['POST'])
@token_required
def send_message():
    sender = g.current_user['uid']
    if request.content_type and 'multipart/form-data' in request.content_type:
        receiver = request.form.get('receiver','').strip()
        msg_type = request.form.get('msg_type','text')
        content = request.form.get('content','')
        file = request.files.get('file')
        file_path = file_name = None
        file_size = 0
    else:
        data = request.get_json()
        receiver = data.get('receiver','').strip()
        msg_type = data.get('msg_type','text')
        content = data.get('content','').strip()
        file_path = data.get('file_path')
        file_name = data.get('file_name')
        file_size = data.get('file_size', 0)
        if not receiver:
            return jsonify({'error':'接收者不能为空'}),400

    # Check if sender is blocked by receiver
    conn = get_db()
    if conn.execute('SELECT 1 FROM user_relations WHERE uid=? AND target_uid=? AND is_blocked=1', (receiver, sender)).fetchone():
        conn.close()
        return jsonify({'error':'你已被此用户拉黑，无法发送消息'}),403
    # Check if sender has blocked receiver
    if conn.execute('SELECT 1 FROM user_relations WHERE uid=? AND target_uid=? AND is_blocked=1', (sender, receiver)).fetchone():
        conn.close()
        return jsonify({'error':'你已拉黑该用户，无法发送消息'}),403

    if request.content_type and 'multipart/form-data' in request.content_type:
        if file and msg_type in ('image','video','audio','file'):
            filename = secure_filename(f"{int(time.time())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            file_path = f'/uploads/{filename}'
            file_name = file.filename
            file_size = os.path.getsize(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    ts = time.time()
    conn.execute('INSERT INTO messages (sender,receiver,content,msg_type,file_path,file_name,file_size,status,timestamp) VALUES (?,?,?,?,?,?,?,?,?)',
                 (sender, receiver, content, msg_type, file_path, file_name, file_size, 'sent', ts))
    conn.commit(); conn.close()
    return jsonify({'message':'发送成功','timestamp':ts}),201

@app.route('/api/messages/revoke/<int:msg_id>', methods=['POST'])
@token_required
def revoke_message(msg_id):
    uid = g.current_user['uid']
    conn = get_db()
    msg = conn.execute('SELECT * FROM messages WHERE id=? AND sender=?', (msg_id, uid)).fetchone()
    if not msg:
        return jsonify({'error':'无权撤回'}),403
    if time.time() - msg['timestamp'] > 120:
        return jsonify({'error':'超过2分钟无法撤回'}),400
    user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
    name = user['name'] if user else uid
    conn.execute('UPDATE messages SET revoked=1, content=? WHERE id=?', (f'{name}撤回了一条消息', msg_id))
    conn.commit(); conn.close()
    return jsonify({'message':'已撤回'})


@app.route('/api/stream')
def stream():
    uid = request.args.get('uid', '')
    token = request.args.get('token', '')
    if not uid or not token or tokens.get(token) != uid:
        return jsonify({'error':'认证失败'}), 401
    mode = request.args.get('mode', '')
    target = request.args.get('target', '')
    after = float(request.args.get('after', '0'))
    def generate():
        while True:
            conn = get_db()
            new_msgs = []
            try:
                if mode == 'private' and target:
                    rows = conn.execute(
                        'SELECT * FROM messages WHERE ((sender=? AND receiver=?) OR (sender=? AND receiver=?)) AND timestamp > ? ORDER BY timestamp ASC',
                        (uid, target, target, uid, after)).fetchall()
                    for m in rows:
                        new_msgs.append({'id':m['id'],'sender':m['sender'],'receiver':m['receiver'],
                                         'content':m['content'],'msg_type':m['msg_type'],
                                         'file_path':m['file_path'],'file_name':m['file_name'],
                                         'file_size':m['file_size'],'status':m['status'],
                                         'timestamp':m['timestamp'],'revoked':m['revoked']})
                        if m['timestamp'] > after:
                            after = m['timestamp']
                elif mode == 'group' and target:
                    rows = conn.execute(
                        '''SELECT gm.*, COALESCE(u.name, '系统') as sender_name
                           FROM group_messages gm LEFT JOIN users u ON gm.sender = u.uid
                           WHERE gm.group_id=? AND gm.timestamp > ? ORDER BY gm.timestamp''',
                        (target, after)).fetchall()
                    for m in rows:
                        new_msgs.append({'id':m['id'],'sender':m['sender'],'sender_name':m['sender_name'],
                                         'content':m['content'],'msg_type':m['msg_type'],
                                         'file_path':m['file_path'],'file_name':m['file_name'],
                                         'status':m['status'],'timestamp':m['timestamp'],'revoked':m['revoked']})
                        if m['timestamp'] > after:
                            after = m['timestamp']
            finally:
                conn.close()
            if new_msgs:
                yield f"data: {json.dumps(new_msgs, ensure_ascii=False)}\n\n"
            else:
                yield ":\n\n"  # keep-alive
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')


# ---------- 用户群组（群组容器） ----------
@app.route('/api/user-groups', methods=['GET'])
@token_required
def get_user_groups():
    uid = g.current_user['uid']
    conn = get_db()
    # 获取用户所在的群组
    groups = conn.execute('''SELECT g.* FROM user_groups g
                             JOIN user_group_members gm ON g.group_id = gm.group_id
                             WHERE gm.uid = ? AND (g.creator = ? OR g.creator = 'system')
                             ORDER BY g.created_at DESC''', (uid, uid)).fetchall()

    result = []
    for grp in groups:
        # 获取群组的聊天室数量，系统群组需动态计算
        if grp['group_type'] == 'system' and grp['category'] == '课程':
            user = conn.execute('SELECT role FROM users WHERE uid=?', (uid,)).fetchone()
            if user and user['role'] == 'student':
                chat_count = conn.execute(
                    'SELECT COUNT(*) FROM lesson_stu WHERE stu_uid=?', (uid,)
                ).fetchone()[0]
            elif user and user['role'] == 'teacher':
                chat_count = conn.execute(
                    'SELECT COUNT(*) FROM lesson WHERE teacher_uid=?', (uid,)
                ).fetchone()[0]
            else:
                chat_count = 0
            # 加上班级/年级聊天室数量
            chat_count += conn.execute(
                "SELECT COUNT(*) FROM user_group_chats ugc JOIN groups_chat gc ON ugc.chat_id=gc.group_id WHERE ugc.group_id=? AND gc.creator='system' AND gc.category='班级'",
                (grp['group_id'],)
            ).fetchone()[0]
        else:
            chat_count = conn.execute('SELECT COUNT(*) FROM user_group_chats WHERE group_id=?',
                                      (grp['group_id'],)).fetchone()[0]
        # 获取群组的成员数量（排除自己），系统群组需动态计算
        if grp['group_type'] == 'system' and grp['category'] == '即时聊天':
            friend_uids = [r[0] for r in conn.execute('SELECT target_uid FROM user_relations WHERE uid=? AND is_friend=1', (uid,)).fetchall()]
            if friend_uids:
                placeholders = ','.join('?' * len(friend_uids))
                member_count = conn.execute(
                    f'SELECT COUNT(*) FROM users WHERE uid != ? AND uid NOT IN ({placeholders})',
                    [uid] + friend_uids
                ).fetchone()[0]
            else:
                member_count = conn.execute(
                    'SELECT COUNT(*) FROM users WHERE uid != ?', (uid,)
                ).fetchone()[0]
        elif grp['group_type'] == 'system' and grp['category'] == '私聊':
            member_count = conn.execute(
                'SELECT COUNT(*) FROM user_relations WHERE uid=? AND is_friend=1', (uid,)
            ).fetchone()[0]
        
        else:
            member_count = conn.execute('SELECT COUNT(*) FROM user_group_members WHERE group_id=? AND uid!=?',
                                        (grp['group_id'], uid)).fetchone()[0]
        result.append({
            'group_id': grp['group_id'],
            'name': grp['name'],
            'creator': grp['creator'],
            'created_at': grp['created_at'],
            'group_type': grp['group_type'],
            'category': grp['category'],
            'chat_count': chat_count,
            'member_count_except_self': member_count
        })
    # 添加"未分类"虚拟群组：包含用户所在但未被任何群组引用的聊天室
    all_group_chat_ids = set()
    for grp in groups:
        cids = conn.execute('SELECT chat_id FROM user_group_chats WHERE group_id=?',
                            (grp['group_id'],)).fetchall()
        all_group_chat_ids.update(r['chat_id'] for r in cids)
    user_chat_ids = conn.execute('SELECT group_id FROM group_members WHERE uid=?', (uid,)).fetchall()
    uncategorized = [r['group_id'] for r in user_chat_ids if r['group_id'] not in all_group_chat_ids]
    if uncategorized:
        result.append({
            'group_id': 'sys_uncategorized_' + uid,
            'name': '未分类',
            'creator': 'system',
            'created_at': 0,
            'group_type': 'system',
            'category': '未分类',
            'chat_count': len(uncategorized),
            'member_count_except_self': 0
        })
    conn.close()
    return jsonify(result)

@app.route('/api/user-groups', methods=['POST'])
@token_required
def create_user_group():
    creator = g.current_user['uid']
    data = request.get_json()
    name = data.get('name', '').strip()
    category = data.get('category', '自定义')
    member_uids = data.get('members', [])
    chat_ids = data.get('chats', [])
    
    if not name:
        return jsonify({'error': '群组名称不能为空'}), 400
    
    group_id = secrets.token_hex(8)
    conn = get_db()
    try:
        now = time.time()
        # 创建群组
        conn.execute('INSERT INTO user_groups VALUES (?,?,?,?,?,?)',
                     (group_id, name, creator, now, 'custom', category))
        # 添加创建者
        conn.execute('INSERT INTO user_group_members VALUES (?,?,?)',
                     (group_id, creator, now))
        # 添加其他勾选的成员
        for m_uid in member_uids:
            if m_uid != creator:
                conn.execute('INSERT OR IGNORE INTO user_group_members VALUES (?,?,?)',
                             (group_id, m_uid, now))
        # 添加聊天室
        for chat in chat_ids:
            if isinstance(chat, dict):
                chat_id = chat.get('chat_id', '')
                chat_name = chat.get('chat_name', '')
            else:
                chat_id = chat
                chat_name = chat
            if chat_id:
                conn.execute('INSERT OR IGNORE INTO user_group_chats VALUES (?,?,?)',
                             (group_id, chat_id, chat_name))
        conn.commit()
        return jsonify({'message': '群组创建成功', 'group_id': group_id}), 201
    except Exception as e:
        return jsonify({'error': f'创建失败: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/user-groups/batch-delete', methods=['POST'])
@token_required
def batch_delete_user_groups():
    uid = g.current_user['uid']
    data = request.get_json()
    group_ids = data.get('group_ids', [])
    conn = get_db()
    deleted = 0
    for gid in group_ids:
        group = conn.execute('SELECT * FROM user_groups WHERE group_id=?', (gid,)).fetchone()
        if group and group['creator'] == uid and group['group_type'] == 'custom':
            conn.execute('DELETE FROM user_groups WHERE group_id=?', (gid,))
            conn.execute('DELETE FROM user_group_members WHERE group_id=?', (gid,))
            conn.execute('DELETE FROM user_group_chats WHERE group_id=?', (gid,))
            deleted += 1
    conn.commit()
    conn.close()
    return jsonify({'message': f'已删除 {deleted} 个群组', 'deleted_count': deleted})

@app.route('/api/user-groups/<group_id>', methods=['PUT'])
@token_required
def update_user_group(group_id):
    uid = g.current_user['uid']
    data = request.get_json()
    conn = get_db()
    group = conn.execute('SELECT * FROM user_groups WHERE group_id=?', (group_id,)).fetchone()
    if not group:
        return jsonify({'error': '群组不存在'}), 404
    if group['creator'] != uid:
        return jsonify({'error': '无权修改'}), 403
    
    name = data.get('name', group['name'])
    category = data.get('category', group['category'])
    conn.execute('UPDATE user_groups SET name=?, category=? WHERE group_id=?',
                 (name, category, group_id))
    conn.commit()
    conn.close()
    return jsonify({'message': '已更新'})

@app.route('/api/user-groups/<group_id>', methods=['DELETE'])
@token_required
def delete_user_group(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    group = conn.execute('SELECT * FROM user_groups WHERE group_id=?', (group_id,)).fetchone()
    if not group:
        return jsonify({'error': '群组不存在'}), 404
    if group['creator'] != uid:
        return jsonify({'error': '无权删除'}), 403
    
    conn.execute('DELETE FROM user_groups WHERE group_id=?', (group_id,))
    conn.execute('DELETE FROM user_group_members WHERE group_id=?', (group_id,))
    conn.execute('DELETE FROM user_group_chats WHERE group_id=?', (group_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})

# ---------- 群组详情（成员+聊天室） ----------
@app.route('/api/user-groups/<group_id>/detail', methods=['GET'])
@token_required
def get_user_group_detail(group_id):
    uid = g.current_user['uid']
    conn = get_db()

    # 处理"未分类"虚拟群组
    if group_id == 'sys_uncategorized_' + uid:
        all_group_chat_ids = set()
        real_groups = conn.execute('SELECT g.group_id FROM user_groups g JOIN user_group_members gm ON g.group_id=gm.group_id WHERE gm.uid=? AND (g.creator=? OR g.creator=\'system\')', (uid, uid)).fetchall()
        for rg in real_groups:
            cids = conn.execute('SELECT chat_id FROM user_group_chats WHERE group_id=?', (rg['group_id'],)).fetchall()
            all_group_chat_ids.update(r['chat_id'] for r in cids)
        user_chats = conn.execute('''SELECT gc.group_id, gc.name FROM group_members gm
                                     JOIN groups_chat gc ON gm.group_id = gc.group_id
                                     WHERE gm.uid=?''', (uid,)).fetchall()
        chat_list = []
        for uc in user_chats:
            if uc['group_id'] not in all_group_chat_ids:
                chat_list.append({'chat_id': uc['group_id'], 'chat_name': uc['name'], 'chat_room_name': uc['name']})
        conn.close()
        return jsonify({
            'group_id': group_id, 'name': '未分类', 'creator': 'system',
            'created_at': 0, 'group_type': 'system', 'category': '未分类',
            'members': [], 'chats': chat_list
        })

    # 检查群组是否存在
    group = conn.execute('SELECT * FROM user_groups WHERE group_id=?', (group_id,)).fetchone()
    if not group:
        return jsonify({'error': '群组不存在'}), 404

    # 检查用户是否在群组中
    if not conn.execute('SELECT 1 FROM user_group_members WHERE group_id=? AND uid=?',
                        (group_id, uid)).fetchone():
        return jsonify({'error': '无权访问'}), 403
    
    # 对于系统群组（即时聊天、私聊），动态计算成员
    if group['group_type'] == 'system' and group['category'] == '即时聊天':
        # 所有用户 - 好友 - 自己
        friend_uids = [r['target_uid'] for r in
                       conn.execute('SELECT target_uid FROM user_relations WHERE uid=? AND is_friend=1', (uid,)).fetchall()]
        if friend_uids:
            placeholders = ','.join('?' * len(friend_uids))
            members = conn.execute(f'''SELECT uid, name, role FROM users 
                                       WHERE uid != ? AND uid NOT IN ({placeholders})
                                       ORDER BY name''',
                [uid] + friend_uids).fetchall()
        else:
            members = conn.execute('''SELECT uid, name, role FROM users 
                                       WHERE uid != ?
                                       ORDER BY name''', (uid,)).fetchall()
        member_list = [{'uid': m['uid'], 'name': m['name'], 'role': m['role'], 'added_at': 0}
                       for m in members]
    elif group['group_type'] == 'system' and group['category'] == '私聊':
        # 好友
        members = conn.execute('''SELECT u.uid, u.name, u.role, r.created_at as added_at
                                   FROM user_relations r
                                   JOIN users u ON r.target_uid = u.uid
                                   WHERE r.uid=? AND r.is_friend=1
                                   ORDER BY u.name''', (uid,)).fetchall()
        member_list = [{'uid': m['uid'], 'name': m['name'], 'role': m['role'], 'added_at': m['added_at']}
                       for m in members]
    else:
        # 普通群组，从表里取
        members = conn.execute('''SELECT u.uid, u.name, u.role, gm.added_at
                                   FROM user_group_members gm
                                   JOIN users u ON gm.uid = u.uid
                                   WHERE gm.group_id=?
                                   ORDER BY u.name''', (group_id,)).fetchall()
        member_list = [{'uid': m['uid'], 'name': m['name'], 'role': m['role'], 'added_at': m['added_at']}
                       for m in members]
    
    # 获取群组中的聊天室
    chats = conn.execute('''SELECT ugc.*, gc.name as chat_room_name
                             FROM user_group_chats ugc
                             LEFT JOIN groups_chat gc ON ugc.chat_id = gc.group_id
                             WHERE ugc.group_id=?''', (group_id,)).fetchall()
    chat_list = [{'chat_id': c['chat_id'], 'chat_name': c['chat_name'],
                  'chat_room_name': c['chat_room_name'] or c['chat_name']}
                 for c in chats]
    
    conn.close()
    return jsonify({
        'group_id': group['group_id'],
        'name': group['name'],
        'creator': group['creator'],
        'created_at': group['created_at'],
        'group_type': group['group_type'],
        'category': group['category'],
        'members': member_list,
        'chats': chat_list
    })

# ---------- 群组聊天室管理 ----------
@app.route('/api/user-groups/<group_id>/chats', methods=['POST'])
@token_required
def add_chat_to_group(group_id):
    uid = g.current_user['uid']
    data = request.get_json()
    chat_id = data.get('chat_id', '').strip()
    chat_name = data.get('chat_name', '').strip()
    
    if not chat_id or not chat_name:
        return jsonify({'error': '参数不全'}), 400
    
    conn = get_db()
    group = conn.execute('SELECT * FROM user_groups WHERE group_id=?', (group_id,)).fetchone()
    if not group:
        return jsonify({'error': '群组不存在'}), 404
    if group['group_type'] == 'system':
        return jsonify({'error': '系统群组不可修改'}), 403
    
    try:
        conn.execute('INSERT INTO user_group_chats VALUES (?,?,?)',
                     (group_id, chat_id, chat_name))
        conn.commit()
        return jsonify({'message': '添加成功'}), 201
    except Exception:
        return jsonify({'error': '聊天室已存在'}), 400
    finally:
        conn.close()

@app.route('/api/user-groups/<group_id>/chats/<chat_id>', methods=['DELETE'])
@token_required
def remove_chat_from_group(group_id, chat_id):
    uid = g.current_user['uid']
    conn = get_db()
    group = conn.execute('SELECT * FROM user_groups WHERE group_id=?', (group_id,)).fetchone()
    if not group:
        return jsonify({'error': '群组不存在'}), 404
    if group['group_type'] == 'system':
        return jsonify({'error': '系统群组不可修改'}), 403
    
    conn.execute('DELETE FROM user_group_chats WHERE group_id=? AND chat_id=?',
                 (group_id, chat_id))
    conn.commit()
    conn.close()
    return jsonify({'message': '已移除'})

# ---------- 在群组内创建聊天室 ----------
@app.route('/api/user-groups/<group_id>/create-chat', methods=['POST'])
@token_required
def create_chat_in_group(group_id):
    uid = g.current_user['uid']
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '聊天室名称不能为空'}), 400

    conn = get_db()
    group = conn.execute('SELECT * FROM user_groups WHERE group_id=?', (group_id,)).fetchone()
    if not group:
        return jsonify({'error': '群组不存在'}), 404

    try:
        now = time.time()
        chat_id = secrets.token_hex(8)
        category = group['category'] if group['category'] else '自定义'
        # 创建群聊
        conn.execute('INSERT INTO groups_chat VALUES (?,?,?,?,?,?)',
                     (chat_id, name, uid, now, 'custom', category))
        # 加入创建者（admin）
        conn.execute('INSERT INTO group_members VALUES (?,?,?,?,?)',
                     (chat_id, uid, 'admin', now, 0))
        creator_name_row = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
        creator_name = creator_name_row['name'] if creator_name_row else uid
        conn.execute('INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)',
                     (chat_id, 'system', creator_name + ' 创建了聊天室', 'system', now))
        # 选中的成员改为发送邀请通知
        member_uids = data.get('members', [])
        for m_uid in member_uids:
            if conn.execute('SELECT 1 FROM users WHERE uid=?', (m_uid,)).fetchone():
                conn.execute('INSERT INTO chat_invites (chat_id, chat_name, from_uid, to_uid, status, created_at) VALUES (?,?,?,?,?,?)',
                             (chat_id, name, uid, m_uid, 'pending', now))
                conn.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, status, created_at) VALUES ('chat_invite', ?, ?, '', json_object('chat_id',?, 'chat_name',?), 'pending', ?)",
                             (uid, m_uid, chat_id, name, now))
        # 关联到群组
        conn.execute('INSERT INTO user_group_chats VALUES (?,?,?)',
                     (group_id, chat_id, name))
        conn.commit()
        return jsonify({'message': '聊天室创建成功', 'chat_id': chat_id}), 201
    except Exception as e:
        return jsonify({'error': f'创建失败: {str(e)}'}), 500
    finally:
        conn.close()

# ---------- 群组成员管理 ----------
@app.route('/api/user-groups/<group_id>/members', methods=['POST'])
@token_required
def add_member_to_group(group_id):
    uid = g.current_user['uid']
    data = request.get_json()
    member_uids = data.get('uids', [])
    if not member_uids:
        return jsonify({'error': '成员列表为空'}), 400
    
    conn = get_db()
    group = conn.execute('SELECT * FROM user_groups WHERE group_id=?', (group_id,)).fetchone()
    if not group:
        return jsonify({'error': '群组不存在'}), 404
    if group['group_type'] == 'system':
        return jsonify({'error': '系统群组不可修改'}), 403
    
    now = time.time()
    added = 0
    for m in member_uids:
        if conn.execute('SELECT 1 FROM users WHERE uid=?', (m,)).fetchone():
            try:
                conn.execute('INSERT INTO user_group_members VALUES (?,?,?)',
                             (group_id, m, now))
                added += 1
            except Exception:
                pass
    conn.commit()
    conn.close()
    return jsonify({'message': f'添加了{added}个成员'})

@app.route('/api/user-groups/<group_id>/members/<member_uid>', methods=['DELETE'])
@token_required
def remove_member_from_group(group_id, member_uid):
    uid = g.current_user['uid']
    conn = get_db()
    group = conn.execute('SELECT * FROM user_groups WHERE group_id=?', (group_id,)).fetchone()
    if not group:
        return jsonify({'error': '群组不存在'}), 404
    if group['group_type'] == 'system':
        return jsonify({'error': '系统群组不可修改'}), 403
    if member_uid == uid:
        return jsonify({'error': '不能将自己移出群组'}), 400

    conn.execute('DELETE FROM user_group_members WHERE group_id=? AND uid=?',
                 (group_id, member_uid))
    conn.commit()
    conn.close()
    return jsonify({'message': '已移除'})

@app.route('/api/user-groups/<group_id>/batch-remove', methods=['POST'])
@token_required
def batch_remove_from_group(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    group = conn.execute('SELECT * FROM user_groups WHERE group_id=?', (group_id,)).fetchone()
    if not group:
        return jsonify({'error': '群组不存在'}), 404
    if group['group_type'] == 'system':
        return jsonify({'error': '系统群组不可修改'}), 403
    data = request.get_json()
    member_uids = data.get('member_uids', [])
    chat_ids = data.get('chat_ids', [])
    for m_uid in member_uids:
        if m_uid != uid:
            conn.execute('DELETE FROM user_group_members WHERE group_id=? AND uid=?', (group_id, m_uid))
    for chat_id in chat_ids:
        conn.execute('DELETE FROM user_group_chats WHERE group_id=? AND chat_id=?', (group_id, chat_id))
    conn.commit()
    conn.close()
    return jsonify({'message': '已移出'})

# ---------- 好友管理 ----------
@app.route('/api/friends', methods=['GET'])
@token_required
def get_friends():
    uid = g.current_user['uid']
    conn = get_db()
    friends = conn.execute('''SELECT u.uid, u.name, u.role, r.created_at
                               FROM user_relations r
                               JOIN users u ON r.target_uid = u.uid
                               WHERE r.uid=? AND r.is_friend=1
                               ORDER BY u.name''', (uid,)).fetchall()
    conn.close()
    return jsonify([{'uid': f['uid'], 'name': f['name'],
                     'role': f['role'], 'created_at': f['created_at']}
                    for f in friends])

@app.route('/api/friends/add', methods=['POST'])
@token_required
def add_friend():
    uid = g.current_user['uid']
    data = request.get_json()
    friend_uid = data.get('uid', '').strip()
    if not friend_uid:
        return jsonify({'error': '用户ID不能为空'}), 400
    if friend_uid == uid:
        return jsonify({'error': '不能添加自己为好友'}), 400
    
    conn = get_db()
    if not conn.execute('SELECT 1 FROM users WHERE uid=?', (friend_uid,)).fetchone():
        return jsonify({'error': '用户不存在'}), 404
    # 拉黑检查
    if conn.execute('SELECT 1 FROM user_relations WHERE uid=? AND target_uid=? AND is_blocked=1', (friend_uid, uid)).fetchone():
        conn.close()
        return jsonify({'error': '你已被该用户拉黑'}), 403
    if conn.execute('SELECT 1 FROM user_relations WHERE uid=? AND target_uid=? AND is_blocked=1', (uid, friend_uid)).fetchone():
        conn.close()
        return jsonify({'error': '你已拉黑该用户'}), 403

    try:
        now = time.time()
        conn.execute('INSERT INTO friends VALUES (?,?,?)', (uid, friend_uid, now))
        conn.execute("INSERT INTO user_relations (uid, target_uid, is_friend, created_at) VALUES (?,?,1,?) ON CONFLICT(uid,target_uid) DO UPDATE SET is_friend=1, created_at=?",
                     (uid, friend_uid, now, now))
        conn.commit()
        return jsonify({'message': '添加好友成功'}), 201
    except Exception:
        return jsonify({'error': '已经是好友了'}), 400
    finally:
        conn.close()

@app.route('/api/friends/remove', methods=['POST'])
@token_required
def remove_friend():
    uid = g.current_user['uid']
    data = request.get_json()
    friend_uid = data.get('uid', '').strip()
    if not friend_uid:
        return jsonify({'error': '用户ID不能为空'}), 400

    conn = get_db()
    user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
    user_name = user['name'] if user else uid
    conn.execute('DELETE FROM friends WHERE uid=? AND friend_uid=?', (uid, friend_uid))
    conn.execute('DELETE FROM friends WHERE uid=? AND friend_uid=?', (friend_uid, uid))
    conn.execute("UPDATE user_relations SET is_friend=0 WHERE uid=? AND target_uid=?", (uid, friend_uid))
    conn.execute("UPDATE user_relations SET is_friend=0 WHERE uid=? AND target_uid=?", (friend_uid, uid))
    # Send notification to the removed friend
    content = f'{user_name}已取消和你的好友关系'
    conn.execute("INSERT INTO announcements (publisher, unit, title, content, target_uid, is_read, created_at) VALUES (?,?,?,?,?,0,?)",
                 (user_name, 'notification', '', content, friend_uid, time.time()))
    conn.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, created_at) VALUES ('system', ?, ?, ?, ?)",
                 (user_name, friend_uid, content, time.time()))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除好友'})

# ---------- 好友申请 ----------
@app.route('/api/friend-request', methods=['POST'])
@token_required
def send_friend_request():
    uid = g.current_user['uid']
    data = request.get_json()
    to_uid = data.get('to_uid', '').strip()
    message = data.get('message', '').strip()
    if not to_uid:
        return jsonify({'error': '用户ID不能为空'}), 400
    if to_uid == uid:
        return jsonify({'error': '不能添加自己为好友'}), 400
    conn = get_db()
    if not conn.execute('SELECT 1 FROM users WHERE uid=?', (to_uid,)).fetchone():
        return jsonify({'error': '用户不存在'}), 404
    # 拉黑检查
    if conn.execute('SELECT 1 FROM user_relations WHERE uid=? AND target_uid=? AND is_blocked=1', (to_uid, uid)).fetchone():
        conn.close()
        return jsonify({'error': '你已被该用户拉黑'}), 403
    if conn.execute('SELECT 1 FROM user_relations WHERE uid=? AND target_uid=? AND is_blocked=1', (uid, to_uid)).fetchone():
        conn.close()
        return jsonify({'error': '你已拉黑该用户'}), 403
    if conn.execute('SELECT 1 FROM user_relations WHERE uid=? AND target_uid=? AND is_friend=1', (uid, to_uid)).fetchone():
        return jsonify({'error': '已经是好友了'}), 400
    if conn.execute('SELECT 1 FROM friend_requests WHERE from_uid=? AND to_uid=? AND status="pending"', (uid, to_uid)).fetchone() or \
       conn.execute('SELECT 1 FROM notifications WHERE sender_uid=? AND receiver_uid=? AND type="friend_request" AND status="pending"', (uid, to_uid)).fetchone():
        return jsonify({'error': '已发送过好友申请，请等待对方处理'}), 400
    conn.execute('INSERT INTO friend_requests (from_uid, to_uid, message, status, created_at) VALUES (?,?,?,?,?)',
                 (uid, to_uid, message, 'pending', time.time()))
    conn.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, status, created_at) VALUES ('friend_request', ?, ?, ?, 'pending', ?)",
                 (uid, to_uid, message, time.time()))
    conn.commit(); conn.close()
    return jsonify({'message': '好友申请已发送'}), 201

@app.route('/api/friend-requests', methods=['GET'])
@token_required
def get_friend_requests():
    uid = g.current_user['uid']
    conn = get_db()
    reqs = conn.execute("SELECT n.id, n.sender_uid as from_uid, u.name as from_name, n.content as message, n.created_at FROM notifications n JOIN users u ON n.sender_uid = u.uid WHERE n.receiver_uid=? AND n.type='friend_request' AND n.status='pending' ORDER BY n.created_at DESC", (uid,)).fetchall()
    conn.close()
    return jsonify([{'id':r['id'],'from_uid':r['from_uid'],'from_name':r['from_name'],
                     'message':r['message'],'created_at':r['created_at']} for r in reqs])

@app.route('/api/friend-requests/<int:req_id>/approve', methods=['POST'])
@token_required
def approve_friend_request(req_id):
    uid = g.current_user['uid']
    conn = get_db()
    req = conn.execute('SELECT * FROM friend_requests WHERE id=? AND to_uid=? AND status="pending"', (req_id, uid)).fetchone()
    if not req:
        # 也查 notifications 表
        n = conn.execute('SELECT * FROM notifications WHERE id=? AND receiver_uid=? AND type="friend_request" AND status="pending"', (req_id, uid)).fetchone()
        if not n:
            return jsonify({'error': '申请不存在'}), 404
        conn.execute("UPDATE notifications SET status='approved' WHERE id=?", (req_id,))
        now = time.time()
        conn.execute('INSERT OR IGNORE INTO friends VALUES (?,?,?)', (n['sender_uid'], uid, now))
        conn.execute('INSERT OR IGNORE INTO friends VALUES (?,?,?)', (uid, n['sender_uid'], now))
        conn.execute("INSERT INTO user_relations (uid, target_uid, is_friend, created_at) VALUES (?,?,1,?) ON CONFLICT(uid,target_uid) DO UPDATE SET is_friend=1, created_at=?", (n['sender_uid'], uid, now, now))
        conn.execute("INSERT INTO user_relations (uid, target_uid, is_friend, created_at) VALUES (?,?,1,?) ON CONFLICT(uid,target_uid) DO UPDATE SET is_friend=1, created_at=?", (uid, n['sender_uid'], now, now))
        conn.commit(); conn.close()
        return jsonify({'message': '已同意好友申请'})
    conn.execute('UPDATE friend_requests SET status="approved" WHERE id=?', (req_id,))
    conn.execute("UPDATE notifications SET status='approved' WHERE sender_uid=? AND receiver_uid=? AND type='friend_request' AND status='pending'", (req['from_uid'], uid))
    now = time.time()
    conn.execute('INSERT OR IGNORE INTO friends VALUES (?,?,?)', (req['from_uid'], uid, now))
    conn.execute('INSERT OR IGNORE INTO friends VALUES (?,?,?)', (uid, req['from_uid'], now))
    conn.execute("INSERT INTO user_relations (uid, target_uid, is_friend, created_at) VALUES (?,?,1,?) ON CONFLICT(uid,target_uid) DO UPDATE SET is_friend=1, created_at=?", (req['from_uid'], uid, now, now))
    conn.execute("INSERT INTO user_relations (uid, target_uid, is_friend, created_at) VALUES (?,?,1,?) ON CONFLICT(uid,target_uid) DO UPDATE SET is_friend=1, created_at=?", (uid, req['from_uid'], now, now))
    conn.commit(); conn.close()
    return jsonify({'message': '已同意好友申请'})

@app.route('/api/friend-requests/<int:req_id>/reject', methods=['POST'])
@token_required
def reject_friend_request(req_id):
    uid = g.current_user['uid']
    conn = get_db()
    req = conn.execute('SELECT * FROM friend_requests WHERE id=? AND to_uid=? AND status="pending"', (req_id, uid)).fetchone()
    if not req:
        n = conn.execute('SELECT * FROM notifications WHERE id=? AND receiver_uid=? AND type="friend_request" AND status="pending"', (req_id, uid)).fetchone()
        if not n:
            return jsonify({'error': '申请不存在'}), 404
        conn.execute("UPDATE notifications SET status='rejected', is_read=1 WHERE id=?", (req_id,))
        conn.commit(); conn.close()
        return jsonify({'message': '已拒绝好友申请'})
    conn.execute('UPDATE friend_requests SET status="rejected" WHERE id=?', (req_id,))
    conn.execute("UPDATE notifications SET status='rejected', is_read=1 WHERE sender_uid=? AND receiver_uid=? AND type='friend_request' AND status='pending'", (req['from_uid'], uid))
    conn.commit(); conn.close()
    return jsonify({'message': '已拒绝好友申请'})

# ---------- 通知中心 ----------
@app.route('/api/notifications', methods=['GET'])
@token_required
def get_notifications():
    uid = g.current_user['uid']
    conn = get_db()
    rows = conn.execute("SELECT n.*, u.name as sender_name FROM notifications n LEFT JOIN users u ON n.sender_uid = u.uid WHERE n.receiver_uid=? ORDER BY n.created_at DESC", (uid,)).fetchall()
    conn.close()
    notifs = []
    for n in rows:
        notifs.append({
            'id': n['id'],
            'type': n['type'],
            'sender_uid': n['sender_uid'],
            'sender_name': n['sender_name'] or n['sender_uid'],
            'content': n['content'] or '',
            'extra': n['extra'] or '{}',
            'status': n['status'] or '',
            'is_read': n['is_read'] == '1' or n['is_read'] == 1,
            'is_locked': n['is_locked'] == '1' or n['is_locked'] == 1,
            'created_at': n['created_at']
        })
    return jsonify(notifs)

@app.route('/api/notifications/system', methods=['POST'])
@token_required
def send_system_notification():
    uid = g.current_user['uid']
    data = request.get_json()
    target_uid = data.get('target_uid', '').strip()
    content = data.get('content', '').strip()
    if not target_uid or not content:
        return jsonify({'error': '参数不完整'}), 400
    conn = get_db()
    user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
    publisher = user['name'] if user else uid
    conn.execute("INSERT INTO announcements (publisher, unit, title, content, target_uid, is_read, created_at) VALUES (?,?,?,?,?,0,?)",
                 (publisher, 'notification', '', content, target_uid, time.time()))
    conn.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, created_at) VALUES ('system', ?, ?, ?, ?)",
                 (publisher, target_uid, content, time.time()))
    conn.commit(); conn.close()
    return jsonify({'message': '通知已发送'}), 201

@app.route('/api/notifications/read', methods=['POST'])
@token_required
def mark_notification_read():
    uid = g.current_user['uid']
    data = request.get_json()
    notif_id = data.get('id', '')
    conn = get_db()
    is_old_prefix = str(notif_id).startswith('fr_') or str(notif_id).startswith('ci_') or str(notif_id).startswith('sys_')
    if is_old_prefix:
        if notif_id.startswith('sys_'):
            conn.execute("UPDATE announcements SET is_read=1 WHERE id=? AND target_uid=?", (notif_id.replace('sys_', ''), uid))
        elif notif_id.startswith('fr_'):
            conn.execute("UPDATE friend_requests SET is_read=1 WHERE id=? AND to_uid=?", (notif_id.replace('fr_', ''), uid))
        elif notif_id.startswith('ci_'):
            conn.execute("UPDATE chat_invites SET is_read=1 WHERE id=? AND to_uid=?", (notif_id.replace('ci_', ''), uid))
    else:
        try:
            conn.execute("UPDATE notifications SET is_read=1 WHERE id=? AND receiver_uid=?", (int(notif_id), uid))
        except ValueError:
            pass
    conn.commit(); conn.close()
    return jsonify({'message': '已标记已读'})

@app.route('/api/notifications/read-all', methods=['POST'])
@token_required
def mark_all_notifications_read():
    uid = g.current_user['uid']
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE receiver_uid=? AND (is_read=0 OR is_read IS NULL)", (uid,))
    conn.execute("UPDATE announcements SET is_read=1 WHERE target_uid=? AND (is_read IS NULL OR is_read=0)", (uid,))
    conn.commit(); conn.close()
    return jsonify({'message': '全部已读'})

@app.route('/api/notifications/unread-count', methods=['GET'])
@token_required
def unread_notification_count():
    uid = g.current_user['uid']
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) as cnt FROM notifications WHERE receiver_uid=? AND (is_read=0 OR is_read IS NULL)", (uid,)).fetchone()
    conn.close()
    return jsonify({'count': count['cnt'] if count else 0})

@app.route('/api/notifications/delete', methods=['POST'])
@token_required
def delete_notification():
    uid = g.current_user['uid']
    data = request.get_json()
    notif_id = data.get('id', '')
    conn = get_db()
    is_old_prefix = str(notif_id).startswith('fr_') or str(notif_id).startswith('ci_') or str(notif_id).startswith('sys_')
    if is_old_prefix:
        if notif_id.startswith('sys_'):
            ann_id = notif_id.replace('sys_', '')
            ann = conn.execute('SELECT * FROM announcements WHERE id=? AND target_uid=?', (ann_id, uid)).fetchone()
            if not ann:
                conn.close()
                return jsonify({'error': '通知不存在'}), 404
            if ann.get('is_locked') in ('1', 1, 'true'):
                conn.close()
                return jsonify({'error': '通知已被锁定，无法删除'}), 403
            conn.execute('DELETE FROM announcements WHERE id=? AND target_uid=?', (ann_id, uid))
        elif notif_id.startswith('fr_'):
            conn.execute('DELETE FROM friend_requests WHERE id=? AND to_uid=?', (notif_id.replace('fr_', ''), uid))
        elif notif_id.startswith('ci_'):
            conn.execute('DELETE FROM chat_invites WHERE id=? AND to_uid=?', (notif_id.replace('ci_', ''), uid))
    else:
        try:
            nid = int(notif_id)
            n = conn.execute('SELECT * FROM notifications WHERE id=? AND receiver_uid=?', (nid, uid)).fetchone()
            if not n:
                conn.close()
                return jsonify({'error': '通知不存在'}), 404
            if n.get('is_locked') in ('1', 1, 'true'):
                conn.close()
                return jsonify({'error': '通知已被锁定，无法删除'}), 403
            conn.execute('DELETE FROM notifications WHERE id=? AND receiver_uid=?', (nid, uid))
        except ValueError:
            conn.close()
            return jsonify({'error': '无效的通知ID'}), 400
    conn.commit(); conn.close()
    return jsonify({'message': '已删除'})

@app.route('/api/notifications/delete-read', methods=['POST'])
@token_required
def delete_read_notifications():
    uid = g.current_user['uid']
    conn = get_db()
    conn.execute("DELETE FROM notifications WHERE receiver_uid=? AND (is_read=1 OR is_read='1') AND (is_locked IS NULL OR is_locked=0 OR is_locked='0')", (uid,))
    conn.execute("DELETE FROM announcements WHERE target_uid=? AND (is_read=1 OR is_read='1') AND (is_locked IS NULL OR is_locked=0 OR is_locked='0')", (uid,))
    conn.execute("DELETE FROM friend_requests WHERE to_uid=? AND (is_read=1 OR is_read='1')", (uid,))
    conn.execute("DELETE FROM chat_invites WHERE to_uid=? AND (is_read=1 OR is_read='1')", (uid,))
    conn.commit(); conn.close()
    return jsonify({'message': '已删除'})

@app.route('/api/notifications/lock', methods=['POST'])
@token_required
def lock_notification():
    uid = g.current_user['uid']
    data = request.get_json()
    notif_id = data.get('id', '')
    locked = data.get('locked', True)
    conn = get_db()
    val = 1 if locked else 0
    try:
        nid = int(notif_id)
        conn.execute("UPDATE notifications SET is_locked=? WHERE id=? AND receiver_uid=? AND type='system'", (val, nid, uid))
    except ValueError:
        if notif_id.startswith('sys_'):
            ann_id = notif_id.replace('sys_', '')
            conn.execute("UPDATE announcements SET is_locked=? WHERE id=? AND target_uid=?", (val, ann_id, uid))
        else:
            conn.close()
            return jsonify({'message': '无需操作'})
    conn.commit(); conn.close()
    return jsonify({'message': '操作成功'})


# ---------- 统一审批端点（notifications 表） ----------
@app.route('/api/notifications/<int:notif_id>/approve', methods=['POST'])
@token_required
def approve_notification(notif_id):
    uid = g.current_user['uid']
    conn = get_db()
    n = conn.execute('SELECT * FROM notifications WHERE id=? AND receiver_uid=? AND status="pending"', (notif_id, uid)).fetchone()
    if not n:
        return jsonify({'error': '通知不存在或已处理'}), 404
    if n['type'] == 'friend_request':
        now = time.time()
        conn.execute("INSERT INTO user_relations (uid,target_uid,is_friend,created_at) VALUES (?,?,1,?) ON CONFLICT(uid,target_uid) DO UPDATE SET is_friend=1, created_at=?",
                     (n['sender_uid'], uid, now, now))
        conn.execute("INSERT INTO user_relations (uid,target_uid,is_friend,created_at) VALUES (?,?,1,?) ON CONFLICT(uid,target_uid) DO UPDATE SET is_friend=1, created_at=?",
                     (uid, n['sender_uid'], now, now))
        conn.execute('INSERT OR IGNORE INTO friends VALUES (?,?,?)', (n['sender_uid'], uid, now))
        conn.execute('INSERT OR IGNORE INTO friends VALUES (?,?,?)', (uid, n['sender_uid'], now))
        conn.execute("UPDATE friend_requests SET status='approved' WHERE from_uid=? AND to_uid=? AND status='pending'", (n['sender_uid'], uid))
        conn.execute("UPDATE notifications SET status='approved', is_read=1 WHERE id=?", (notif_id,))
        conn.commit(); conn.close()
        return jsonify({'message': '已同意好友申请'})
    elif n['type'] == 'chat_invite':
        extra = json.loads(n['extra'] or '{}')
        chat_id = extra.get('chat_id', '')
        chat_name = extra.get('chat_name', '')
        now = time.time()
        conn.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)', (chat_id, uid, 'member', now, 0))
        conn.execute("UPDATE chat_invites SET status='approved' WHERE chat_id=? AND to_uid=? AND status='pending'", (chat_id, uid))
        conn.execute("UPDATE notifications SET status='approved' WHERE id=?", (notif_id,))
        user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
        user_name = user['name'] if user else uid
        conn.execute("INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)",
                     (chat_id, 'system', f'{user_name} 接受了邀请加入聊天室', 'system', now))
        conn.commit(); conn.close()
        return jsonify({'message': '已接受邀请', 'chat_id': chat_id, 'chat_name': chat_name})
    elif n['type'] == 'group_join':
        extra = json.loads(n['extra'] or '{}')
        gid = extra['group_id']
        cur = conn.execute('SELECT status, max_members FROM events_groups WHERE id=?', (gid,)).fetchone()
        if not cur:
            return jsonify({'error': '小组不存在'}), 404
        if cur['status'] == 'full':
            return jsonify({'error': '该小组已满员'}), 400
        cur_count = conn.execute('SELECT COUNT(*) FROM events_groups_members WHERE group_id=?', (gid,)).fetchone()[0]
        if cur_count >= cur['max_members']:
            conn.execute('UPDATE events_groups SET status=? WHERE id=?', ('full', gid))
            return jsonify({'error': '小组人数已满，已自动设为满员'}), 400
        conn.execute('INSERT INTO events_groups_members (group_id, member_uid) VALUES (?,?)', (gid, n['sender_uid']))
        conn.execute("UPDATE notifications SET status='approved', is_read=1 WHERE id=?", (notif_id,))
        # 同步加入赛事聊天室
        group_row = conn.execute('SELECT event_id FROM events_groups WHERE id=?', (gid,)).fetchone()
        if group_row:
            chat_id = 'chat_event_' + str(group_row['event_id'])
            now2 = time.time()
            conn.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)', (chat_id, n['sender_uid'], 'member', now2, 0))
            conn.execute('''INSERT OR IGNORE INTO user_group_chats (group_id, chat_id, chat_name)
                             SELECT ?, ?, name FROM events WHERE id=?''',
                          ('sys_events_' + n['sender_uid'], chat_id, group_row['event_id']))
            member_name = conn.execute('SELECT name FROM users WHERE uid=?', (n['sender_uid'],)).fetchone()
            if member_name:
                conn.execute("INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)",
                             (chat_id, 'system', f'{member_name["name"]} 加入了小组，进入聊天室', 'system', now2))
        conn.commit(); conn.close()
        return jsonify({'message': '已同意加入申请'})
    else:
        return jsonify({'error': '该类型通知不支持审批操作'}), 400

@app.route('/api/notifications/<int:notif_id>/reject', methods=['POST'])
@token_required
def reject_notification(notif_id):
    uid = g.current_user['uid']
    conn = get_db()
    n = conn.execute('SELECT * FROM notifications WHERE id=? AND receiver_uid=? AND status="pending"', (notif_id, uid)).fetchone()
    if not n:
        return jsonify({'error': '通知不存在或已处理'}), 404
    conn.execute("UPDATE notifications SET status='rejected', is_read=1 WHERE id=?", (notif_id,))
    if n['type'] == 'friend_request':
        conn.execute("UPDATE friend_requests SET status='rejected' WHERE from_uid=? AND to_uid=? AND status='pending'", (n['sender_uid'], uid))
    elif n['type'] == 'chat_invite':
        extra = json.loads(n['extra'] or '{}')
        chat_id = extra.get('chat_id', '')
        conn.execute("UPDATE chat_invites SET status='rejected' WHERE chat_id=? AND to_uid=? AND status='pending'", (chat_id, uid))
    elif n['type'] == 'group_join':
        pass
    conn.commit(); conn.close()
    return jsonify({'message': '已拒绝'})

# ---------- 聊天室邀请处理 ----------
@app.route('/api/chat-invites/<int:invite_id>/approve', methods=['POST'])
@token_required
def approve_chat_invite(invite_id):
    uid = g.current_user['uid']
    conn = get_db()
    inv = conn.execute('SELECT * FROM chat_invites WHERE id=? AND to_uid=? AND status="pending"', (invite_id, uid)).fetchone()
    if not inv:
        n = conn.execute('SELECT * FROM notifications WHERE id=? AND receiver_uid=? AND type="chat_invite" AND status="pending"', (invite_id, uid)).fetchone()
        if not n:
            return jsonify({'error': '邀请不存在'}), 404
        now = time.time()
        extra = json.loads(n['extra'] or '{}')
        chat_id = extra.get('chat_id', '')
        chat_name = extra.get('chat_name', '')
        conn.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)', (chat_id, uid, 'member', now, 0))
        conn.execute("UPDATE notifications SET status='approved' WHERE id=?", (invite_id,))
        user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
        user_name = user['name'] if user else uid
        conn.execute("INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)",
                     (chat_id, 'system', f'{user_name} 接受了邀请加入聊天室', 'system', now))
        conn.commit(); conn.close()
        return jsonify({'message': '已接受邀请', 'chat_id': chat_id, 'chat_name': chat_name})
    now = time.time()
    conn.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)', (inv['chat_id'], uid, 'member', now, 0))
    conn.execute('UPDATE chat_invites SET status="approved" WHERE id=?', (invite_id,))
    conn.execute("UPDATE notifications SET status='approved' WHERE sender_uid=? AND receiver_uid=? AND type='chat_invite' AND status='pending'", (inv['from_uid'], uid))
    user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
    user_name = user['name'] if user else uid
    conn.execute("INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)",
                 (inv['chat_id'], 'system', f'{user_name} 接受了邀请加入聊天室', 'system', now))
    conn.commit(); conn.close()
    return jsonify({'message': '已接受邀请', 'chat_id': inv['chat_id'], 'chat_name': inv['chat_name']})

@app.route('/api/chat-invites/<int:invite_id>/reject', methods=['POST'])
@token_required
def reject_chat_invite(invite_id):
    uid = g.current_user['uid']
    conn = get_db()
    inv = conn.execute('SELECT * FROM chat_invites WHERE id=? AND to_uid=? AND status="pending"', (invite_id, uid)).fetchone()
    if not inv:
        n = conn.execute('SELECT * FROM notifications WHERE id=? AND receiver_uid=? AND type="chat_invite" AND status="pending"', (invite_id, uid)).fetchone()
        if not n:
            return jsonify({'error': '邀请不存在'}), 404
        conn.execute("UPDATE notifications SET status='rejected', is_read=1 WHERE id=?", (invite_id,))
        conn.commit(); conn.close()
        return jsonify({'message': '已拒绝邀请'})
    conn.execute('UPDATE chat_invites SET status="rejected" WHERE id=?', (invite_id,))
    conn.execute("UPDATE notifications SET status='rejected', is_read=1 WHERE sender_uid=? AND receiver_uid=? AND type='chat_invite' AND status='pending'", (inv['from_uid'], uid))
    conn.commit(); conn.close()
    return jsonify({'message': '已拒绝邀请'})

# ---------- 黑名单 ----------
@app.route('/api/blacklist', methods=['GET'])
@token_required
def get_blacklist():
    uid = g.current_user['uid']
    conn = get_db()
    blocked = conn.execute('''SELECT u.uid, u.name, u.role FROM user_relations r
                               JOIN users u ON r.target_uid = u.uid
                               WHERE r.uid=? AND r.is_blocked=1''', (uid,)).fetchall()
    conn.close()
    return jsonify([{'uid': b['uid'], 'name': b['name'], 'role': b['role']} for b in blocked])

@app.route('/api/blacklist/add', methods=['POST'])
@token_required
def add_blacklist():
    uid = g.current_user['uid']
    data = request.get_json()
    blocked_uid = data.get('uid', '').strip()
    if not blocked_uid:
        return jsonify({'error': '用户ID不能为空'}), 400
    if blocked_uid == uid:
        return jsonify({'error': '不能拉黑自己'}), 400
    conn = get_db()
    try:
        conn.execute('INSERT OR IGNORE INTO blacklist VALUES (?,?)', (uid, blocked_uid))
        conn.execute("INSERT INTO user_relations (uid, target_uid, is_blocked) VALUES (?,?,1) ON CONFLICT(uid,target_uid) DO UPDATE SET is_blocked=1",
                     (uid, blocked_uid))
        user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
        user_name = user['name'] if user else uid
        content = f'{user_name}已将你拉黑'
        conn.execute("INSERT INTO announcements (publisher, unit, title, content, target_uid, is_read, created_at) VALUES (?,?,?,?,?,0,?)",
                     (user_name, 'notification', '', content, blocked_uid, time.time()))
        conn.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, created_at) VALUES ('system', ?, ?, ?, ?)",
                     (user_name, blocked_uid, content, time.time()))
        conn.commit()
        return jsonify({'message': '已拉黑'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/blacklist/remove', methods=['POST'])
@token_required
def remove_blacklist():
    uid = g.current_user['uid']
    data = request.get_json()
    blocked_uid = data.get('uid', '').strip()
    if not blocked_uid:
        return jsonify({'error': '用户ID不能为空'}), 400
    conn = get_db()
    conn.execute('DELETE FROM blacklist WHERE uid=? AND blocked_uid=?', (uid, blocked_uid))
    conn.execute("UPDATE user_relations SET is_blocked=0 WHERE uid=? AND target_uid=?", (uid, blocked_uid))
    conn.commit()
    conn.close()
    return jsonify({'message': '已取消拉黑'})

# ---------- 系统默认群组自动创建 ----------
def ensure_default_groups(uid):
    conn = get_db()
    try:
        now = time.time()

        # 检查并创建"即时聊天"群组
        chat_group = conn.execute('''SELECT g.group_id FROM user_groups g
                                      JOIN user_group_members gm ON g.group_id = gm.group_id
                                      WHERE gm.uid=? AND g.category='即时聊天' AND g.group_type='system' ''',
                                  (uid,)).fetchone()
        if not chat_group:
            group_id = 'sys_im_' + uid
            conn.execute('INSERT OR IGNORE INTO user_groups VALUES (?,?,?,?,?,?)',
                         (group_id, '即时聊天', 'system', now, 'system', '即时聊天'))
            conn.execute('INSERT OR IGNORE INTO user_group_members VALUES (?,?,?)',
                         (group_id, uid, now))

        # 检查并创建"私聊"群组
        private_group = conn.execute('''SELECT g.group_id FROM user_groups g
                                         JOIN user_group_members gm ON g.group_id = gm.group_id
                                         WHERE gm.uid=? AND g.category='私聊' AND g.group_type='system' ''',
                                     (uid,)).fetchone()
        if not private_group:
            group_id = 'sys_private_' + uid
            conn.execute('INSERT OR IGNORE INTO user_groups VALUES (?,?,?,?,?,?)',
                         (group_id, '私聊', 'system', now, 'system', '私聊'))
            conn.execute('INSERT OR IGNORE INTO user_group_members VALUES (?,?,?)',
                         (group_id, uid, now))

        # 检查并创建"课程"群组
        course_group = conn.execute('''SELECT g.group_id FROM user_groups g
                                        JOIN user_group_members gm ON g.group_id = gm.group_id
                                        WHERE gm.uid=? AND g.category='课程' AND g.group_type='system' ''',
                                    (uid,)).fetchone()
        if not course_group:
            course_group_id = 'sys_courses_' + uid
            conn.execute('INSERT OR IGNORE INTO user_groups VALUES (?,?,?,?,?,?)',
                         (course_group_id, '课程和班级', 'system', now, 'system', '课程'))
            conn.execute('INSERT OR IGNORE INTO user_group_members VALUES (?,?,?)',
                         (course_group_id, uid, now))
        else:
            course_group_id = course_group['group_id']
        # 每次登录同步用户的课程/班级聊天室到"课程和班级"群组
        user = conn.execute('SELECT role FROM users WHERE uid=?', (uid,)).fetchone()
        if user:
            if user['role'] == 'student':
                courses = conn.execute('''SELECT l.* FROM lesson l
                                           JOIN lesson_stu ls ON l.lesson_id = ls.lesson_id
                                           WHERE ls.stu_uid=?''', (uid,)).fetchall()
            elif user['role'] == 'teacher':
                courses = conn.execute('SELECT * FROM lesson WHERE teacher_uid=?',
                                       (uid,)).fetchall()
            else:
                courses = []

            for course in courses:
                lesson_id = course['lesson_id']
                chat_id = 'chat_' + lesson_id
                chat_name = course['lesson_name']
                conn.execute('INSERT OR IGNORE INTO user_group_chats VALUES (?,?,?)',
                             (course_group_id, chat_id, chat_name))

            # 将用户所在的班级/年级聊天室也关联到"课程和班级"群组
            class_ids = conn.execute('SELECT class_id FROM class_stu WHERE uid=?', (uid,)).fetchall()
            for cr in class_ids:
                cid = cr[0]
                chat_id = 'chat_class_' + cid
                cname = conn.execute('SELECT class_name FROM classes WHERE class_id=?', (cid,)).fetchone()
                if cname:
                    conn.execute('INSERT OR IGNORE INTO user_group_chats VALUES (?,?,?)',
                                 (course_group_id, chat_id, cname[0]))

        # 检查并创建"赛事"群组
        event_group = conn.execute('''SELECT g.group_id FROM user_groups g
                                       JOIN user_group_members gm ON g.group_id = gm.group_id
                                       WHERE gm.uid=? AND g.category='赛事' AND g.group_type='system' ''',
                                   (uid,)).fetchone()
        if not event_group:
            event_group_id = 'sys_events_' + uid
            conn.execute('INSERT OR IGNORE INTO user_groups VALUES (?,?,?,?,?,?)',
                         (event_group_id, '赛事', 'system', now, 'system', '赛事'))
            conn.execute('INSERT OR IGNORE INTO user_group_members VALUES (?,?,?)',
                         (event_group_id, uid, now))
        else:
            event_group_id = event_group['group_id']
        # 每次登录同步用户的赛事聊天室到"赛事"群组
        user = conn.execute('SELECT role FROM users WHERE uid=?', (uid,)).fetchone()
        if user:
            # 参与的赛事（通过 events_groups_members）
            event_ids = conn.execute('''SELECT DISTINCT eg.event_id FROM events_groups eg
                                         JOIN events_groups_members egm ON eg.id = egm.group_id
                                         WHERE egm.member_uid=?''', (uid,)).fetchall()
            # 负责的赛事（通过 events.creator_uid）
            created_ids = conn.execute('SELECT id FROM events WHERE creator_uid=?',
                                       (uid,)).fetchall()
            all_ids = set(r[0] for r in event_ids) | set(r[0] for r in created_ids)
            for eid in all_ids:
                chat_id = 'chat_event_' + str(eid)
                ename = conn.execute('SELECT name FROM events WHERE id=?', (eid,)).fetchone()
                if ename:
                    conn.execute('INSERT OR IGNORE INTO user_group_chats VALUES (?,?,?)',
                                 (event_group_id, chat_id, ename['name']))

        conn.commit()
    finally:
        conn.close()


# ---------- 群聊 ----------
@app.route('/api/groups', methods=['GET'])
@token_required
def get_groups():
    uid = g.current_user['uid']
    conn = get_db()
    groups = conn.execute('''SELECT g.* FROM groups_chat g
                             JOIN group_members gm ON g.group_id = gm.group_id
                             WHERE gm.uid = ?''', (uid,)).fetchall()
    conn.close()
    return jsonify([{'group_id':gr['group_id'],'name':gr['name'],'creator':gr['creator'],
                     'created_at':gr['created_at'],'group_type':gr['group_type'],
                     'category':gr['category']} for gr in groups])

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
    conn = get_db()
    try:
        all_members = [creator] + members
        for m in all_members:
            if not conn.execute('SELECT uid FROM users WHERE uid=?',(m,)).fetchone():
                return jsonify({'error':f'成员 {m} 不存在'}),404
        now = time.time()
        conn.execute('INSERT INTO groups_chat VALUES (?,?,?,?,?,?)',
                     (group_id, name, creator, now, 'custom', category))
        for m in all_members:
            role = 'admin' if m == creator else 'member'
            conn.execute('INSERT INTO group_members VALUES (?,?,?,?,?)', (group_id, m, role, now, 0))
        conn.execute('INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)',
                     (group_id, 'system', '聊天室已创建', 'system', now))
        conn.commit()
        return jsonify({'message':'群聊创建成功','group_id':group_id}),201
    except Exception as e:
        return jsonify({'error':'系统繁忙'}),500
    finally:
        conn.close()

@app.route('/api/groups/<group_id>/messages', methods=['GET'])
@token_required
def get_group_messages(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    if not conn.execute('SELECT 1 FROM group_members WHERE group_id=? AND uid=?',(group_id,uid)).fetchone():
        return jsonify({'error':'无权访问'}),403
    msgs = conn.execute('''SELECT gm.*, COALESCE(u.name, '系统') as sender_name
                            FROM group_messages gm
                            LEFT JOIN users u ON gm.sender = u.uid
                            WHERE gm.group_id=? ORDER BY gm.timestamp''', (group_id,)).fetchall()
    conn.close()
    return jsonify([{'id':m['id'],'sender':m['sender'],'sender_name':m['sender_name'],'content':m['content'],
                     'msg_type':m['msg_type'],'file_path':m['file_path'],
                     'file_name':m['file_name'],'status':m['status'],
                     'timestamp':m['timestamp'],'revoked':m['revoked']} for m in msgs])

@app.route('/api/groups/<group_id>/send', methods=['POST'])
@token_required
def send_group_message(group_id):
    sender = g.current_user['uid']
    conn = get_db()
    if not conn.execute('SELECT 1 FROM group_members WHERE group_id=? AND uid=?',(group_id,sender)).fetchone():
        return jsonify({'error':'无权发送'}),403
    if request.content_type and 'multipart/form-data' in request.content_type:
        msg_type = request.form.get('msg_type','text')
        content = request.form.get('content','')
        file = request.files.get('file')
        file_path = file_name = None
        if file:
            filename = secure_filename(f"{int(time.time())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            file_path = f'/uploads/{filename}'
            file_name = file.filename
        ts = time.time()
        conn.execute('INSERT INTO group_messages (group_id,sender,content,msg_type,file_path,file_name,status,timestamp) VALUES (?,?,?,?,?,?,?,?)',
                     (group_id, sender, content, msg_type, file_path, file_name, 'sent', ts))
        conn.commit(); conn.close()
        return jsonify({'message':'发送成功'}),201
    else:
        data = request.get_json()
        content = data.get('content','')
        msg_type = data.get('msg_type','text')
        file_path = data.get('file_path')
        file_name = data.get('file_name')
        file_size = data.get('file_size', 0)
        ts = time.time()
        conn.execute('INSERT INTO group_messages (group_id,sender,content,msg_type,file_path,file_name,file_size,status,timestamp) VALUES (?,?,?,?,?,?,?,?,?)',
                     (group_id, sender, content, msg_type, file_path, file_name, file_size, 'sent', ts))
        conn.commit(); conn.close()
        return jsonify({'message':'发送成功'}),201

@app.route('/api/groups/revoke/<int:msg_id>', methods=['POST'])
@token_required
def revoke_group_message(msg_id):
    uid = g.current_user['uid']
    conn = get_db()
    try:
        msg = conn.execute('SELECT * FROM group_messages WHERE id=?', (msg_id,)).fetchone()
        if not msg:
            return jsonify({'error':'消息不存在'}),404
        member = conn.execute('SELECT role FROM group_members WHERE group_id=? AND uid=?', (msg['group_id'], uid)).fetchone()
        is_admin = member and member['role'] in ('admin','manager')
        is_own = msg['sender'] == uid
        can_revoke = is_own and (is_admin or time.time() - msg['timestamp'] <= 120)
        can_revoke = can_revoke or (not is_own and is_admin)
        if not can_revoke:
            err = '超过2分钟无法撤回' if is_own else '无权撤回'
            return jsonify({'error':err}), (400 if is_own else 403)
        user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
        name = user['name'] if user else uid
        conn.execute('UPDATE group_messages SET revoked=1, content=? WHERE id=?', (f'{name}撤回了一条消息', msg_id))
        conn.commit()
        return jsonify({'message':'已撤回'})
    finally:
        conn.close()

def _dissolve_chat_room(conn, group_id, reason):
    """解散聊天室：删除成员、插入解散原因、删除聊天室，保留消息，发送解散通知"""
    # 先获取聊天室名称和成员列表（删除前）
    chat = conn.execute('SELECT name FROM groups_chat WHERE group_id=?', (group_id,)).fetchone()
    chat_name = chat['name'] if chat else group_id
    members = conn.execute('SELECT uid FROM group_members WHERE group_id=?', (group_id,)).fetchall()

    conn.execute('DELETE FROM group_members WHERE group_id=?', (group_id,))
    conn.execute('INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)',
                 (group_id, 'system', reason, 'system', time.time()))
    # 发送系统通知给所有成员
    now = time.time()
    for m in members:
        conn.execute(
            "INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, status, created_at) VALUES ('system', 'system', ?, ?, '{}', 'sent', ?)",
            (m['uid'], f'聊天室「{chat_name}」已解散', now))
    conn.execute('DELETE FROM groups_chat WHERE group_id=?', (group_id,))
    conn.execute('DELETE FROM user_group_chats WHERE chat_id=?', (group_id,))
    conn.commit()

@app.route('/api/groups/<group_id>/leave', methods=['POST'])
@token_required
def leave_group(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    member = conn.execute('SELECT role FROM group_members WHERE group_id=? AND uid=?',(group_id,uid)).fetchone()
    if not member: return jsonify({'error':'你不在群中'}),403
    # 检查是否为系统创建的聊天室（课程/班级群等）
    chat = conn.execute('SELECT creator FROM groups_chat WHERE group_id=?', (group_id,)).fetchone()
    if chat and chat['creator'] == 'system':
        conn.close()
        return jsonify({'error':'系统聊天室无法退出！'}),403
    if member['role'] == 'admin':
        count = conn.execute('SELECT COUNT(*) FROM group_members WHERE group_id=?',(group_id,)).fetchone()[0]
        if count > 1:
            return jsonify({'error':'群主不能退出，请转让群主'}),403
    user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
    user_name = user['name'] if user else uid
    conn.execute('INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)',
                 (group_id, 'system', user_name + ' 退出了聊天室', 'system', time.time()))
    conn.execute('DELETE FROM group_members WHERE group_id=? AND uid=?',(group_id,uid))
    conn.commit()
    # 自动解散：退出后只剩≤1人
    remaining = conn.execute('SELECT COUNT(*) FROM group_members WHERE group_id=?',(group_id,)).fetchone()[0]
    if remaining <= 1:
        _dissolve_chat_room(conn, group_id, '聊天室人员只剩一人，已自动解散')
    conn.close()
    return jsonify({'message':'已退出'})

@app.route('/api/groups/<group_id>/detail', methods=['GET'])
@token_required
def chat_room_detail(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    if not conn.execute('SELECT 1 FROM group_members WHERE group_id=? AND uid=?',(group_id,uid)).fetchone():
        return jsonify({'error':'无权访问'}),403
    chat = conn.execute('SELECT * FROM groups_chat WHERE group_id=?', (group_id,)).fetchone()
    if not chat: return jsonify({'error':'聊天室不存在'}),404
    category = chat['category'] or ''
    is_course = (chat['creator'] == 'system' and category == '课程')
    is_event = (chat['creator'] == 'system' and category == '赛事')
    is_class = (chat['creator'] == 'system' and category == '班级')
    # 课程聊天室：提取 lesson_id，获取教师 uid
    teacher_uid = None
    lesson_id = None
    if is_course and group_id.startswith('chat_'):
        lesson_id = group_id[5:]
        lesson = conn.execute('SELECT teacher_uid FROM lesson WHERE lesson_id=?', (lesson_id,)).fetchone()
        if lesson:
            teacher_uid = lesson['teacher_uid']
    # 赛事聊天室：获取负责人 uid
    event_creator_uid = None
    if is_event and group_id.startswith('chat_event_'):
        eid = group_id[11:]
        ev = conn.execute('SELECT creator_uid FROM events WHERE id=?', (eid,)).fetchone()
        if ev:
            event_creator_uid = ev['creator_uid']
    # 班级聊天室：提取 class_id
    class_id_val = None
    class_name = None
    if is_class and group_id.startswith('chat_class_'):
        class_id_val = group_id[11:]
        cls = conn.execute('SELECT class_name FROM classes WHERE class_id=?', (class_id_val,)).fetchone()
        if cls:
            class_name = cls['class_name']
    members = conn.execute('''SELECT gm.uid, gm.role, gm.joined_at, gm.call_notify, u.name
                              FROM group_members gm JOIN users u ON gm.uid = u.uid
                              WHERE gm.group_id=? ORDER BY gm.joined_at''', (group_id,)).fetchall()
    # 为每个成员查询身份职位（按聊天室类型过滤）
    member_list = []
    for m in members:
        positions = []
        if is_course:
            # 课程聊天室：仅查课代表职位（教师角色由前端 roleLabel 显示）
            lp_rows = conn.execute('''SELECT DISTINCT lp.position_name, l.lesson_name
                                       FROM lesson_positions lp
                                       JOIN lesson l ON lp.lesson_id = l.lesson_id
                                       WHERE lp.uid=?''', (m['uid'],)).fetchall()
            for r in lp_rows:
                positions.append({'type':'lesson','label':r['lesson_name']+' '+r['position_name']})
        elif is_class and class_id_val:
            # 班级聊天室：仅查该班级的班干部职位
            cp_rows = conn.execute('''SELECT position_name FROM class_positions
                                       WHERE class_id=? AND uid=?''',
                                    (class_id_val, m['uid'])).fetchall()
            for r in cp_rows:
                positions.append({'type':'class','label':r['position_name']})
        # 普通/赛事聊天室：不查询任何职位
        member_list.append({
            'uid': m['uid'], 'name': m['name'], 'role': m['role'],
            'call_notify': m['call_notify'] or 0, 'positions': positions
        })
    if is_course or is_event:
        member_list.sort(key=lambda x: (0 if x['uid'] in (teacher_uid, event_creator_uid) else 1))
    my_call_notify = None
    for m in member_list:
        if m['uid'] == uid:
            my_call_notify = m['call_notify']
            break
    conn.close()
    result = {
        'group_id': chat['group_id'],
        'name': chat['name'],
        'creator': chat['creator'],
        'group_type': chat['group_type'],
        'category': category,
        'call_notify': my_call_notify or 0,
        'is_system': chat['creator'] == 'system',
        'members': member_list
    }
    if is_course:
        result['lesson_id'] = lesson_id
        result['teacher_uid'] = teacher_uid
    if is_event:
        result['is_event'] = True
    if is_class:
        result['class_id'] = class_id_val
        result['class_name'] = class_name
    return jsonify(result)

@app.route('/api/groups/<group_id>/invite', methods=['POST'])
@token_required
def invite_to_chat(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    if not conn.execute('SELECT 1 FROM group_members WHERE group_id=? AND uid=?', (group_id, uid)).fetchone():
        return jsonify({'error':'你不在聊天室中'}),403
    chat = conn.execute('SELECT name FROM groups_chat WHERE group_id=?', (group_id,)).fetchone()
    chat_name = chat['name'] if chat else '聊天室'
    data = request.get_json()
    members = data.get('members', [])
    now = time.time()
    invited = 0
    for m_uid in members:
        if conn.execute('SELECT 1 FROM users WHERE uid=?', (m_uid,)).fetchone():
            if not conn.execute('SELECT 1 FROM group_members WHERE group_id=? AND uid=?', (group_id, m_uid)).fetchone():
                conn.execute('INSERT INTO chat_invites (chat_id, chat_name, from_uid, to_uid, status, created_at) VALUES (?,?,?,?,?,?)',
                             (group_id, chat_name, uid, m_uid, 'pending', now))
                conn.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, status, created_at) VALUES ('chat_invite', ?, ?, '', json_object('chat_id',?, 'chat_name',?), 'pending', ?)",
                             (uid, m_uid, group_id, chat_name, now))
                invited += 1
    conn.commit()
    conn.close()
    return jsonify({'message':f'已发送 {invited} 份邀请'})

@app.route('/api/groups/<group_id>/kick', methods=['POST'])
@token_required
def kick_from_chat(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    member = conn.execute('SELECT role FROM group_members WHERE group_id=? AND uid=?', (group_id, uid)).fetchone()
    if not member or member['role'] not in ('admin',):
        return jsonify({'error':'仅群主可踢出成员'}),403
    chat = conn.execute('SELECT creator FROM groups_chat WHERE group_id=?', (group_id,)).fetchone()
    if chat and chat['creator'] == 'system':
        conn.close()
        return jsonify({'error':'系统聊天室不能踢出成员'}),403
    data = request.get_json()
    target_uid = data.get('uid', '')
    if target_uid == uid:
        return jsonify({'error':'不能踢出自己'}),400
    target = conn.execute('SELECT role FROM group_members WHERE group_id=? AND uid=?', (group_id, target_uid)).fetchone()
    if not target:
        return jsonify({'error':'该用户不在聊天室中'}),404
    if target['role'] == 'admin':
        return jsonify({'error':'不能踢出群主'}),400
    target_user = conn.execute('SELECT name FROM users WHERE uid=?', (target_uid,)).fetchone()
    target_name = target_user['name'] if target_user else target_uid
    conn.execute('DELETE FROM group_messages WHERE sender=? AND group_id=?', (target_uid, group_id))
    conn.execute('DELETE FROM group_members WHERE group_id=? AND uid=?', (group_id, target_uid))
    conn.execute('INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)',
                 (group_id, 'system', f'{target_name} 已被移出聊天室', 'system', time.time()))
    conn.commit()
    remaining = conn.execute('SELECT COUNT(*) FROM group_members WHERE group_id=?',(group_id,)).fetchone()[0]
    if remaining <= 1:
        _dissolve_chat_room(conn, group_id, '聊天室人员只剩一人，已自动解散')
    conn.close()
    return jsonify({'message':f'已移除 {target_name}'})

@app.route('/api/groups/<group_id>/dissolve', methods=['POST'])
@token_required
def dissolve_chat_room(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    member = conn.execute('SELECT role FROM group_members WHERE group_id=? AND uid=?', (group_id, uid)).fetchone()
    if not member or member['role'] not in ('admin',):
        return jsonify({'error':'仅群主可解散聊天室'}),403
    chat = conn.execute('SELECT creator FROM groups_chat WHERE group_id=?', (group_id,)).fetchone()
    if chat and chat['creator'] == 'system':
        conn.close()
        return jsonify({'error':'系统聊天室不能解散'}),403
    _dissolve_chat_room(conn, group_id, '聊天室已被解散')
    conn.close()
    return jsonify({'message':'聊天室已解散'})
@app.route('/api/groups/<group_id>/rename', methods=['PUT'])
@token_required
def rename_chat(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    member = conn.execute('SELECT role FROM group_members WHERE group_id=? AND uid=?', (group_id, uid)).fetchone()
    if not member or member['role'] not in ('admin',):
        return jsonify({'error':'仅群主和管理员可修改名称'}),403
    name = request.get_json().get('name', '').strip()
    if not name:
        return jsonify({'error':'名称不能为空'}),400
    conn.execute('UPDATE groups_chat SET name=? WHERE group_id=?', (name, group_id))
    conn.commit(); conn.close()
    return jsonify({'message':'名称已修改'})

@app.route('/api/groups/<group_id>/admin', methods=['POST'])
@token_required
def manage_admin(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    member = conn.execute('SELECT role FROM group_members WHERE group_id=? AND uid=?', (group_id, uid)).fetchone()
    if not member or member['role'] != 'admin':
        return jsonify({'error':'仅群主可管理管理员'}),403
    data = request.get_json()
    target_uid = data.get('uid', '')
    action = data.get('action', '')  # 'set' or 'unset'
    target = conn.execute('SELECT role FROM group_members WHERE group_id=? AND uid=?', (group_id, target_uid)).fetchone()
    if not target:
        return jsonify({'error':'该用户不在聊天室中'}),404
    if target['role'] == 'admin':
        return jsonify({'error':'不能修改群主权限'}),400
    if action == 'set':
        conn.execute('UPDATE group_members SET role=? WHERE group_id=? AND uid=?', ('manager', group_id, target_uid))
    elif action == 'unset':
        conn.execute('UPDATE group_members SET role=? WHERE group_id=? AND uid=?', ('member', group_id, target_uid))
    else:
        return jsonify({'error':'无效操作'}),400
    conn.commit(); conn.close()
    return jsonify({'message':'已更新'})

@app.route('/api/groups/<group_id>/announcement', methods=['POST'])
@token_required
def post_chat_announcement(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    member = conn.execute('SELECT role FROM group_members WHERE group_id=? AND uid=?', (group_id, uid)).fetchone()
    if not member or member['role'] not in ('admin', 'manager'):
        return jsonify({'error':'仅群主和管理员可发布公告'}),403
    content = request.get_json().get('content', '').strip()
    if not content:
        return jsonify({'error':'公告内容不能为空'}),400
    user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
    user_name = user['name'] if user else uid
    conn.execute('INSERT INTO group_messages (group_id, sender, content, msg_type, timestamp) VALUES (?,?,?,?,?)',
                 (group_id, 'system', f'📢 公告 - {user_name}: {content}', 'system', time.time()))
    conn.commit(); conn.close()
    return jsonify({'message':'公告已发布'})

# ---------- 课代表管理 ----------
@app.route('/api/lesson-positions/set', methods=['POST'])
@token_required
def set_lesson_position():
    """设为课代表"""
    uid = g.current_user['uid']
    data = request.get_json()
    lesson_id = data.get('lesson_id', '').strip()
    target_uid = data.get('uid', '').strip()
    if not lesson_id or not target_uid:
        return jsonify({'error':'参数不全'}),400
    conn = get_db()
    # 仅该课程教师可设置课代表
    lesson = conn.execute('SELECT * FROM lesson WHERE lesson_id=?', (lesson_id,)).fetchone()
    if not lesson:
        conn.close(); return jsonify({'error':'课程不存在'}),404
    if lesson['teacher_uid'] != uid:
        conn.close(); return jsonify({'error':'仅授课教师可设置课代表'}),403
    # 检查目标用户是否在该课程的聊天室中
    chat_id = 'chat_' + lesson_id
    if not conn.execute('SELECT 1 FROM group_members WHERE group_id=? AND uid=?', (chat_id, target_uid)).fetchone():
        conn.close(); return jsonify({'error':'该用户不在本课程聊天室中'}),404
    conn.execute('INSERT OR IGNORE INTO lesson_positions (lesson_id, uid, position_name) VALUES (?,?,?)',
                 (lesson_id, target_uid, '课代表'))
    conn.commit(); conn.close()
    return jsonify({'message':'已设为课代表'})

@app.route('/api/lesson-positions/unset', methods=['POST'])
@token_required
def unset_lesson_position():
    """取消课代表"""
    uid = g.current_user['uid']
    data = request.get_json()
    lesson_id = data.get('lesson_id', '').strip()
    target_uid = data.get('uid', '').strip()
    if not lesson_id or not target_uid:
        return jsonify({'error':'参数不全'}),400
    conn = get_db()
    lesson = conn.execute('SELECT * FROM lesson WHERE lesson_id=?', (lesson_id,)).fetchone()
    if not lesson:
        conn.close(); return jsonify({'error':'课程不存在'}),404
    if lesson['teacher_uid'] != uid:
        conn.close(); return jsonify({'error':'仅授课教师可取消课代表'}),403
    conn.execute('DELETE FROM lesson_positions WHERE lesson_id=? AND uid=?', (lesson_id, target_uid))
    conn.commit(); conn.close()
    return jsonify({'message':'已取消课代表'})

# ---------- 公告 ----------
@app.route('/api/announcements', methods=['GET'])
@token_required
def get_announcements():
    unit = request.args.get('unit','')
    conn = get_db()
    if unit and unit != '全部':
        anns = conn.execute('SELECT * FROM announcements WHERE unit=? ORDER BY created_at DESC', (unit,)).fetchall()
    else:
        anns = conn.execute('SELECT * FROM announcements ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([{'id':a['id'],'publisher':a['publisher'],'unit':a['unit'],
                     'title':a['title'],'content':a['content'],
                     'created_at':a['created_at'],'modified_at':a['modified_at']} for a in anns])

@app.route('/api/announcements', methods=['POST'])
@token_required
def create_announcement():
    user = g.current_user
    if user['role'] == 'student':
        return jsonify({'error':'学生不能发布公告'}),403
    data = request.get_json()
    title = data.get('title','').strip()
    content = data.get('content','').strip()
    unit = data.get('unit','').strip()
    if not title or len(title)>100: return jsonify({'error':'标题1-100字符'}),400
    if not content or len(content)>10000: return jsonify({'error':'正文1-10000字符'}),400
    if user['role'] == 'teacher' and unit not in ('计算机学院','教务处','数学学院'):
        unit = '计算机学院'  # 默认教师所在学院
    now = time.time()
    conn = get_db()
    conn.execute('INSERT INTO announcements (publisher,unit,title,content,attachments,created_at,modified_at) VALUES (?,?,?,?,?,?,?)',
                 (user['uid'], unit, title, content, '[]', now, now))
    conn.commit(); conn.close()
    return jsonify({'message':'发布成功'}),201

@app.route('/api/announcements/<int:id>', methods=['PUT'])
@token_required
def update_announcement(id):
    user = g.current_user
    conn = get_db()
    ann = conn.execute('SELECT * FROM announcements WHERE id=?',(id,)).fetchone()
    if not ann: return jsonify({'error':'公告不存在'}),404
    if user['role'] != 'manager' and ann['publisher'] != user['uid']:
        return jsonify({'error':'无权修改'}),403
    data = request.get_json()
    title = data.get('title',ann['title'])
    content = data.get('content',ann['content'])
    now = time.time()
    conn.execute('UPDATE announcements SET title=?,content=?,modified_at=?,modifier=? WHERE id=?',
                 (title, content, now, user['uid'], id))
    conn.commit(); conn.close()
    return jsonify({'message':'修改成功'})

@app.route('/api/announcements/<int:id>', methods=['DELETE'])
@token_required
def delete_announcement(id):
    user = g.current_user
    conn = get_db()
    ann = conn.execute('SELECT * FROM announcements WHERE id=?',(id,)).fetchone()
    if not ann: return jsonify({'error':'公告不存在'}),404
    if user['role'] != 'manager' and ann['publisher'] != user['uid']:
        return jsonify({'error':'无权删除'}),403
    conn.execute('DELETE FROM announcements WHERE id=?',(id,))
    conn.commit(); conn.close()
    return jsonify({'message':'已删除'})

# ---------- 查询 ----------
@app.route('/api/search/users', methods=['GET'])
@token_required
def search_users():
    name_or_id = request.args.get('name_or_id', '').strip()
    course = request.args.get('course', '').strip()
    class_name = request.args.get('class', '').strip()
    position = request.args.get('position', '').strip()
    event_id = request.args.get('event_id', '').strip()
    if not any([name_or_id, course, class_name, position, event_id]):
        return jsonify([])
    conn = get_db()
    query = 'SELECT DISTINCT u.uid, u.name, u.role FROM users u WHERE 1=1'
    params = []
    if name_or_id:
        query += ' AND (u.uid LIKE ? OR u.name LIKE ?)'
        params.extend([f'%{name_or_id}%', f'%{name_or_id}%'])
    if course:
        query += ''' AND u.uid IN (SELECT stu_uid FROM lesson_stu ls
                     JOIN lesson l ON ls.lesson_id=l.lesson_id
                     WHERE l.lesson_name LIKE ?)'''
        params.append(f'%{course}%')
    if class_name:
        query += ''' AND u.uid IN (SELECT uid FROM class_stu cs
                     JOIN classes c ON cs.class_id=c.class_id
                     WHERE c.class_name LIKE ?)'''
        params.append(f'%{class_name}%')
    if position:
        query += ''' AND u.uid IN (SELECT uid FROM class_positions WHERE position_name LIKE ?
                     UNION SELECT uid FROM lesson_positions WHERE position_name LIKE ?)'''
        params.extend([f'%{position}%', f'%{position}%'])
    if event_id:
        query += ''' AND u.uid IN (SELECT member_uid FROM events_groups_members egm
                     JOIN events_groups eg ON egm.group_id=eg.id WHERE eg.event_id=?)'''
        params.append(event_id)
    users = conn.execute(query, params).fetchall()
    result = []
    for u in users:
        tags = []
        cp_rows = conn.execute('''SELECT DISTINCT cp.position_name, c.class_name
                                   FROM class_positions cp
                                   JOIN class_stu cs ON cp.class_id=cs.class_id AND cp.uid=cs.uid
                                   JOIN classes c ON cp.class_id=c.class_id
                                   WHERE cs.uid=?''', (u['uid'],)).fetchall()
        for r in cp_rows:
            tags.append({'type':'class','label':f"{r['class_name']} {r['position_name']}"})
        lp_rows = conn.execute('''SELECT DISTINCT lp.position_name, l.lesson_name
                                   FROM lesson_positions lp
                                   JOIN lesson l ON lp.lesson_id=l.lesson_id
                                   WHERE lp.uid=?''', (u['uid'],)).fetchall()
        for r in lp_rows:
            tags.append({'type':'lesson','label':f"{r['lesson_name']} {r['position_name']}"})
        ev_rows = conn.execute('''SELECT DISTINCT e.name
                                   FROM events_groups_members egm
                                   JOIN events_groups eg ON egm.group_id=eg.id
                                   JOIN events e ON eg.event_id=e.id
                                   WHERE egm.member_uid=?''', (u['uid'],)).fetchall()
        for r in ev_rows:
            tags.append({'type':'event','label':f"参赛-{r['name']}"})
        result.append({'uid':u['uid'],'name':u['name'],'role':u['role'],'tags':tags})
    conn.close()
    return jsonify(result)

@app.route('/api/search/options', methods=['GET'])
@token_required
def search_options():
    type_ = request.args.get('type', '')
    conn = get_db()
    if type_ == 'courses':
        rows = conn.execute('SELECT DISTINCT lesson_name FROM lesson ORDER BY lesson_name').fetchall()
        conn.close()
        return jsonify([r['lesson_name'] for r in rows])
    elif type_ == 'classes':
        rows = conn.execute('SELECT DISTINCT class_name FROM classes ORDER BY class_name').fetchall()
        conn.close()
        return jsonify([r['class_name'] for r in rows])
    conn.close()
    return jsonify([])

@app.route('/api/classrooms/free', methods=['GET'])
@token_required
def free_classrooms():
    date = request.args.get('date',''); start = request.args.get('start',''); end = request.args.get('end','')
    conn = get_db()
    rooms = conn.execute('SELECT * FROM classrooms').fetchall()
    conn.close()
    return jsonify([{'id':r['id'],'building':r['building'],'floor':r['floor'],
                     'seats':r['seats'],'media':'有' if r['has_media'] else '无'} for r in rooms])

@app.route('/api/events', methods=['GET'])
@token_required
def get_events():
    conn = get_db()
    events = conn.execute('SELECT * FROM events ORDER BY start_time ASC').fetchall()
    conn.close()
    return jsonify([{'id':e['id'],'name':e['name'],'type':e['type'],'start_time':e['start_time'],
                     'end_time':e['end_time'],'location':e['location'],'target':e['target'],
                     'organizer':e['organizer'],'description':e['description'],'creator_uid':e['creator_uid']} for e in events])

@app.route('/api/events/<int:event_id>', methods=['GET'])
@token_required
def get_event_detail(event_id):
    conn = get_db()
    event = conn.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'error': '赛事不存在'}), 404
    groups = conn.execute('''SELECT eg.*, u.name as leader_name,
        (SELECT COUNT(*) FROM events_groups_members WHERE group_id=eg.id) as member_count
        FROM events_groups eg JOIN users u ON eg.leader_uid=u.uid
        WHERE eg.event_id=? ORDER BY eg.created_at''', (event_id,)).fetchall()
    uid = g.current_user['uid']
    my_group = conn.execute('''SELECT egm.group_id FROM events_groups_members egm
        JOIN events_groups eg ON egm.group_id=eg.id
        WHERE eg.event_id=? AND egm.member_uid=?''', (event_id, uid)).fetchone()
    conn.close()
    return jsonify({
        'id': event['id'],
        'name': event['name'],
        'type': event['type'],
        'start_time': event['start_time'],
        'end_time': event['end_time'],
        'location': event['location'],
        'target': event['target'],
        'organizer': event['organizer'],
        'description': event['description'],
        'creator_uid': event['creator_uid'],
        'groups': [{
            'id': g['id'],
            'group_name': g['group_name'],
            'leader_uid': g['leader_uid'],
            'leader_name': g['leader_name'],
            'status': g['status'],
            'max_members': g['max_members'],
            'description': g['description'],
            'member_count': g['member_count'],
            'created_at': g['created_at']
        } for g in groups],
        'my_group_id': my_group['group_id'] if my_group else None
    })

@app.route('/api/events', methods=['POST'])
@token_required
def create_event():
    if g.current_user['role'] != 'manager':
        return jsonify({'error': '仅管理员可发布赛事'}), 403
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO events (name, type, start_time, end_time, location, target, organizer, description, creator_uid)
                 VALUES (?,?,?,?,?,?,?,?,?)''',
              (data['name'], data.get('type',''), data.get('start_time',''),
               data.get('end_time',''), data.get('location',''), data.get('target',''),
               data.get('organizer',''), data.get('description',''), g.current_user['uid']))
    eid = c.lastrowid
    chat_id = 'chat_event_' + str(eid)
    now = time.time()
    c.execute('INSERT OR IGNORE INTO groups_chat VALUES (?,?,?,?,?,?)',
              (chat_id, data['name'] + '聊天室', 'system', now, 'system', '赛事'))
    c.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)',
              (chat_id, g.current_user['uid'], 'admin', now, 0))
    # 同步到管理员的"赛事"系统群组
    admin_group_id = 'sys_events_' + g.current_user['uid']
    c.execute('INSERT OR IGNORE INTO user_group_chats VALUES (?,?,?)',
              (admin_group_id, chat_id, data['name']))
    conn.commit()
    conn.close()
    return jsonify({'message': '赛事发布成功', 'event_id': eid}), 201

@app.route('/api/events/<int:event_id>/groups', methods=['POST'])
@token_required
def create_event_group(event_id):
    uid = g.current_user['uid']
    data = request.get_json()
    group_name = data.get('group_name', '').strip()
    if not group_name:
        return jsonify({'error': '小组名称不能为空'}), 400
    max_members = data.get('max_members', 4)
    if not isinstance(max_members, int) or max_members < 2 or max_members > 20:
        return jsonify({'error': '人数上限需为2-20的整数'}), 400
    conn = get_db()
    existing = conn.execute('''SELECT 1 FROM events_groups_members egm
        JOIN events_groups eg ON egm.group_id=eg.id
        WHERE eg.event_id=? AND egm.member_uid=?''', (event_id, uid)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': '你已在该赛事的小组中，不能创建新小组'}), 400
    c = conn.cursor()
    c.execute('INSERT INTO events_groups (event_id, group_name, leader_uid, max_members, description) VALUES (?,?,?,?,?)',
              (event_id, group_name, uid, max_members, data.get('description', '')))
    gid = c.lastrowid
    c.execute('INSERT INTO events_groups_members (group_id, member_uid) VALUES (?,?)', (gid, uid))
    # 将创建者加入赛事聊天室
    chat_id = 'chat_event_' + str(event_id)
    now_ts = time.time()
    c.execute('INSERT OR IGNORE INTO group_members VALUES (?,?,?,?,?)', (chat_id, uid, 'member', now_ts, 0))
    # 同步到创建者的"赛事"系统群组
    c.execute('INSERT OR IGNORE INTO user_group_chats (group_id, chat_id, chat_name) '
              'SELECT ?, ?, name FROM events WHERE id=?',
              ('sys_events_' + uid, chat_id, event_id))
    conn.commit()
    conn.close()
    return jsonify({'message': '小组创建成功', 'group_id': gid}), 201

@app.route('/api/events/groups/search', methods=['GET'])
@token_required
def search_event_group_member():
    eid = request.args.get('eid', type=int)
    uid = request.args.get('uid', '').strip()
    if not eid or not uid:
        return jsonify({'error': '参数不足'}), 400
    conn = get_db()
    group = conn.execute('''SELECT eg.*, u.name as leader_name,
        (SELECT COUNT(*) FROM events_groups_members WHERE group_id=eg.id) as member_count
        FROM events_groups eg
        JOIN events_groups_members egm ON eg.id = egm.group_id
        JOIN users u ON eg.leader_uid=u.uid
        WHERE eg.event_id=? AND egm.member_uid=?''', (eid, uid)).fetchone()
    conn.close()
    if group:
        return jsonify({'found': True, 'group': {
            'id': group['id'], 'group_name': group['group_name'],
            'leader_name': group['leader_name'], 'status': group['status'],
            'member_count': group['member_count'],
            'max_members': group['max_members']
        }})
    return jsonify({'found': False})

@app.route('/api/events/groups/<int:gid>/status', methods=['PUT'])
@token_required
def set_event_group_status(gid):
    uid = g.current_user['uid']
    data = request.get_json()
    new_status = data.get('status', 'full')
    if new_status not in ('recruiting', 'full'):
        return jsonify({'error': '无效的状态值'}), 400
    conn = get_db()
    group = conn.execute('SELECT * FROM events_groups WHERE id=?', (gid,)).fetchone()
    if not group:
        return jsonify({'error': '小组不存在'}), 404
    if group['leader_uid'] != uid:
        return jsonify({'error': '仅组长可修改状态'}), 403
    conn.execute('UPDATE events_groups SET status=? WHERE id=?', (new_status, gid))
    conn.commit()
    conn.close()
    return jsonify({'message': f'状态已更新为 {new_status}'})

@app.route('/api/events/groups/<int:gid>/apply', methods=['POST'])
@token_required
def apply_join_event_group(gid):
    uid = g.current_user['uid']
    data = request.get_json()
    message = data.get('message', '') or '我想加入你的小组'
    conn = get_db()
    group = conn.execute('''SELECT eg.*, e.name as event_name FROM events_groups eg
        JOIN events e ON eg.event_id=e.id WHERE eg.id=?''', (gid,)).fetchone()
    if not group:
        return jsonify({'error': '小组不存在'}), 404
    if group['status'] == 'full':
        return jsonify({'error': '该小组已满员'}), 400
    existing = conn.execute('SELECT 1 FROM events_groups_members WHERE group_id=? AND member_uid=?', (gid, uid)).fetchone()
    if existing:
        return jsonify({'error': '你已在该小组中'}), 400
    # 检查是否已在该赛事的其他小组中
    other_group = conn.execute('''SELECT 1 FROM events_groups_members egm
        JOIN events_groups eg ON egm.group_id=eg.id
        WHERE eg.event_id=? AND egm.member_uid=? AND eg.id!=?''', (group['event_id'], uid, gid)).fetchone()
    if other_group:
        conn.close()
        return jsonify({'error': '你已在该赛事的其他小组中'}), 400
    now = time.time()
    sender_user = conn.execute('SELECT name FROM users WHERE uid=?', (uid,)).fetchone()
    sender_name = sender_user['name'] if sender_user else uid
    conn.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, extra, status, created_at) VALUES (?,?,?,?,?,'pending',?)",
                 ('group_join', uid, group['leader_uid'], message,
                  json.dumps({'group_id': gid, 'group_name': group['group_name'], 'event_name': group['event_name']}),
                  now))
    conn.commit()
    conn.close()
    return jsonify({'message': '申请已发送，等待组长审批'})

@app.route('/api/events/groups/<int:gid>/members/<member_uid>', methods=['DELETE'])
@token_required
def leave_event_group(gid, member_uid):
    uid = g.current_user['uid']
    conn = get_db()
    group = conn.execute('SELECT * FROM events_groups WHERE id=?', (gid,)).fetchone()
    if not group:
        return jsonify({'error': '小组不存在'}), 404
    if member_uid != uid:
        if group['leader_uid'] != uid:
            return jsonify({'error': '无权操作'}), 403
    if member_uid == group['leader_uid']:
        return jsonify({'error': '组长不能退出，请先转让组长或解散小组'}), 400
    check = conn.execute('SELECT 1 FROM events_groups_members WHERE group_id=? AND member_uid=?', (gid, member_uid)).fetchone()
    if not check:
        conn.close()
        return jsonify({'error': '该成员不在此小组中'}), 404
    conn.execute('DELETE FROM events_groups_members WHERE group_id=? AND member_uid=?', (gid, member_uid))
    # 从赛事聊天室移除
    chat_id = 'chat_event_' + str(group['event_id'])
    conn.execute('DELETE FROM group_members WHERE group_id=? AND uid=?', (chat_id, member_uid))
    # 从退出者的"赛事"系统群组移除
    conn.execute('DELETE FROM user_group_chats WHERE group_id=? AND chat_id=?',
                 ('sys_events_' + member_uid, chat_id))
    # 如果之前满员，退出后人数低于上限则恢复招募中
    if group['status'] == 'full':
        remaining = conn.execute('SELECT COUNT(*) FROM events_groups_members WHERE group_id=?', (gid,)).fetchone()[0]
        if remaining < group['max_members']:
            conn.execute('UPDATE events_groups SET status=? WHERE id=?', ('recruiting', gid))
    conn.commit()
    conn.close()
    return jsonify({'message': '已退出小组'})

@app.route('/api/events/groups/<int:gid>/members', methods=['GET'])
@token_required
def get_event_group_members(gid):
    conn = get_db()
    group = conn.execute('SELECT * FROM events_groups WHERE id=?', (gid,)).fetchone()
    if not group:
        conn.close()
        return jsonify({'error': '小组不存在'}), 404
    members = conn.execute('''SELECT egm.member_uid, u.name, u.role
        FROM events_groups_members egm JOIN users u ON egm.member_uid=u.uid
        WHERE egm.group_id=? ORDER BY egm.id''', (gid,)).fetchall()
    conn.close()
    return jsonify([{
        'member_uid': m['member_uid'],
        'name': m['name'],
        'role': m['role'],
        'is_leader': m['member_uid'] == group['leader_uid']
    } for m in members])

@app.route('/api/events/groups/<int:gid>/kick', methods=['POST'])
@token_required
def kick_event_group_member(gid):
    uid = g.current_user['uid']
    data = request.get_json()
    target_uid = data.get('uid', '').strip()
    if not target_uid:
        return jsonify({'error': '参数不足'}), 400
    conn = get_db()
    group = conn.execute('SELECT * FROM events_groups WHERE id=?', (gid,)).fetchone()
    if not group:
        conn.close()
        return jsonify({'error': '小组不存在'}), 404
    if group['leader_uid'] != uid:
        conn.close()
        return jsonify({'error': '仅组长可踢出成员'}), 403
    if target_uid == uid:
        conn.close()
        return jsonify({'error': '不能踢出自己'}), 400
    if target_uid == group['leader_uid']:
        conn.close()
        return jsonify({'error': '不能踢出组长'}), 400
    check = conn.execute('SELECT 1 FROM events_groups_members WHERE group_id=? AND member_uid=?', (gid, target_uid)).fetchone()
    if not check:
        conn.close()
        return jsonify({'error': '该成员不在此小组中'}), 404
    conn.execute('DELETE FROM events_groups_members WHERE group_id=? AND member_uid=?', (gid, target_uid))
    chat_id = 'chat_event_' + str(group['event_id'])
    conn.execute('DELETE FROM group_members WHERE group_id=? AND uid=?', (chat_id, target_uid))
    conn.execute('DELETE FROM user_group_chats WHERE group_id=? AND chat_id=?',
                 ('sys_events_' + target_uid, chat_id))
    if group['status'] == 'full':
        remaining = conn.execute('SELECT COUNT(*) FROM events_groups_members WHERE group_id=?', (gid,)).fetchone()[0]
        if remaining < group['max_members']:
            conn.execute('UPDATE events_groups SET status=? WHERE id=?', ('recruiting', gid))
    conn.commit()
    conn.close()
    return jsonify({'message': '已踢出成员'})

@app.route('/api/events/groups/<int:gid>/transfer', methods=['POST'])
@token_required
def transfer_event_group_leader(gid):
    uid = g.current_user['uid']
    data = request.get_json()
    new_leader_uid = data.get('uid', '').strip()
    if not new_leader_uid:
        return jsonify({'error': '参数不足'}), 400
    conn = get_db()
    group = conn.execute('SELECT * FROM events_groups WHERE id=?', (gid,)).fetchone()
    if not group:
        conn.close()
        return jsonify({'error': '小组不存在'}), 404
    if group['leader_uid'] != uid:
        conn.close()
        return jsonify({'error': '仅组长可转让组长'}), 403
    if new_leader_uid == uid:
        conn.close()
        return jsonify({'error': '不能转让给自己'}), 400
    check = conn.execute('SELECT 1 FROM events_groups_members WHERE group_id=? AND member_uid=?', (gid, new_leader_uid)).fetchone()
    if not check:
        conn.close()
        return jsonify({'error': '目标用户不在此小组中'}), 404
    conn.execute('UPDATE events_groups SET leader_uid=? WHERE id=?', (new_leader_uid, gid))
    conn.commit()
    conn.close()
    return jsonify({'message': '组长已转让'})

@app.route('/api/events/groups/<int:gid>/dissolve', methods=['POST'])
@token_required
def dissolve_event_group(gid):
    uid = g.current_user['uid']
    conn = get_db()
    group = conn.execute('SELECT eg.*, e.name as event_name FROM events_groups eg JOIN events e ON eg.event_id=e.id WHERE eg.id=?', (gid,)).fetchone()
    if not group:
        conn.close()
        return jsonify({'error': '小组不存在'}), 404
    if group['leader_uid'] != uid:
        conn.close()
        return jsonify({'error': '仅组长可解散小组'}), 403
    # 获取所有成员列表（用于通知和清理）
    members = conn.execute('SELECT member_uid FROM events_groups_members WHERE group_id=?', (gid,)).fetchall()
    chat_id = 'chat_event_' + str(group['event_id'])
    now = time.time()
    # 给每个成员发送解散通知（除组长自己外）
    for m in members:
        if m['member_uid'] != uid:
            conn.execute("INSERT INTO notifications (type, sender_uid, receiver_uid, content, status, created_at) VALUES (?,?,?,?,'sent',?)",
                         ('system', uid, m['member_uid'], f'小组「{group["group_name"]}」已解散（赛事：{group["event_name"]}）', now))
        # 从聊天室移除
        conn.execute('DELETE FROM group_members WHERE group_id=? AND uid=?', (chat_id, m['member_uid']))
        # 从赛事群组移除
        conn.execute('DELETE FROM user_group_chats WHERE group_id=? AND chat_id=?',
                     ('sys_events_' + m['member_uid'], chat_id))
    # 删除小组成员记录
    conn.execute('DELETE FROM events_groups_members WHERE group_id=?', (gid,))
    # 删除小组
    conn.execute('DELETE FROM events_groups WHERE id=?', (gid,))
    conn.commit()
    conn.close()
    return jsonify({'message': '小组已解散'})

@app.route('/api/tutor_duty', methods=['GET'])
@token_required
def tutor_duty():
    date = request.args.get('date',''); college = request.args.get('college','')
    conn = get_db()
    if college:
        duties = conn.execute('SELECT * FROM tutor_duty WHERE duty_date=? AND college=?',(date,college)).fetchall()
    else:
        duties = conn.execute('SELECT * FROM tutor_duty WHERE duty_date=?',(date,)).fetchall()
    conn.close()
    return jsonify([{'teacher_name':d['teacher_name'],'teacher_uid':d['teacher_uid'],
                     'college':d['college'],'duty_date':d['duty_date'],
                     'start_time':d['start_time'],'end_time':d['end_time'],
                     'location':d['location'],'contact':d['contact']} for d in duties])

@app.route('/api/teacher_office', methods=['GET'])
@token_required
def teacher_office():
    college = request.args.get('college','')
    conn = get_db()
    if college:
        offices = conn.execute('SELECT * FROM teacher_office WHERE college=?',(college,)).fetchall()
    else:
        offices = conn.execute('SELECT * FROM teacher_office').fetchall()
    conn.close()
    return jsonify([{'name':o['name'],'uid':o['uid'],'college':o['college'],
                     'title':o['title'],'office':o['office'],'phone':o['phone']} for o in offices])

@app.route('/api/course_schedule', methods=['GET'])
@token_required
def course_schedule():
    classroom = request.args.get('classroom','')
    conn = get_db()
    if classroom:
        courses = conn.execute('SELECT * FROM course_schedule WHERE classroom_id=?',(classroom,)).fetchall()
    else:
        courses = conn.execute('SELECT * FROM course_schedule').fetchall()
    conn.close()
    return jsonify([{'course_name':c['course_name'],'teacher':c['teacher'],
                     'classroom':c['classroom_id'],'day_of_week':c['day_of_week'],
                     'start_time':c['start_time'],'end_time':c['end_time']} for c in courses])

# ---------- 语音/视频通话信令 ----------
user_heartbeats = {}  # uid -> last heartbeat timestamp
call_events = {}      # uid -> [event, ...]
active_calls = {}     # call_id -> {caller, callee, caller_name, callee_name, call_type, status, created_at}

@app.route('/api/groups/<group_id>/call-setting', methods=['POST'])
@token_required
def set_call_notify(group_id):
    uid = g.current_user['uid']
    data = request.get_json()
    call_notify = data.get('call_notify', 0)
    conn = get_db()
    chat = conn.execute('SELECT * FROM groups_chat WHERE group_id=?', (group_id,)).fetchone()
    if not chat:
        conn.close()
        return jsonify({'error': '聊天室不存在'}), 404
    # 系统聊天室强制开启，不可修改
    if chat['creator'] == 'system' and call_notify != 1:
        conn.close()
        return jsonify({'error': '系统聊天室强制开启通话通知'}), 403
    # 检查用户是否在聊天室中
    if not conn.execute('SELECT 1 FROM group_members WHERE group_id=? AND uid=?', (group_id, uid)).fetchone():
        conn.close()
        return jsonify({'error': '你不是该聊天室成员'}), 403
    conn.execute('UPDATE group_members SET call_notify=? WHERE group_id=? AND uid=?', (call_notify, group_id, uid))
    conn.commit()
    conn.close()
    return jsonify({'message': '设置成功', 'call_notify': call_notify})

@app.route('/api/call/preference', methods=['GET', 'POST'])
@token_required
def call_preference():
    uid = g.current_user['uid']
    conn = get_db()
    if request.method == 'GET':
        target_uid = request.args.get('with', '').strip()
        if not target_uid:
            return jsonify({'error': '参数不完整'}), 400
        row = conn.execute('SELECT call_notify FROM user_relations WHERE uid=? AND target_uid=?', (uid, target_uid)).fetchone()
        conn.close()
        return jsonify({'call_notify': row['call_notify'] if row else 0})
    else:
        data = request.get_json()
        target_uid = data.get('target_uid', '').strip()
        call_notify = data.get('call_notify', 0)
        if not target_uid:
            return jsonify({'error': '参数不完整'}), 400
        conn.execute('INSERT OR REPLACE INTO call_preferences (uid, target_uid, call_notify) VALUES (?,?,?)',
                     (uid, target_uid, call_notify))
        conn.execute("INSERT INTO user_relations (uid, target_uid, call_notify) VALUES (?,?,?) ON CONFLICT(uid,target_uid) DO UPDATE SET call_notify=?",
                     (uid, target_uid, call_notify, call_notify))
        conn.commit()
        conn.close()
        return jsonify({'message': '设置成功', 'call_notify': call_notify})

@app.route('/api/call/check-online', methods=['POST'])
@token_required
def call_check_online():
    data = request.get_json()
    target_uid = data.get('uid', '').strip()
    last_seen = user_heartbeats.get(target_uid, 0)
    online = time.time() - last_seen < 3600
    return jsonify({'online': online})

@app.route('/api/call/invite', methods=['POST'])
@token_required
def call_invite():
    sender = g.current_user['uid']
    data = request.get_json()
    target_uid = data.get('target_uid', '').strip()
    call_type = data.get('call_type', 'video')
    if not target_uid:
        return jsonify({'error': '参数不完整'}), 400
    last_seen = user_heartbeats.get(target_uid, 0)
    if time.time() - last_seen > 15:
        return jsonify({'error': '对方未在线'}), 400
    # 检查对方是否允许通话通知（私聊）
    conn = get_db()
    pref = conn.execute('SELECT call_notify FROM user_relations WHERE uid=? AND target_uid=?', (target_uid, sender)).fetchone()
    if pref and pref['call_notify'] == 0:
        conn.close()
        return jsonify({'error': '你没有通话权限！'}), 400
    user = conn.execute('SELECT name FROM users WHERE uid=?', (sender,)).fetchone()
    conn.close()
    sender_name = user['name'] if user else sender
    call_id = str(uuid.uuid4())[:8]
    active_calls[call_id] = {
        'caller': sender, 'callee': target_uid,
        'caller_name': sender_name, 'callee_name': '',
        'call_type': call_type, 'status': 'ringing', 'created_at': time.time()
    }
    # Queue event for target
    call_events.setdefault(target_uid, []).append({
        'type': 'call_invite', 'call_id': call_id,
        'from_uid': sender, 'from_name': sender_name, 'call_type': call_type
    })
    return jsonify({'call_id': call_id, 'message': '通话邀请已发送'}), 201

@app.route('/api/call/respond', methods=['POST'])
@token_required
def call_respond():
    uid = g.current_user['uid']
    data = request.get_json()
    call_id = data.get('call_id', '')
    action = data.get('action', '')
    call = active_calls.get(call_id)
    if not call:
        return jsonify({'error': '通话不存在'}), 404
    if action == 'accept':
        call['status'] = 'connected'
        call_events.setdefault(call['caller'], []).append({
            'type': 'call_accepted', 'call_id': call_id
        })
    elif action == 'reject':
        call['status'] = 'rejected'
        call_events.setdefault(call['caller'], []).append({
            'type': 'call_rejected', 'call_id': call_id
        })
    elif action == 'hangup':
        call['status'] = 'ended'
        other = call['callee'] if uid == call['caller'] else call['caller']
        call_events.setdefault(other, []).append({
            'type': 'call_hangup', 'call_id': call_id
        })
    return jsonify({'message': '操作成功'})

# Extend SSE stream to deliver call events and track heartbeat
_original_generate = None
# We monkey-patch the stream endpoint to add call event delivery
@app.route('/api/call/events')
def call_events_stream():
    uid = request.args.get('uid', '')
    token = request.args.get('token', '')
    if not uid or not token or tokens.get(token) != uid:
        return jsonify({'error': '认证失败'}), 401
    def generate():
        tick = 0
        while True:
            user_heartbeats[uid] = time.time()
            events = call_events.get(uid, [])
            if events:
                yield f"data: {json.dumps(events, ensure_ascii=False)}\n\n"
                call_events[uid] = []
            else:
                yield ":\n\n"
            tick += 1
            if tick % 20 == 0:
                _cleanup_stale_calls()
            time.sleep(1.5)
    return Response(generate(), mimetype='text/event-stream')

# Periodic cleanup of stale call data (called from SSE streams)
def _cleanup_stale_calls():
    now = time.time()
    for cid in list(active_calls.keys()):
        if now - active_calls[cid].get('created_at', 0) > 120:
            del active_calls[cid]
    for uid in list(call_events.keys()):
        call_events[uid] = [e for e in call_events[uid] if now - e.get('_ts', now) < 30]


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)