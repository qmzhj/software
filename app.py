import sqlite3, hashlib, secrets, re, time, os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g, send_from_directory
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='static', static_url_path='')
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

SALT = "CampusFakeSalt2024!"
tokens = {}

# ---------- 数据库初始化 ----------
def init_db():
    conn = sqlite3.connect('campus.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (uid TEXT PRIMARY KEY, name TEXT, password TEXT, role TEXT,
                  locked INTEGER DEFAULT 0, unlock_time TEXT, login_fails INTEGER DEFAULT 0)''')
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
    c.execute('''CREATE TABLE IF NOT EXISTS classrooms
                 (id TEXT PRIMARY KEY, building TEXT, floor INTEGER, seats INTEGER,
                  has_media INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS course_schedule
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, course_name TEXT, teacher TEXT,
                  classroom_id TEXT, day_of_week INTEGER, start_time TEXT, end_time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT,
                  start_time TEXT, end_time TEXT, location TEXT, target TEXT,
                  organizer TEXT, description TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tutor_duty
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_name TEXT, teacher_uid TEXT,
                  college TEXT, duty_date TEXT, start_time TEXT, end_time TEXT,
                  location TEXT, contact TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS teacher_office
                 (uid TEXT PRIMARY KEY, name TEXT, college TEXT, title TEXT,
                  office TEXT, phone TEXT)''')
    conn.commit()
    _seed_data(conn)
    conn.close()

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
        c.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)', [
            (1,'秋季运动会','体育赛事','2026-05-10 08:00','2026-05-10 17:00','体育场','全体','体育部','一年一度校运会'),
            (2,'校园十大歌手','文艺活动','2026-05-15 18:30','2026-05-15 21:00','大礼堂','学生','学生会','展示你的歌喉'),
            (3,'人工智能讲座','学术讲座','2026-05-08 14:00','2026-05-08 16:00','报告厅A','全体','计算机学院','特邀教授讲座')
        ])
    if c.execute('SELECT COUNT(*) FROM tutor_duty').fetchone()[0] == 0:
        c.executemany('INSERT INTO tutor_duty VALUES (?,?,?,?,?,?,?,?)', [
            (1,'李明','TE2023001','计算机学院','2026-05-01','08:00','12:00','教学楼A301','123456789'),
            (2,'王芳','TE2023002','计算机学院','2026-05-01','14:00','18:00','教学楼B205','987654321')
        ])
    if c.execute('SELECT COUNT(*) FROM teacher_office').fetchone()[0] == 0:
        c.executemany('INSERT INTO teacher_office VALUES (?,?,?,?,?,?)', [
            ('TE2023001','李明','计算机学院','教授','教学楼A栋301室','123456789'),
            ('TE2023002','王芳','计算机学院','副教授','教学楼B栋205室','987654321'),
            ('TE2023003','张强','数学学院','讲师','教学楼C栋102室','1122334455')
        ])
    conn.commit()

# ---------- 辅助函数 ----------
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

# ---------- 路由 ----------
@app.route('/')
def index():
    return app.send_static_file('login.html')

@app.route('/main')
def main_page():
    return app.send_static_file('main.html')

@app.route('/chat')
def chat_page():
    return app.send_static_file('chat.html')

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
    if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$', password):
        return jsonify({'error':'密码需包含大小写字母和数字，至少8位'}),400
    if password != confirm:
        return jsonify({'error':'两次密码不一致'}),400
    role = 'student' if re.match(r'^202\d{5}$', uid) else 'teacher'
    conn = get_db()
    try:
        if conn.execute('SELECT uid FROM users WHERE uid=?',(uid,)).fetchone():
            return jsonify({'error':'该学工号已注册'}),409
        conn.execute('INSERT INTO users (uid,name,password,role,locked) VALUES (?,?,?,?,0)',
                     (uid, name, hash_password(password), role))
        conn.commit()
        return jsonify({'message':'注册成功'}),201
    except:
        return jsonify({'error':'系统繁忙'}),500
    finally:
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
        return jsonify({'message':'登录成功','token':token,'name':user['name'],'role':user['role']}),200
    except:
        return jsonify({'error':'系统繁忙'}),500
    finally:
        conn.close()

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
    return jsonify({'uid':u['uid'],'name':u['name'],'role':u['role']})

# 个人资料修改（姓名和密码）
@app.route('/api/userinfo', methods=['PUT'])
@token_required
def update_userinfo():
    data = request.get_json()
    new_name = data.get('name','').strip()
    new_password = data.get('password','').strip()
    if not new_name:
        return jsonify({'error':'姓名不能为空'}),400
    conn = get_db()
    try:
        if new_password:
            if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$', new_password):
                return jsonify({'error':'密码需包含大小写字母和数字，至少8位'}),400
            conn.execute('UPDATE users SET name=?, password=? WHERE uid=?',
                         (new_name, hash_password(new_password), g.current_user['uid']))
        else:
            conn.execute('UPDATE users SET name=? WHERE uid=?', (new_name, g.current_user['uid']))
        conn.commit()
        return jsonify({'message':'修改成功','name':new_name})
    except:
        return jsonify({'error':'系统繁忙'}),500
    finally:
        conn.close()

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
        if file and msg_type in ('image','video','audio','file'):
            filename = secure_filename(f"{int(time.time())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            file_path = f'/uploads/{filename}'
            file_name = file.filename
            file_size = os.path.getsize(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        ts = time.time()
        conn = get_db()
        conn.execute('INSERT INTO messages (sender,receiver,content,msg_type,file_path,file_name,file_size,status,timestamp) VALUES (?,?,?,?,?,?,?,?,?)',
                     (sender, receiver, content, msg_type, file_path, file_name, file_size, 'sent', ts))
        conn.commit(); conn.close()
        return jsonify({'message':'发送成功','timestamp':ts}),201
    else:
        data = request.get_json()
        receiver = data.get('receiver','').strip()
        msg_type = data.get('msg_type','text')
        content = data.get('content','').strip()
        if not receiver:
            return jsonify({'error':'接收者不能为空'}),400
        ts = time.time()
        conn = get_db()
        conn.execute('INSERT INTO messages (sender,receiver,content,msg_type,status,timestamp) VALUES (?,?,?,?,?,?)',
                     (sender, receiver, content, msg_type, 'sent', ts))
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
    conn.execute('UPDATE messages SET revoked=1 WHERE id=?', (msg_id,))
    conn.commit(); conn.close()
    return jsonify({'message':'已撤回'})

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
    return jsonify([{'group_id':g['group_id'],'name':g['name'],'creator':g['creator'],
                     'created_at':g['created_at'],'group_type':g['group_type'],
                     'category':g['category']} for g in groups])

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
            conn.execute('INSERT INTO group_members VALUES (?,?,?,?)', (group_id, m, role, now))
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
    msgs = conn.execute('SELECT * FROM group_messages WHERE group_id=? ORDER BY timestamp',(group_id,)).fetchall()
    conn.close()
    return jsonify([{'id':m['id'],'sender':m['sender'],'content':m['content'],
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
        ts = time.time()
        conn.execute('INSERT INTO group_messages (group_id,sender,content,msg_type,status,timestamp) VALUES (?,?,?,?,?,?)',
                     (group_id, sender, content, msg_type, 'sent', ts))
        conn.commit(); conn.close()
        return jsonify({'message':'发送成功'}),201

@app.route('/api/groups/<group_id>/leave', methods=['POST'])
@token_required
def leave_group(group_id):
    uid = g.current_user['uid']
    conn = get_db()
    member = conn.execute('SELECT role FROM group_members WHERE group_id=? AND uid=?',(group_id,uid)).fetchone()
    if not member: return jsonify({'error':'你不在群中'}),403
    if member['role'] == 'admin':
        count = conn.execute('SELECT COUNT(*) FROM group_members WHERE group_id=?',(group_id,)).fetchone()[0]
        if count > 1:
            return jsonify({'error':'群主不能退出，请转让群主'}),403
    conn.execute('DELETE FROM group_members WHERE group_id=? AND uid=?',(group_id,uid))
    conn.commit(); conn.close()
    return jsonify({'message':'已退出'})

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
    q = request.args.get('q','').strip()
    if not q: return jsonify([])
    conn = get_db()
    users = conn.execute("SELECT uid,name,role FROM users WHERE uid LIKE ? OR name LIKE ? LIMIT 50",
                         (f'%{q}%', f'%{q}%')).fetchall()
    conn.close()
    return jsonify([{'uid':u['uid'],'name':u['name'],'role':u['role']} for u in users])

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
    return jsonify([{'name':e['name'],'type':e['type'],'start_time':e['start_time'],
                     'end_time':e['end_time'],'location':e['location'],'target':e['target'],
                     'organizer':e['organizer'],'description':e['description']} for e in events])

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

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)