"""Additive Render delivery bridge; register on the existing Flask app."""
import hashlib, hmac, io, os, secrets, zipfile, json
from flask import request, jsonify, Response, render_template_string, send_file
from PIL import Image

PAGE='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{{ title }}</title><body><h1>{{ title }}</h1><p>共 {{ files|length }} 份高清图纸</p>{% for f in files %}<p><a href="{{ base }}/{{ f[0] }}" download>{{ f[1] }}</a></p>{% endfor %}</body></html>'''

def register(app, connect):
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
            return send_file(io.BytesIO(bytes(row[1])),mimetype='image/png',as_attachment=True,download_name=row[0])
        finally:conn.close()
