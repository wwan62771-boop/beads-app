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

# 后台管理页面 HTML（输入框全选 + 多重兼容复制）
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
        .link-input { width: 100%; min-width: 240px; padding: 8px; border: 1px solid #007bff; border-radius: 6px; background: #f4f8ff; font-size: 13px; color: #0056b3; font-weight: 500; }
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
                    <th>完整提取链接（点框内全选/复制）</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                {% for item in patterns %}
                <tr>
                    <td><strong>{{ item.title }}</strong></td>
                    <td>{{ item.filenames.split(',')|length }} 张</td>
                    <td>
                        <input type="text" class="link-input" id="input-{{ item.id }}" readonly value="https://wanwan-dwt0.onrender.com/d/{{ item.id }}" onclick="this.select(); focus();">
                    </td>
                    <td class="action-td">
                        <button class="btn-copy" id="btn-{{ item.id }}" onclick="copyUrl('{{ item.id }}')">📋 复制</button>
                        <a class="btn-delete" href="/delete/{{ item.id }}" onclick="return confirm('确定要删除该图纸吗？')">删除</a>
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="4" style="text-align: center; color: #999;">暂无图纸数据</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <script>
    function copyUrl(id) {
        const inputElem = document.getElementById('input-' + id);
        const btnElem = document.getElementById('btn-' + id);
        
        inputElem.select();
        inputElem.setSelectionRange(0, 99999);
        
        let copied = false;
        try {
            copied = document.execCommand('copy');
        } catch (e) {
            copied = false;
        }

        if (copied) {
            btnElem.innerText = '✅ 已复制';
            setTimeout(() => { btnElem.innerText = '📋 复制'; }, 2000);
        } else {
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(inputElem.value).then(() => {
                    btnElem.innerText = '✅ 已复制';
                    setTimeout(() => { btnElem.innerText = '📋 复制'; }, 2000);
                }).catch(() => {
                    prompt('请按 Ctrl+C / 长按复制链接：', inputElem.value);
                });
            } else {
                prompt('请按 Ctrl+C / 长按复制链接：', inputElem.value);
            }
        }
    }
    </script>
</body>
</html>
"""

# 客户下载提取页面 HTML
DOWNLOAD_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>拼豆图纸下载 - {{ pattern.title }}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8f9fa; margin: 0; padding: 20px; text-align: center; }
        .container { max-width: 600px; margin: 0 auto; background: #fff; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { font-size: 22px; color: #333; margin-bottom: 10px; }
        p { color: #666; font-size: 14px; margin-bottom: 20px; }
        .img-card { margin-bottom: 20px; border: 1px solid #eee; border-radius: 8px; padding: 10px; background: #fafafa; }
        .img-card img { max-width: 100%; height: auto; border-radius: 6px; }
        .download-btn { display: inline-block; margin-top: 8px; padding: 8px 16px; background: #28a745; color: white; text-decoration: none; border-radius: 6px; font-size: 14px; }
        .download-btn:hover { background: #218838; }
    </style>
</head>
<body>
    <div class="container">
        <h1>✨ {{ pattern.title }} ✨</h1>
        <p>长按上方图片可保存，或点击下方按钮直接下载高清晰度原图：</p>
        
        {% for img in filenames %}
        <div class="img-card">
            <img src="/uploads/{{ img }}" alt="图纸">
            <div>
                <a class="download-btn" href="/uploads/{{ img }}" download>📥 点击下载此张图纸</a>
            </div>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/')
def admin():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM patterns ORDER BY created_at DESC;")
    patterns = cur.fetchall()
    cur.close()
    conn.close()
    return render_template_string(ADMIN_HTML, patterns=patterns)

@app.route('/upload', methods=['POST'])
def upload():
    title = request.form.get('title')
    files = request.files.getlist('files')
    
    if not files or not title:
        flash('请填写名称并选择图片！')
        return redirect(url_for('admin'))
        
    saved_filenames = []
    for file in files:
        if file.filename != '':
            ext = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4().hex[:8]}{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            saved_filenames.append(unique_filename)
            
    if saved_filenames:
        pattern_id = uuid.uuid4().hex[:8]
        filenames_str = ",".join(saved_filenames)
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO patterns (id, title, filenames) VALUES (%s, %s, %s);",
            (pattern_id, title, filenames_str)
        )
        conn.commit()
        cur.close()
        conn.close()
        
        flash('上传成功！数据已持久化保存至数据库。')
    return redirect(url_for('admin'))

@app.route('/d/<pattern_id>')
def download_page(pattern_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM patterns WHERE id = %s;", (pattern_id,))
    pattern = cur.fetchone()
    cur.close()
    conn.close()
    
    if not pattern:
        return "该图纸链接不存在或已被删除", 404
        
    filenames = pattern['filenames'].split(',')
    return render_template_string(DOWNLOAD_HTML, pattern=pattern, filenames=filenames)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/delete/<pattern_id>')
def delete_pattern(pattern_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT filenames FROM patterns WHERE id = %s;", (pattern_id,))
    pattern = cur.fetchone()
    
    if pattern:
        filenames = pattern['filenames'].split(',')
        for fn in filenames:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
            if os.path.exists(file_path):
                os.remove(file_path)
                
        cur.execute("DELETE FROM patterns WHERE id = %s;", (pattern_id,))
        conn.commit()
        flash('删除成功！')
        
    cur.close()
    conn.close()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
