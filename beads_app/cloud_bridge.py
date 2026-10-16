"""Additive Render delivery bridge; register on the existing Flask app."""
import hashlib, hmac, io, os, secrets, zipfile, json
from flask import request, jsonify, Response, render_template_string, send_file, make_response
from PIL import Image

PAGE='\n<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">\n    <title>{{ title }} - 图纸提取下载</title>\n    <style>\n        * { box-sizing: border-box; }\n        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8f9fa; margin: 0; padding: 12px; text-align: center; color: #333; }\n        .container { max-width: 600px; margin: 0 auto; background: #fff; padding: 18px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); }\n        h1 { font-size: 20px; color: #222; margin-top: 5px; margin-bottom: 8px; word-break: break-all; }\n        .tip-banner { background: #fff3cd; color: #856404; padding: 10px; border-radius: 8px; font-size: 13px; margin-bottom: 18px; text-align: left; line-height: 1.5; }\n        .img-card { margin-bottom: 20px; border: 1px solid #edf2f7; border-radius: 10px; padding: 10px; background: #ffffff; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }\n        .img-card img { width: 100%; height: auto; border-radius: 6px; display: block; margin-bottom: 10px; }\n        .download-btn { display: block; width: 100%; padding: 12px; background: #28a745; color: white; text-decoration: none; border-radius: 8px; font-size: 15px; font-weight: bold; text-align: center; }\n        .download-btn:active { background: #218838; }\n    </style>\n</head>\n<body>\n    <div class="container">\n        <h1>✨ {{ title }} ✨</h1>\n        <div class="tip-banner">\n            💡 <strong>保存提示：</strong><br>\n            • <strong>手机端：</strong>可直接长按下方图纸图片，选择“保存到相册”。<br>\n            • <strong>电脑端/原图：</strong>可点击图片下方的绿色按钮直接下载。\n        </div>\n        \n        {% for file in files %}\n        <div class="img-card">\n            <img src="{{ base }}/{{ file[0] }}" alt="{{ file[1] }}" loading="lazy">\n            <a class="download-btn" href="{{ base }}/{{ file[0] }}?download=1" download="{{ file[1] }}">📥 点击下载高清原图</a>\n        </div>\n        {% endfor %}\n    </div>\n</body>\n</html>\n'


