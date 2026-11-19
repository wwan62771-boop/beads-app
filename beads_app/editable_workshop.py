"""Private editable workspace backed by the existing PostgreSQL service."""
import hashlib,hmac,json,os,re,secrets,time
from collections import defaultdict,deque
from functools import wraps
from pathlib import Path
from flask import request,jsonify,make_response,redirect,render_template_string,send_file
from itsdangerous import URLSafeTimedSerializer,BadSignature,SignatureExpired
from werkzeug.security import check_password_hash
from cloud_edit_bundle import validate_bundle,LIMIT

ROOT=Path(__file__).resolve().parent
STYLE="""body{margin:0;background:#f7f8f5;color:#34463e;font:15px/1.7 system-ui,sans-serif}main{max-width:900px;margin:40px auto;padding:20px}article,form.login{background:white;padding:24px;border:1px solid #d8e1da;border-radius:16px;margin:16px 0}button,a.button,input{font:inherit;padding:10px 16px;border:1px solid #b5c7bc;border-radius:9px;background:white;color:#426858}a.button{text-decoration:none;display:inline-block;margin:4px}label{display:block;margin:16px 0}p{overflow-wrap:anywhere}.error{color:#a33}h1{font-size:26px}h2{font-size:19px}"""
LOGIN="""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>云端改图登录</title><style>{{style}}</style><main><form method="post" class="login"><h1>我的云端改图</h1><p>使用首次上传时的本机管理中心登录密码。</p><label>登录密码 <input name="password" type="password" required autocomplete="current-password"></label><p class="error">{{error}}</p><button>登录</button></form></main></html>"""
PAGE="""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>我的云端改图</title><style>{{style}}</style><main><h1>我的云端改图</h1><p>这里显示从本机主动上传的作品。选择规格后，打开工坊继续编辑。</p><form method="post" action="/editor/logout"><input type="hidden" name="csrf" value="{{csrf}}"><button>退出登录</button></form>{% for item in items %}<article><h2>{{item.bundle.name}}</h2><p>{{item.bundle.series}} · 云端第 {{item.revision}} 版</p>{% for entry in item.bundle.entries %}<a class="button" href="/editor/workshop?work={{item.id}}&entry={{loop.index0}}">{{entry.project.W}} × {{entry.project.H}} 格 · {{entry.project.paletteId}} · 继续编辑</a>{% endfor %}</article>{% else %}<p>还没有上传的作品，请在本机管理中心打开一款作品，点击“上传本款到云端”。</p>{% endfor %}</main></html>"""

