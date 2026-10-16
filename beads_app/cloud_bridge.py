"""Additive Render delivery bridge; register on the existing Flask app."""
import hashlib, hmac, io, os, secrets, zipfile, json
from flask import request, jsonify, Response, render_template_string, send_file, make_response
from PIL import Image

PAGE='\n<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">\n    <title>{{ title }} - 图纸提取下载</title>\n    <style>\n        * { box-sizing: border-box; }\n        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8f9fa; margin: 0; padding: 12px; text-align: center; color: #333; }\n        .container { max-width: 600px; margin: 0 auto; background: #fff; padding: 18px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); }\n        h1 { font-size: 20px; color: #222; margin-top: 5px; margin-bottom: 8px; word-break: break-all; }\n        .tip-banner { background: #fff3cd; color: #856404; padding: 10px; border-radius: 8px; font-size: 13px; margin-bottom: 18px; text-align: left; line-height: 1.5; }\n        .img-card { margin-bottom: 20px; border: 1px solid #edf2f7; border-radius: 10px; padding: 10px; background: #ffffff; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }\n        .img-card img { width: 100%; height: auto; border-radius: 6px; display: block; margin-bottom: 10px; }\n        .download-btn { display: block; width: 100%; padding: 12px; background: #28a745; color: white; text-decoration: none; border-radius: 8px; font-size: 15px; font-weight: bold; text-align: center; }\n        .download-btn:active { background: #218838; }\n    </style>\n</head>\n<body>\n    <div class="container">\n        <h1>✨ {{ title }} ✨</h1>\n        <div class="tip-banner">\n            💡 <strong>保存提示：</strong><br>\n            • <strong>手机端：</strong>可直接长按下方图纸图片，选择“保存到相册”。<br>\n            • <strong>电脑端/原图：</strong>可点击图片下方的绿色按钮直接下载。\n        </div>\n        \n        {% for file in files %}\n        <div class="img-card">\n            <img src="{{ base }}/{{ file[0] }}" alt="{{ file[1] }}" loading="lazy">\n            <a class="download-btn" href="{{ base }}/{{ file[0] }}?download=1" download="{{ file[1] }}">📥 点击下载高清原图</a>\n        </div>\n        {% endfor %}\n    </div>\n</body>\n</html>\n'


ADMIN_COLLECTIONS = r'''<section class="library-cloud-panel">
<style>
.library-cloud-panel{max-width:900px;margin:0 auto 18px;background:white;padding:20px;border-radius:12px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#333;text-align:left}.library-cloud-panel h2{font-size:20px;margin:0 0 12px}.library-cloud-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.library-cloud-card{border:1px solid #e3e8e5;border-radius:12px;padding:14px;min-width:0}.library-cloud-card img{height:150px;width:100%;object-fit:contain;background:#f8f9f7;border-radius:6px}.library-cloud-card h3{font-size:16px;overflow-wrap:anywhere}.library-cloud-actions{display:flex;gap:8px;flex-wrap:wrap}.library-cloud-actions a,.library-cloud-actions button{font:inherit;font-size:13px;text-decoration:none;padding:9px;border:1px solid #d6e2dc;border-radius:7px;color:#315f4b;background:#f5faf6;cursor:pointer}.library-cloud-panel>p,.library-cloud-card p{font-size:13px;color:#68766e}.library-cloud-feedback{font-size:13px;color:#315f4b}.library-cloud-copy{box-sizing:border-box;width:100%;min-height:110px;margin-top:10px}.library-cloud-panel [hidden]{display:none}
</style>
<h2>管理中心发布的合集</h2><p>这里显示已经发布到云端的图纸。以前直接在此后台上传的图纸保留在下方。</p>
{% if error %}<p>合集列表暂时读取失败，请稍后刷新。</p>{% elif not collections %}<p>还没有从管理中心发布的合集。</p>{% else %}<div class="library-cloud-grid">
{% for item in collections %}<article class="library-cloud-card">
{% if item[3] %}<img src="/c/{{ item[0] }}/{{ item[3] }}" alt="{{ item[1] }}" loading="lazy">{% endif %}
<h3>{{ item[1] }}</h3><p>{{ item[2] }}份高清图纸</p><div class="library-cloud-actions"><a href="/c/{{ item[0] }}" target="_blank" rel="noopener">打开合集</a><button type="button" data-cloud-copy="link" data-path="/c/{{ item[0] }}">复制链接</button><button type="button" data-cloud-copy="message" data-path="/c/{{ item[0] }}">复制提取文案</button></div><p class="library-cloud-feedback" role="status"></p><textarea class="library-cloud-copy" readonly hidden aria-label="待复制内容"></textarea></article>{% endfor %}</div>{% endif %}
<script>
for(const button of document.querySelectorAll('[data-cloud-copy]'))button.addEventListener('click',async()=>{
 const url=location.origin+button.dataset.path,card=button.closest('.library-cloud-card'),feedback=card.querySelector('.library-cloud-feedback'),field=card.querySelector('textarea');
 const value=button.dataset.cloudCopy==='link'?url:`亲，图纸提取链接如下：\n${url}\n💗 温馨提示：\n请复制上方链接，粘贴到手机浏览器打开，即可下载高清拼豆图纸哦！\n⏳ 首次打开可能需要等待约10秒，后台启动后即可正常访问，请耐心等待一下哦～`;
 try{await navigator.clipboard.writeText(value);feedback.textContent='已复制';field.hidden=true;}catch{field.hidden=false;field.value=value;field.focus();field.select();feedback.textContent='请长按下方已选中的内容复制。';}
});
</script></section>'''