ADMIN_COLLECTIONS = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>万万 · 云端图纸</title><style>\n*{box-sizing:border-box}body{margin:0;background:#f7f8f5;color:#34463e;font:15px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}.page{max-width:1000px;margin:auto;padding:20px 14px}h1{font-size:24px;margin:8px 0}p{color:#78867d;font-size:13px}button,input,select{font:inherit}button,.action{border:1px solid #d8e1da;background:#fff;color:#426858;border-radius:8px;padding:8px 12px;text-decoration:none;cursor:pointer}input,select{padding:10px;border:1px solid #d8e1da;border-radius:8px;background:white;min-width:0}.toolbar{display:flex;gap:8px;margin:18px 0;flex-wrap:wrap}.toolbar input{flex:1;min-width:150px}.row{display:flex;gap:14px;align-items:center;background:white;padding:14px;border:1px solid #e3e8e1;border-radius:12px;margin:10px 0}.thumb{width:86px;height:102px;flex:0 0 86px;object-fit:contain;background:#f7f7f3;border-radius:8px}.content{min-width:0;flex:1}.content h2{font-size:16px;margin:0 0 4px;overflow-wrap:anywhere}.meta{font-size:12px;color:#839086;margin:0 0 8px}.actions{display:flex;flex-wrap:wrap;gap:7px}.actions button,.actions a{font-size:13px;padding:7px 9px}.feedback{margin:4px 0 0;color:#56816a}.copyfield{width:100%;margin-top:8px;min-height:100px}details{padding:12px;background:#fff;border:1px solid #e3e8e1;border-radius:10px;margin:18px 0}summary{cursor:pointer}details form{display:grid;gap:10px;margin-top:10px}.pager{display:flex;justify-content:center;gap:16px;align-items:center;margin:22px 0}.empty{padding:30px;text-align:center}.danger{color:#b06b62!important}@media(max-width:480px){.row{gap:10px;padding:11px}.thumb{width:68px;height:88px;flex-basis:68px}.actions{gap:6px}.actions button,.actions a{padding:6px 8px;font-size:12px}}\n</style></head><body><main class="page"><h1>我的云端图纸</h1><p>新旧图纸统一查看，客户原有链接继续使用。</p>\n<form class="toolbar" method="get"><input name="q" value="{{ q }}" placeholder="搜索名称或链接编号…" aria-label="搜索名称或链接编号"><select name="source" aria-label="来源"><option value="all" {% if filter_source==\'all\' %}selected{% endif %}>全部图纸</option><option value="new" {% if filter_source==\'new\' %}selected{% endif %}>管理中心发布</option><option value="old" {% if filter_source==\'old\' %}selected{% endif %}>以前直接上传</option></select><button>搜索</button>{% if q or filter_source!=\'all\' %}<a class="action" href="/">清除</a>{% endif %}</form>\n<p>共{{ total }}套 · 按名称排列 · 每页20套</p>\n{% for item in items %}<article class="row"><img class="thumb" src="{{ item.image }}" alt="{{ item.title }}" loading="lazy"><div class="content"><h2>{{ item.title }}</h2><p class="meta">{{ \'管理中心发布\' if item.kind==\'new\' else \'以前直接上传\' }} · {{ item.count }}份图纸 · {{ item.id[-6:] }}</p><div class="actions"><a class="action" href="{{ item.path }}" target="_blank" rel="noopener">打开</a><button type="button" data-copy="link" data-path="{{ item.path }}">复制链接</button><button type="button" data-copy="message" data-path="{{ item.path }}">复制提取文案</button>{% if item.kind==\'old\' %}<a class="action danger" href="/delete/{{ item.id }}" data-delete>删除</a>{% endif %}</div><p class="feedback" role="status"></p><textarea class="copyfield" readonly hidden aria-label="待复制内容"></textarea></div></article>{% else %}<div class="empty">没有找到图纸，请换个关键词。</div>{% endfor %}\n<nav class="pager">{% if page>1 %}<a class="action" href="{{ url_for(\'admin\',q=q,source=filter_source,page=page-1) }}">上一页</a>{% endif %}<span>{{ page }} / {{ pages }}页</span>{% if page<pages %}<a class="action" href="{{ url_for(\'admin\',q=q,source=filter_source,page=page+1) }}">下一页</a>{% endif %}</nav>\n<details><summary>直接上传新图纸</summary>{% for message in get_flashed_messages() %}<p>{{ message }}</p>{% endfor %}<form action="/upload" method="post" enctype="multipart/form-data"><label>图纸名称<input name="title" required maxlength="255"></label><input type="file" name="files" multiple accept="image/*" required><button>上传并生成链接</button></form></details></main>\n<script>\nfor(const button of document.querySelectorAll(\'[data-copy]\'))button.addEventListener(\'click\',async()=>{const url=location.origin+button.dataset.path,card=button.closest(\'.row\'),field=card.querySelector(\'textarea\'),feedback=card.querySelector(\'.feedback\'),text=button.dataset.copy===\'link\'?url:`亲，图纸提取链接如下：\\n${url}\\n💗 温馨提示：\\n请复制上方链接，粘贴到手机浏览器打开，即可下载高清拼豆图纸哦！\\n⏳ 首次打开可能需要等待约10秒，后台启动后即可正常访问，请耐心等待一下哦～`;try{await navigator.clipboard.writeText(text);feedback.textContent=\'已复制\';field.hidden=true;}catch{field.hidden=false;field.value=text;field.focus();field.select();feedback.textContent=\'请长按下方已选内容复制。\';}});\nfor(const link of document.querySelectorAll(\'[data-delete]\'))link.addEventListener(\'click\',e=>{if(!confirm(\'确认删除这套图纸？删除后原客户链接将无法下载。\'))e.preventDefault();});\n</script></body></html>\n'

def register(app, connect):
    # Keep the original uploads/list/actions and add published collections above it.
    original_admin=app.view_functions.get('admin')
    if original_admin:
        def combined_admin():
            q=request.args.get('q','').strip()[:200];source=request.args.get('source','all')
            if source not in ['all','new','old']:source='all'
            try:page=max(1,int(request.args.get('page','1')))
            except ValueError:page=1
            conn=connect()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute('CREATE TABLE IF NOT EXISTS library_collections(id TEXT PRIMARY KEY,digest TEXT UNIQUE NOT NULL,title TEXT NOT NULL)')
                        cur.execute('CREATE TABLE IF NOT EXISTS library_collection_files(id TEXT PRIMARY KEY,collection_id TEXT REFERENCES library_collections(id),filename TEXT NOT NULL,data BYTEA NOT NULL)')
                        union="SELECT 'new' AS kind,c.id,c.title,(SELECT COUNT(*) FROM library_collection_files f WHERE f.collection_id=c.id) AS count,(SELECT MIN(f.id) FROM library_collection_files f WHERE f.collection_id=c.id) AS thumb FROM library_collections c UNION ALL SELECT 'old',p.id,p.title,(SELECT COUNT(*) FROM pattern_images i WHERE i.pattern_id=p.id),(SELECT MIN(i.id) FROM pattern_images i WHERE i.pattern_id=p.id) FROM patterns p"
                        terms=[];args=[]
                        if source!='all':terms.append('kind=%s');args.append(source)
                        if q:
                            # Treat user keywords as literal substrings, including % and _.
                            keyword='%'+q.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
                            terms.append("(LOWER(title) LIKE LOWER(%s) ESCAPE '!' OR id LIKE %s ESCAPE '!')");args.extend([keyword,keyword])
                        where=' WHERE '+' AND '.join(terms) if terms else ''
                        cur.execute('SELECT COUNT(*) FROM ('+union+') AS entries'+where,tuple(args));total=cur.fetchone()[0]
                        pages=max(1,(total+19)//20);page=min(page,pages)
                        cur.execute('SELECT * FROM ('+union+') AS entries'+where+' ORDER BY title,kind,id LIMIT %s OFFSET %s',tuple(args+[20,(page-1)*20]));rows=cur.fetchall()
                items=[]
                for kind,identity,title,count,thumb in rows:
                    path=('/c/' if kind=='new' else '/d/')+identity
                    items.append(dict(kind=kind,id=identity,title=title,count=count,path=path,image=('/c/'+identity+'/'+thumb if kind=='new' else '/img/'+thumb) if thumb else ''))
                return render_template_string(ADMIN_COLLECTIONS,items=items,q=q,filter_source=source,total=total,page=page,pages=pages)
            finally:conn.close()
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
