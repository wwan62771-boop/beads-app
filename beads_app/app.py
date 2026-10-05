import os
import io
import zipfile
import uuid
import secrets
from flask import Flask, request, render_template_string, redirect, url_for, send_from_directory, send_file, session

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# 配置项
ADMIN_PASSWORD = "123456"  # 后台登录密码（部署后请修改为你自己的密码）
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 模拟简单数据库保存图纸组信息：{ group_id: { "title": "...", "files": ["filename1.png", ...] } }
# 在实际运行中也可以写入本地 JSON 文件
import json
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# HTML 模板：客人下载页面
CLIENT_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>拼豆图纸下载 - {{ group.title }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f9; color: #333; line-height: 1.6; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; background: #fff; padding: 25px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }
        .header { text-align: center; border-bottom: 2px dashed #eee; padding-bottom: 15px; margin-bottom: 20px; }
        .header h1 { font-size: 20px; color: #ff6b81; }
        .header p { font-size: 13px; color: #888; margin-top: 5px; }
        .gallery { display: flex; flex-direction: column; gap: 20px; }
        .card { border: 1px solid #f0f0f0; border-radius: 12px; overflow: hidden; background: #fafafa; }
        .card img { width: 100%; display: block; max-height: 400px; object-fit: contain; background: #eee; }
        .card-body { padding: 12px; text-align: center; }
        .btn { display: inline-block; width: 100%; padding: 12px; background: #ff6b81; color: #fff; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 14px; text-align: center; border: none; cursor: pointer; }
        .btn:hover { background: #ff4757; }
        .btn-zip { background: #2ed573; margin-bottom: 20px; }
        .btn-zip:hover { background: #26af5f; }
        .footer { text-align: center; margin-top: 25px; font-size: 12px; color: #aaa; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎨 拼豆图纸专区</h1>
            <p>图纸名称：<strong>{{ group.title }}</strong></p>
        </div>

        {% if group.files|length > 1 %}
        <a href="{{ url_for('download_zip', group_id=group_id) }}" class="btn btn-zip">📦 打包下载全部图片 (.zip)</a>
        {% endif %}

        <div class="gallery">
            {% for img in group.files %}
            <div class="card">
                <img src="{{ url_for('get_file', filename=img) }}" alt="图纸">
                <div class="card-body">
                    <a href="{{ url_for('get_file', filename=img) }}" download class="btn">⬇️ 保存原图 (单张)</a>
                </div>
            </div>
            {% endfor %}
        </div>

        <div class="footer">
            <p>长按图片或点击下方按钮保存高清图纸</p>
            <p>© 拼豆手作工坊</p>
        </div>
    </div>
</body>
</html>
"""

# HTML 模板：后台管理界面
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>图纸后台管理系统</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #eef2f7; color: #333; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        h1 { font-size: 22px; margin-bottom: 20px; color: #2c3e50; }
        .upload-card { background: #f8f9fa; border: 2px dashed #cbd5e1; padding: 25px; border-radius: 10px; text-align: center; margin-bottom: 30px; }
        .form-group { margin-bottom: 15px; text-align: left; }
        label { display: block; margin-bottom: 6px; font-weight: bold; font-size: 14px; }
        input[type="text"], input[type="file"], input[type="password"] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; }
        .btn { padding: 10px 20px; background: #3b82f6; color: #fff; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; }
        .btn:hover { background: #2563eb; }
        .btn-danger { background: #ef4444; padding: 6px 12px; font-size: 12px; }
        .btn-danger:hover { background: #dc2626; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { border-bottom: 1px solid #e2e8f0; padding: 12px; text-align: left; font-size: 14px; }
        th { background: #f1f5f9; }
        .link-text { color: #2563eb; font-size: 13px; word-break: break-all; }
        .copy-btn { padding: 4px 8px; font-size: 12px; background: #10b981; color: white; border: none; border-radius: 4px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="container">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h1>🛠️ 图纸上传与管理后台</h1>
            <a href="{{ url_for('logout') }}" style="color: #ef4444; text-decoration: none; font-size: 14px;">退出登录</a>
        </div>

        <div class="upload-card">
            <form action="{{ url_for('upload') }}" method="post" enctype="multipart/form-data">
                <div class="form-group">
                    <label>图纸名称/备注（例如：宝可梦皮卡丘）：</label>
                    <input type="text" name="title" placeholder="请输入图纸名称" required>
                </div>
                <div class="form-group">
                    <label>选择图片（可按住 Ctrl/Cmd 一次选多张）：</label>
                    <input type="file" name="files" multiple accept="image/*" required>
                </div>
                <button type="submit" class="btn">🚀 立即上传并生成下载链接</button>
            </form>
        </div>

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
                {% for gid, item in data.items() %}
                <tr>
                    <td><strong>{{ item.title }}</strong></td>
                    <td>{{ item.files|length }} 张</td>
                    <td>
                        <span class="link-text" id="link-{{ gid }}">{{ request.host_url }}d/{{ gid }}</span>
                        <button class="copy-btn" onclick="copyLink('link-{{ gid }}')">复制</button>
                    </td>
                    <td>
                        <a href="{{ url_for('delete', group_id=gid) }}" class="btn btn-danger" onclick="return confirm('确定删除这份图纸吗？')">删除</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <script>
        function copyLink(elementId) {
            var text = document.getElementById(elementId).innerText;
            navigator.clipboard.writeText(text).then(function() {
                alert("下载链接已成功复制到剪贴板！");
            });
        }
    </script>
</body>
</html>
"""

# HTML 模板：登录页面
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>后台登录</title>
    <style>
        body { font-family: sans-serif; background: #f3f4f6; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .box { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); width: 300px; text-align: center; }
        input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #3b82f6; color: white; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; }
    </style>
</head>
<body>
    <div class="box">
        <h2>管理员登录</h2>
        <form method="post">
            <input type="password" name="password" placeholder="请输入后台密码" required>
            <button type="submit">登录</button>
        </form>
    </div>
</body>
</html>
"""

# 路由设置
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin'))
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('login'))

@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))
    data = load_data()
    return render_template_string(ADMIN_TEMPLATE, data=data)

@app.route('/upload', methods=['POST'])
def upload():
    if not session.get('admin'):
        return redirect(url_for('login'))
    
    title = request.form.get('title', '未命名图纸')
    files = request.files.getlist('files')
    
    saved_filenames = []
    for file in files:
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4().hex}{ext}"
            file.save(os.path.join(UPLOAD_FOLDER, unique_filename))
            saved_filenames.append(unique_filename)
            
    if saved_filenames:
        group_id = uuid.uuid4().hex[:8]  # 生成短ID
        data = load_data()
        data[group_id] = {
            "title": title,
            "files": saved_filenames
        }
        save_data(data)
        
    return redirect(url_for('admin'))

@app.route('/delete/<group_id>')
def delete(group_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    data = load_data()
    if group_id in data:
        # 删除文件
        for filename in data[group_id]['files']:
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        del data[group_id]
        save_data(data)
    return redirect(url_for('admin'))

# 客人访问链接
@app.route('/d/<group_id>')
def client_view(group_id):
    data = load_data()
    group = data.get(group_id)
    if not group:
        return "图纸不存在或已被删除", 404
    return render_template_string(CLIENT_TEMPLATE, group=group, group_id=group_id)

@app.route('/uploads/<filename>')
def get_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/download_zip/<group_id>')
def download_zip(group_id):
    data = load_data()
    group = data.get(group_id)
    if not group:
        return "图纸不存在", 404
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for idx, filename in enumerate(group['files'], 1):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.exists(file_path):
                ext = os.path.splitext(filename)[1]
                zf.write(file_path, f"{group['title']}_图纸_{idx}{ext}")
    memory_file.seek(0)
    return send_file(memory_file, download_name=f"{group['title']}_全部图纸.zip", as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)