def register(app, connect):
    # Keep the original uploads/list/actions and add published collections above it.
    original_admin=app.view_functions.get('admin')
    if original_admin:
        def combined_admin():
            response=make_response(original_admin())
            if response.status_code!=200:return response
            conn=connect();collections=[];error=False
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT c.id,c.title,COUNT(f.id),(SELECT MIN(i.id) FROM library_collection_files i WHERE i.collection_id=c.id) FROM library_collections c LEFT JOIN library_collection_files f ON f.collection_id=c.id GROUP BY c.id,c.title ORDER BY c.title,c.id")
                    collections=cur.fetchall()
            except Exception:
                app.logger.warning('Cloud collection list unavailable')
                error=True
            finally:conn.close()
            panel=render_template_string(ADMIN_COLLECTIONS,collections=collections,error=error)
            html=response.get_data(as_text=True)
            response.set_data(html.replace('<body>','<body>'+panel,1) if '<body>' in html else panel+html)
            return response
        app.view_functions['admin']=combined_admin
    @app.before_request
    def protect_legacy_admin():
        if request.path in ['/', '/upload'] or request.path.startswith('/delete/'):
            password=os.environ.get('CLOUD_ADMIN_PASSWORD','')
            auth=request.authorization
            if len(password)<16 or not auth or auth.username!='admin' or not hmac.compare_digest(auth.password or '',password):
                return Response('管理员登录',401,{'WWW-Authenticate':'Basic realm="Wanwan admin"'})

    @app.post('/api/library-publish')
    def publish():
        token=os.environ.get('LIBRARY_PUBLISH_TOKEN','')
        if len(token)<32 or not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+token):
            return jsonify(error='云端发布验证失败。'),401
        if request.content_length is None or request.content_length>81*1024*1024:
            return jsonify(error='每次发布最多80MB，请分成两个合集。'),413
        title=request.headers.get('X-Collection-Title','')
        try:
            from urllib.parse import unquote
            title=unquote(title).strip()
            if not 1<=len(title)<=120:raise ValueError()
            raw=request.get_data()
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                infos=z.infolist()
                if not 1<=len(infos)<=200 or sum(f.file_size for f in infos)>80*1024*1024:raise ValueError()
                files=[];names=set()
                for f in infos:
                    if f.is_dir() or '/' in f.filename or '\\' in f.filename or not f.filename.lower().endswith('.png') or f.filename in names or f.file_size>33*1024*1024:raise ValueError()
                    names.add(f.filename);data=z.read(f)
                    with Image.open(io.BytesIO(data)) as im:
                        if im.format!='PNG' or im.width*im.height>40_000_000:raise ValueError()
                        im.verify()
                    files.append((secrets.token_hex(16),f.filename,data))
        except Exception:
            return jsonify(error='合集内容无效，请重新选择高清PNG。'),400
        digest=hashlib.sha256(json.dumps([title,sorted((name,hashlib.sha256(data).hexdigest()) for _,name,data in files)],ensure_ascii=False).encode()).hexdigest()
        conn=connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    # Serialize only the same payload, including simultaneous retries.
                    cur.execute('SELECT pg_advisory_xact_lock(%s)',(int(digest[:15],16),))
                    cur.execute('CREATE TABLE IF NOT EXISTS library_collections(id TEXT PRIMARY KEY,digest TEXT UNIQUE NOT NULL,title TEXT NOT NULL)')
                    cur.execute('CREATE TABLE IF NOT EXISTS library_collection_files(id TEXT PRIMARY KEY,collection_id TEXT REFERENCES library_collections(id),filename TEXT NOT NULL,data BYTEA NOT NULL)')
                    cur.execute('SELECT id FROM library_collections WHERE digest=%s',(digest,));old=cur.fetchone()
                    cid=old[0] if old else secrets.token_urlsafe(24)
                    if not old:
                        cur.execute('INSERT INTO library_collections VALUES(%s,%s,%s)',(cid,digest,title))
                        for fid,name,data in files:cur.execute('INSERT INTO library_collection_files VALUES(%s,%s,%s,%s)',(fid,cid,name,data))
            return jsonify(path='/c/'+cid,count=len(files))
        finally:conn.close()

    @app.get('/c/<cid>')
    def collection(cid):
        conn=connect()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT title FROM library_collections WHERE id=%s',(cid,));row=cur.fetchone()
                if not row:return '合集不存在',404
                cur.execute('SELECT id,filename FROM library_collection_files WHERE collection_id=%s ORDER BY filename',(cid,));files=cur.fetchall()
            return render_template_string(PAGE,title=row[0],files=files,base='/c/'+cid)
        finally:conn.close()

    @app.get('/c/<cid>/<fid>')
    def collection_file(cid,fid):
        conn=connect()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT filename,data FROM library_collection_files WHERE collection_id=%s AND id=%s',(cid,fid));row=cur.fetchone()
            if not row:return '图纸不存在',404
            return send_file(io.BytesIO(bytes(row[1])),mimetype='image/png',as_attachment=request.args.get('download')=='1',download_name=row[0])
        finally:conn.close()
