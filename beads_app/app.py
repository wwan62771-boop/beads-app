import os
import uuid
import psycopg2
import psycopg2.extras
from psycopg2.extras import RealDictCursor
from flask import Flask, request, render_template_string, redirect, url_for, send_from_directory, flash

app = Flask(__name__)
app.secret_key = 'beads_secret_key'

# 文件上传配置
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 获取数据库连接
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL 环境变量未设置！")
    conn = psycopg2.connect(db_url)
    return conn

# 初始化数据库表结构
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS patterns (
            id VARCHAR(10) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            filenames TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

# 初始化数据库
try:
    init_db()
except Exception as e:
    print(f"数据库初始化提示: {e}")

# 后台管理页面 HTML（一键复制 + 输入框选中）
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>图纸上传与管理后台</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; }
        .container { max-width: 950px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        h1 { font-size: 24px; color: #333; margin-bottom: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; font-weight: bold; margin-bottom: 5px; color: #555; }
        input[type="text"], input[type="file"] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
        .btn { background: #007bff; color: white; border: none; padding: 12px 20px; border-radius: 6px; cursor: pointer; font-size: 16px; width: 100%; }
        .btn:hover { background: #0056b3; }
        table { width: 100%; border-collapse: collapse; margin-top: 25px; }
        th, td { padding: 12px; border-bottom: 1px solid #eee; text-align: left; }
        th { background: #f8f9fa; color: #666; }
        .link-input { width: 100%; min-width: 220px; padding: 6px; border: 1px solid #ddd; border-radius: 4px; background: #fdfdfd; font-size: 13px; color: #333; }
        .flash { padding: 10px; background: #e7f5ff; color: #1971c2; border-radius: 6px; margin-bottom: 15px; }
        .btn-delete { background: #dc3545; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; text-decoration: none; font-size: 13px; }
        .btn-copy { background: #28a745; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; margin-right: 5px; white-space: nowrap; }
        .btn-copy:hover { background: #218838; }
        .action-td { white-space: nowrap; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛠️ 图纸上传与管理后台</h1>
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="flash">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <form method="POST" action="/upload" enctype="multipart/form-data">
            <div class="form-group">
                <label>图纸名称/备注：</label>
                <input type="text" name="title" placeholder="例如：宝可梦皮卡丘" required>
            </div>
            <div class="form-group">
                <label>选择图片（可多选）：</label>
                <input type="file" name="files" multiple required>
            </div>
            <button type="submit" class="btn">🚀 立即上传并生成下载链接</button>
        </form>

        <h2>📂 已上传图纸列表</h2>
        <table>
            <thead>
                <tr>
                    <th>名称</th>
                    <th>图片数量</th>
                    <th>完整提取链接（可复制/长按全选）</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                {% for item in patterns %}
                <tr>
                    <td><strong>{{ item.title }}</strong></td>
                    <td>{{ item.filenames.split(',')|length }} 张</td>
                    <td>
                        <input type="text" class="link-input" id="input-{{ item.id }}" readonly value="https://wanwan-dwt0.onrender.com/d/{{ item.id }}" onclick="this.select();">
                    </td>
                    <td class="action-td">
                        <button class="btn-copy" id="btn-{{ item.id }}" onclick="copyUrl('{{ item.id }}')">📋 复制链接</button>
                        <a class="btn-delete" href="/delete/{{ item.id }}" onclick="return confirm('确定要删除该图纸吗？')">删除</a>
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="4" style="