def register(app,connect):
    failures=defaultdict(deque)
    def token():return os.environ.get('LIBRARY_PUBLISH_TOKEN','')
    def bearer():return len(token())>=32 and hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+token())
    def serializer():return URLSafeTimedSerializer(hashlib.sha256(token().encode()).hexdigest(),salt='private-editor-v1')
    def schema(cur):
        cur.execute('CREATE TABLE IF NOT EXISTS editable_owner(id INTEGER PRIMARY KEY,password_hash TEXT NOT NULL)')
        cur.execute('CREATE TABLE IF NOT EXISTS editable_revisions(work_id TEXT NOT NULL,revision INTEGER NOT NULL,digest TEXT NOT NULL,bundle TEXT NOT NULL,created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(work_id,revision))')
    def owner():
        conn=connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    schema(cur);cur.execute('SELECT password_hash FROM editable_owner WHERE id=1');row=cur.fetchone()
                    return row[0] if row else None
        finally:conn.close()
    def session_data():
        try:
            data=serializer().loads(request.cookies.get('private_editor',''),max_age=86400)
            password_hash=owner()
            if password_hash and hmac.compare_digest(data.get('owner',''),hashlib.sha256(password_hash.encode()).hexdigest()):return data
        except (BadSignature,SignatureExpired,TypeError):pass
        return None
    def protected(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            if bearer():return fn(*args,**kwargs)
            data=session_data() if len(token())>=32 else None
            if not data:return jsonify(error='请先登录云端改图。'),401
            if request.method!='GET' and not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),data['csrf']):
                return jsonify(error='页面验证失效，请重新登录。'),403
            return fn(*args,**kwargs)
        return wrapped
    @app.after_request
    def editor_headers(response):
        if request.path.startswith(('/editor','/editor-api')):
            response.headers['Cache-Control']='no-store'
            response.headers['X-Content-Type-Options']='nosniff'
            response.headers['X-Frame-Options']='DENY'
            response.headers['Referrer-Policy']='same-origin'
        return response
    @app.post('/editor-api/setup')
    def setup():
        if not bearer():return jsonify(error='发布密钥无效。'),401
        value=(request.json or {}).get('password_hash','')
        if not isinstance(value,str) or not re.fullmatch(r'(scrypt:32768:8:1|pbkdf2:sha256:[0-9]{5,7})\$[A-Za-z0-9]{8,64}\$[a-f0-9]{64,256}',value):
            return jsonify(error='本机登录密码格式不支持。'),400
        conn=connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    schema(cur);cur.execute('INSERT INTO editable_owner VALUES(1,%s) ON CONFLICT(id) DO NOTHING',(value,))
        finally:conn.close()
        return jsonify(ok=True)
    @app.route('/editor/login',methods=['GET','POST'])
    def login():
        error=''
        if request.method=='POST':
            ip=request.remote_addr;now=time.time();queue=failures[ip]
            while queue and now-queue[0]>900:queue.popleft()
            if len(queue)>=8:error='尝试次数过多，请15分钟后再试。'
            else:
                password_hash=owner() if len(token())>=32 else None
                password=request.form.get('password','')[:512]
                if password_hash and check_password_hash(password_hash,password):
                    failures.pop(ip,None)
                    response=make_response(redirect('/editor'))
                    response.set_cookie('private_editor',serializer().dumps(dict(owner=hashlib.sha256(password_hash.encode()).hexdigest(),csrf=secrets.token_urlsafe(32))),max_age=86400,secure=True,httponly=True,samesite='Strict',path='/')
                    return response
                queue.append(now);error='密码不正确，或本机尚未上传作品。'
        return render_template_string(LOGIN,style=STYLE,error=error)
    @app.post('/editor/logout')
    def logout():
        data=session_data()
        if not data or not hmac.compare_digest(request.form.get('csrf',''),data['csrf']):return '页面验证失效',403
        response=make_response(redirect('/editor/login'));response.delete_cookie('private_editor',path='/');return response
    def read_works():
        conn=connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    schema(cur)
                    cur.execute("SELECT work_id,revision,jsonb_build_object('name',bundle::jsonb->'name','series',bundle::jsonb->'series','entries',(SELECT jsonb_agg(jsonb_build_object('project',jsonb_build_object('W',entry->'project'->'W','H',entry->'project'->'H','paletteId',entry->'project'->'paletteId'))) FROM jsonb_array_elements(bundle::jsonb->'entries') entry))::text FROM (SELECT DISTINCT ON(work_id) work_id,revision,bundle FROM editable_revisions ORDER BY work_id,revision DESC) latest ORDER BY work_id LIMIT 200")
                    return [dict(id=row[0],revision=row[1],bundle=json.loads(row[2])) for row in cur.fetchall()]
        finally:conn.close()
    @app.get('/editor')
    def index():
        data=session_data() if len(token())>=32 else None
        if not data:return redirect('/editor/login')
        return render_template_string(PAGE,style=STYLE,items=read_works(),csrf=data['csrf'])
    @app.get('/editor-api/session')
    @protected
    def session_info():return jsonify(csrf=(session_data() or {}).get('csrf',''))
    @app.get('/editor-api/works')
    @protected
    def works():
        return jsonify(items=[dict(id=item['id'],revision=item['revision'],name=item['bundle']['name'],series=item['bundle'].get('series',''),specs=len(item['bundle']['entries'])) for item in read_works()])
    @app.route('/editor-api/works/<wid>',methods=['GET','POST'])
    @protected
    def work(wid):
        if not re.fullmatch('[a-f0-9]{32}',wid):return jsonify(error='作品编号无效。'),400
        payload=request.get_json(silent=True) or {}
        if request.method=='POST':
            try:raw,digest=validate_bundle(payload.get('bundle'))
            except (ValueError,TypeError,KeyError,AttributeError) as error:return jsonify(error=str(error)),400
            expected=payload.get('expected_revision')
            if type(expected) is not int or expected<0:return jsonify(error='缺少版本校验。'),400
        conn=connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    schema(cur)
                    cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(wid,))
                    cur.execute('SELECT revision,digest,bundle FROM editable_revisions WHERE work_id=%s ORDER BY revision DESC LIMIT 1',(wid,))
                    old=cur.fetchone()
                    if request.method=='GET':
                        if not old:return jsonify(error='云端作品不存在。'),404
                        return jsonify(revision=old[0],bundle=json.loads(old[2]))
                    revision=old[0] if old else 0
                    if old and old[1]==digest:return jsonify(revision=revision,duplicate=True)
                    if revision!=expected:return jsonify(error='云端已有更新版本，请先取回或重新打开，避免覆盖其他电脑的修改。'),409
                    cur.execute('INSERT INTO editable_revisions(work_id,revision,digest,bundle) VALUES(%s,%s,%s,%s)',(wid,revision+1,digest,raw.decode()))
                    return jsonify(revision=revision+1)
        finally:conn.close()
    @app.get('/editor/workshop')
    def workshop():
        if not session_data():return redirect('/editor/login')
        source=(ROOT/'editor-workshop.html').read_text()
        source=source.replace('</html>','<script src="/editor/client.js"></script></html>')
        return source
    @app.get('/editor/client.js')
    def client():
        if not session_data():return '请先登录',401
        return send_file(ROOT/'editor-client.js',mimetype='application/javascript')
