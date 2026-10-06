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

# 后台管理页面 HTML（完美适配电脑与手机移动端）
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>图纸上传与管理后台</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f4f6f8; margin: 0; padding: 12px; color: #333; }
        .container { max-width: 900px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); }
        h1 { font-size: 20px; color: #222; margin-top: 0; margin-bottom: 16px; text-align: center; }
        h2 { font-size: 16px; color: #444; margin-top: 24px; margin-bottom: 12px; border-bottom: 2px solid #007bff; padding-bottom: 6px; }
        .form-group { margin-bottom: 14px; }
        label { display: block; font-weight: 600; margin-bottom: 6px; color: #555; font-size: 14px; }
        input[type="text"], input[type="file"] { width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 8px; font-size: 15px; background: #fff; }
        .btn-submit { background: #007bff; color: white; border: none; padding: 14px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%; }
        .btn-submit:active { background: #0056b3; }
        .flash { padding: 10px 14px; background: #e7f5ff; color: #1971c2; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
        
        /* 桌面端表格样式 */
        .table-wrapper { width: 100%; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 12px 10px; border-bottom: 1px solid #eee; text-align: left; font-size: 14px; }
        th { background: #f8f9fa; color: #666; font-weight: 600; }
        
        /* 链接输入框 */
        .link-input { width: 100%; padding: 10px; border: 1px solid #007bff; border-radius: 6px; background: #f4f8ff; font-size: 13px; color: #0056b3; -webkit-appearance: none; }
        
        /* 按钮组 */
        .btn-copy { background: #28a745; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: bold; }
        .btn-delete { background: #dc3545; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; text-decoration: none; font-size: 13px; display: inline-block; }

        /* 📱 手机端适配样式 (屏幕宽度小于 650px 时触发) */
        @media (max-width: 650px) {
            body { padding: 8px; }
            .container { padding: 15px; border-radius: 10px; }
            h1 { font-size: 18px; }
            
            /* 隐藏传统表格头 */
            table, thead, tbody, th, td, tr { display: block; }
            thead { display: none; }
            
            /* 转换每一行为手机卡片 */
            tr { background: #fafafa; border: 1px solid #e2e8f0; border-radius: 10px; margin-bottom: 12px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
            td { padding: 6px 0; border: none; }
            td:nth-child(1) { font-size: 16px; color: #111; padding-bottom: 4px; }
            td:nth-child(2) { font-size: 13px; color: #666; margin-bottom: 8px; }
            
            .card-actions { display: flex; gap: 8px; margin-top: 10px; }
            .btn-copy, .btn-delete { flex: 1; text-align: center; padding: 10px; font-size: 14px; }
        }
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
                <label>图纸名称 / 备注：</label>
                <input type="text" name="title" placeholder="例如：复古狗狗四宫格" required>
            </div>
            <div class="form-group">
                <label>选择图纸图片（可多选）：</label>
                <input type="file" name="files" multiple required>
            </div>
            <button type="submit" class="btn-submit">🚀 上传并生成生成提取链接</button>
        </form>

        <h2>📂 已上传图纸列表</h2>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>名称</th>
                        <th>图片数</th>
                        <th>客户提取链接</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in patterns %}
                    <tr>
                        <td><strong>{{ item.title }}</strong></td>
                        <td>包含 {{ item.filenames.split(',')|length }} 张图纸</td>
                        <td>
                            <input type="text" class="link-input" id="input-{{ item.id }}" readonly value="https://wanwan-dwt0.onrender.com/d/{{ item.id }}" onclick="this.select();">
                        </td>
                        <td>
                            <div class="card-actions">
                                <button class="btn-copy" id="btn-{{ item.id }}" onclick="copyUrl('{{ item.id }}')">📋 复制链接</button>
                                <a class="btn-delete" href="/delete/{{ item.id }}" onclick="return confirm('确定要删除该图纸吗？')">删除</a>
                            </div>
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="4" style="text-align: center; color: #999; padding: 20px;">暂无图纸数据</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <script>
    function copyUrl(id) {
        const inputElem = document.getElementById('input-' + id);
        const btnElem = document.getElementById('btn-' + id);
        
        inputElem.select();
        inputElem.setSelectionRange(0, 99999); // 兼容 iOS Safari
        
        let copied = false;
        try {
            copied = document.execCommand('copy');
        } catch (e) {
            copied = false;
        }

        if (copied) {
            btnElem.innerText = '✅ 已复制';
            setTimeout(() => { btnElem.innerText = '📋 复制链接'; }, 2000);
        } else {
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(inputElem.value).then(() => {
                    btnElem.innerText = '✅ 已复制';
                    setTimeout(() => { btnElem.innerText = '📋 复制链接'; }, 2000);
                }).catch(() => {
                    prompt('手机请长按框内链接复制：', inputElem.value);
                });
            } else {
                prompt('手机请长按框内链接复制：', inputElem.value);
            }
        }
    }
    </script>
</body>
</html>
"""

# 客户提取页面 HTML（手机专属大图流展示）
DOWNLOAD_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{{ pattern.title }} - 图纸提取下载</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8f9fa; margin: 0; padding: 12px; text-align: center; color: #333; }
        .container { max-width: 600px; margin: 0 auto; background: #fff; padding: 18px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); }
        h1 { font-size: 20px; color: #222; margin-top: 5px; margin-bottom: 8px; word-break: break-all; }
        .tip-banner { background: #fff3cd; color: #856404; padding: 10px; border-radius: 8px; font-size: 13px; margin-bottom: 18px; text-align: left; line-height: 1.5; }
        .img-card { margin-bottom: 20px; border: 1px solid #edf2f7; border-radius: 10px; padding: 10px; background: #ffffff; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
        .img-card img { width: 100%; height: auto; border-radius: 6px; display: block; margin-bottom: 10px; }
        .download-btn { display: block; width: 100%; padding: 12px; background: #28a745; color: white; text-decoration: none; border-radius: 8px; font-size: 15px; font-weight: bold; text-align: center; }
        .download-btn:active { background: #218838; }
    </style>
</head>
<body>
    <div class="container">
        <h1>✨ {{ pattern.title }} ✨</h1>
        <div class="tip-banner">
            💡 <strong>保存提示：</strong><br>
            • <strong>手机端：</strong>可直接长按下方图纸图片，选择“保存到相册”。<br>
            • <strong>电脑端/原图：</strong>可点击图片下方的绿色按钮直接下载。
        </div>
        
        {% for img in filenames %}
        <div class="img-card">
            <img src="/uploads/{{ img }}" alt="图纸图片">
            <a class="download-btn" href="/uploads/{{ img }}" download>📥 点击下载高清原图</a>
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
        
        flash('上传成功！图纸及链接已永久保存。')
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
