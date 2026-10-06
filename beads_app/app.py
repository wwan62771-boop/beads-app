import os
import io
import uuid
import zipfile
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, redirect, url_for, render_template_string, send_from_directory, flash, jsonify, send_file

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "beads_secret_key_12345")

# 目录配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 数据库连接函数
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        return None
    url = DATABASE_URL.replace("postgres://", "postgresql://")
    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    return conn

# 初始化数据库表
def init_db():
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    filenames TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        conn.close()

try:
    init_db()
except Exception as e:
    print(f"Database initialization failed: {e}")

# 后台管理页面 HTML
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>图纸上传与管理后台</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        h1 { font-size: 24px; color: #333; margin-bottom: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; font-weight: bold; margin-bottom: 5px; color: #555; }
        input[type="text"], input[type="file"] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
        .btn { background: #007bff; color: white; border: none; padding: 12px 20px; border-radius: 6px; cursor: pointer; font-size: 16px; width: 100%; }
        .btn:hover { background: #0056b3; }
        table { width: 100%; border-collapse: collapse; margin-top: 25px; }
        th, td { padding: 12px; border-bottom: 1px solid #eee; text-align: left; }
        th { background: #f8f9fa; color: #666; }
        .link { color: #007bff; text-decoration: none; word-break: break-all; }
        .flash { padding: 10px; background: #e7f5ff; color: #1971c2; border-radius: 6px; margin-bottom: 15px; }
        .btn-delete { background: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; text-decoration: none; font-size: 13px; }
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
                    <th>下载链接</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                {% for item in patterns %}
                <tr>
                    <td><strong>{{ item.title }}</strong></td>
                    <td>{{ item.filenames.split(',')|length }} 张</td>
                    <td><a class="link" href="/d/{{ item.id }}" target="_blank">/d/{{ item.id }}</a></td>
                    <td><a class="btn-delete" href="/delete/{{ item.id }}" onclick="return confirm('确定要删除该图纸吗？')">删除</a></td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="4" style="text-align: center; color: #999;">暂无图纸数据</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

# 客人下载前端 HTML
CLIENT_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ pattern.title }} - 图纸下载</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #fafafa; margin: 0; padding: 20px; text-align: center; }
        .container { max-width: 600px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        h1 { font-size: 20px; color: #333; margin-bottom: 15px; }
        .btn-zip { display: inline-block; background: #28a745; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-bottom: 20px; }
        .img-card { margin-bottom: 20px; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
        img { width: 100%; display: block; }
        .tips { font-size: 14px; color: #888; margin-top: 10px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>✨ {{ pattern.title }} ✨</h1>
        <a class="btn-zip" href="/download_zip/{{ pattern.id }}">📦 一键打包下载全部图纸 (.zip)</a>
        <p class="tips">提示：手机端可直接长按下方图片保存到相册哦～</p>
        {% for img in images %}
            <div class="img-card">
                <img src="/uploads/{{ img }}" alt="图纸图片">
            </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/')
@app.route('/admin')
def admin():
    conn = get_db_connection()
    patterns = []
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM patterns ORDER BY created_at DESC;")
            patterns = cur.fetchall()
        conn.close()
    return render_template_string(ADMIN_HTML, patterns=patterns)

@app.route('/upload', methods=['POST'])
def upload():
    title = request.form.get('title')
    files = request.files.getlist('files')
    
    if not title or not files:
        flash("请填写完整标题并选择文件！")
        return redirect('/admin')

    saved_filenames = []
    group_id = str(uuid.uuid4())[:8]

    for file in files:
        if file.filename:
            ext = os.path.splitext(file.filename)[1]
            filename = f"{group_id}_{uuid.uuid4().hex[:6]}{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            saved_filenames.append(filename)

    if saved_filenames:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO patterns (id, title, filenames) VALUES (%s, %s, %s);",
                    (group_id, title, ",".join(saved_filenames))
                )
                conn.commit()
            conn.close()
        flash("上传成功！数据已持久化保存至数据库。")

    return redirect('/admin')

@app.route('/d/<group_id>')
def client_view(group_id):
    conn = get_db_connection()
    pattern = None
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM patterns WHERE id = %s;", (group_id,))
            pattern = cur.fetchone()
        conn.close()

    if not pattern:
        return "图纸不存在或已被删除", 404

    images = pattern['filenames'].split(',')
    return render_template_string(CLIENT_HTML, pattern=pattern, images=images)

@app.route('/delete/<group_id>')
def delete_pattern(group_id):
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM patterns WHERE id = %s;", (group_id,))
            pattern = cur.fetchone()
            if pattern:
                filenames = pattern['filenames'].split(',')
                for fn in filenames:
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                cur.execute("DELETE FROM patterns WHERE id = %s;", (group_id,))
                conn.commit()
        conn.close()
        flash("图纸删除成功！")
    return redirect('/admin')

@app.route('/uploads/<filename>')
def get_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/download_zip/<group_id>')
def download_zip(group_id):
    conn = get_db_connection()
    pattern = None
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM patterns WHERE id = %s;", (group_id,))
            pattern = cur.fetchone()
        conn.close()

    if not pattern:
        return "图纸不存在", 404

    filenames = pattern['filenames'].split(',')
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for idx, filename in enumerate(filenames, 1):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                ext = os.path.splitext(filename)[1]
                zf.write(file_path, f"{pattern['title']}_图纸_{idx}{ext}")
    memory_file.seek(0)
    return send_file(memory_file, download_name=f"{pattern['title']}_全部图纸.zip", as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
