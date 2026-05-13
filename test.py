import json
import sqlite3, hashlib, secrets, re, time, os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g, send_from_directory
from functools import wraps
from werkzeug.utils import secure_filename
import json
import os
verification_codes = {}
verification_codes['13800138000']={
            'code': "123456",
            'expires_at': time.time() + 300,  # 5分钟后过期
            'attempts': 0,  # 验证尝试次数
        }
def handle_reset_password(data):
    """处理重置密码请求"""
    phone = data.get('phone')
    code = data.get('code')
    new_password = data.get('new_password')
    
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
        
        user.execute(
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

handle_reset_password(
{
  "phone": "13800138000",
  "code": "123456",  
  "new_password": "NewPass123"
})