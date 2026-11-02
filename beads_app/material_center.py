"""Private material handoff, additive to the existing PostgreSQL application."""
import hashlib,hmac,io,json,os,secrets,tempfile,time,zipfile
from collections import defaultdict,deque
from functools import wraps
from flask import request,jsonify,render_template_string,make_response,redirect,send_file
from itsdangerous import URLSafeTimedSerializer,BadSignature,SignatureExpired
from PIL import Image

STYLE='''*{box-sizing:border-box}body{margin:0;background:#eef5ff;color:#28496b;font:15px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1050px;margin:auto;padding:24px 16px}header,.row{display:flex;gap:14px;align-items:center;justify-content:space-between}h1{font-size:26px}h2{font-size:19px;margin:0}p{color:#66809b}article,.login{background:white;border:1px solid #c7dbf5;border-radius:18px;padding:20px;margin:16px 0;box-shadow:0 4px 15px #315c9609}.login{max-width:420px;margin:12vh auto}button,.button{display:inline-block;border:1px solid #8fb3e2;background:#f4f9ff;color:#29598b;border-radius:10px;padding:10px 14px;font:inherit;text-decoration:none;cursor:pointer}button.primary{background:#347de0;color:white}input,select,textarea{font:inherit;padding:10px;border:1px solid #bfd4ee;border-radius:9px;max-width:100%}input[type=password]{width:100%}.actions{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.images{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}.image img{width:100%;height:200px;object-fit:contain;background:#f7f9fc;border-radius:9px}.image>a{display:block;text-decoration:none}.download-original{display:block;text-align:center;margin-top:8px;padding:8px 12px;border:1px solid #bfd4ee;border-radius:9px;background:#f4f9ff;color:#29598b;font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;background:#f5f8fc;padding:14px;border-radius:10px}.badge{background:#eaf2ff;padding:4px 10px;border-radius:20px;font-size:13px}.error{color:#aa3737}button:disabled{opacity:.6;cursor:wait}label{display:block;margin:10px 0}@media(max-width:500px){header{align-items:flex-start;flex-wrap:wrap}.images{grid-template-columns:1fr 1fr}.image img{height:160px}}'''
LOGIN='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>素材领取中心 · 登录</title><style>{{ style }}</style><main><form class="login" method="post"><h1>一万万一 · 素材领取中心</h1><p>登录后查看、下载已准备好的素材。</p><label>领取密码<input name="password" type="password" autocomplete="current-password" required maxlength="512"></label><p class="error">{{ error }}</p><button class="primary">进入素材库</button></form></main></html>'''
PAGE='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>一万万一 · 素材领取中心</title><style>{{ style }}</style><main><header><div><h1>一万万一 · 素材领取中心</h1><p>最新素材在最上面，下载后记得标记进度。</p></div><form method="post" action="/materials/logout"><input type="hidden" name="csrf" value="{{ csrf }}"><button>退出登录</button></form></header><form class="actions"><input name="q" value="{{ q }}" placeholder="搜索素材名称" aria-label="搜索素材名称"><select name="status" aria-label="发布状态">{% for key,label in states.items() %}<option value="{{ key }}" {% if key==status %}selected{% endif %}>{{ label }}</option>{% endfor %}</select><button>筛选</button></form>{% for item in items %}<article data-id="{{ item.id }}"><div class="row"><h2>{{ item.title }}</h2><span class="badge">{{ labels[item.status] }}</span></div><p>{{ item.created }} · {{ item.files|length }} 张图片</p><div class="actions"><a class="button" href="/materials/{{ item.id }}/zip">下载整套素材</a>{% if item.status!='downloaded' %}<button data-status="downloaded">标记已下载</button>{% endif %}{% if item.status!='published' %}<button class="primary" data-status="published">标记已发布</button>{% else %}<button data-status="ready">改为待发布</button>{% endif %}</div>{% if item['copy'] %}<section><h3>小红书文案</h3><button data-copy="copy">复制文案</button><pre data-content="copy">{{ item['copy'] }}</pre></section>{% endif %}{% if item['template'] %}<section><h3>小红书固定模板</h3><button data-copy="template">复制固定模板</button><pre data-content="template">{{ item['template'] }}</pre></section>{% endif %}{% if item['links'] %}<section><h3>客户云端链接</h3>{% for link in item['links'] %}<p><a href="{{ link.url }}" target="_blank" rel="noopener">{{ link.title }}</a></p>{% endfor %}<button data-copy="links">复制完整提取文案</button><pre data-content="links">{{ item['link_copy'] }}</pre></section>{% endif %}{% for group in item['groups'] %}{% if group.files %}<h3>{{ group.label }} · {{ group.files|length }} 张</h3><div class="images">{% for f in group.files %}<div class="image"><a href="/materials/{{ item.id }}/file/{{ f[0] }}?download=1"><img loading="lazy" src="/materials/{{ item.id }}/file/{{ f[0] }}?preview=1" alt="{{ f[1] }}"><span class="download-original">下载原图</span></a></div>{% endfor %}</div>{% endif %}{% endfor %}<p role="status" class="feedback"></p></article>{% else %}<article>暂时没有符合条件的素材。发布后会显示在这里。</article>{% endfor %}<nav class="actions">{% if page>1 %}<a class="button" href="?page={{ page-1 }}&q={{ q|urlencode }}&status={{ status }}">上一页</a>{% endif %}<span>第 {{ page }} 页 · 共 {{ total }} 组</span>{% if page*12<total %}<a class="button" href="?page={{ page+1 }}&q={{ q|urlencode }}&status={{ status }}">下一页</a>{% endif %}</nav></main><script>const csrf={{ csrf|tojson }};for(const b of document.querySelectorAll('[data-copy]'))b.onclick=async()=>{const pre=b.closest('article').querySelector('[data-content="'+b.dataset.copy+'"]');try{await navigator.clipboard.writeText(pre.textContent);b.textContent='已复制';}catch{const range=document.createRange();range.selectNodeContents(pre);getSelection().removeAllRanges();getSelection().addRange(range);b.closest('article').querySelector('.feedback').textContent='请复制已选中的文案。'}};for(const b of document.querySelectorAll('[data-status]'))b.onclick=async()=>{b.disabled=true;const row=b.closest('article');try{const r=await fetch('/materials/'+row.dataset.id+'/status',{method:'POST',headers:{'Content-Type':'application/json','X-Material-CSRF':csrf},body:JSON.stringify({status:b.dataset.status})});if(!r.ok)throw Error('保存失败，请刷新登录后重试。');location.reload()}catch(e){row.querySelector('.feedback').textContent=e.message;b.disabled=false}};</script></html>'''

def customer_link_copy(links):
    return '\n\n'.join(link['title']+'\n亲，图纸提取链接如下：\n'+link['url']+'\n💗 温馨提示：\n请复制上方链接，粘贴到手机浏览器打开，即可下载高清拼豆图纸哦！\n⏳ 首次打开可能需要等待约10秒，后台启动后即可正常访问，请耐心等待一下哦～' for link in links)

def register(app,connect):
    failures=defaultdict(deque)
    def schema(cur):
        cur.execute("CREATE TABLE IF NOT EXISTS material_sets(id TEXT PRIMARY KEY,digest TEXT UNIQUE NOT NULL,title TEXT NOT NULL,copy TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'ready',complete INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL,manifest TEXT NOT NULL)")
        cur.execute('CREATE TABLE IF NOT EXISTS material_files(id TEXT PRIMARY KEY,set_id TEXT REFERENCES material_sets(id),filename TEXT NOT NULL,sha TEXT NOT NULL,data BYTEA NOT NULL,preview BYTEA NOT NULL)')
        cur.execute('CREATE TABLE IF NOT EXISTS material_bundle_meta(id TEXT PRIMARY KEY REFERENCES material_sets(id),content TEXT NOT NULL)')
    def auth_publish():
        token=os.environ.get('LIBRARY_PUBLISH_TOKEN','')
        return len(token)>=32 and hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+token)
    def signer():
        password=os.environ.get('MATERIAL_READER_PASSWORD','');token=os.environ.get('LIBRARY_PUBLISH_TOKEN','')
        if not ((len(password)==6 and password.isascii() and password.isdigit()) or len(password)>=16) or len(token)<32:return None
        return URLSafeTimedSerializer(hashlib.sha256((password+'\0'+token).encode()).hexdigest(),salt='materials-reader-v1')
    def ticket():
        s=signer()
        if s:
            try:return s.loads(request.cookies.get('materials_login',''),max_age=7*86400)
            except (BadSignature,SignatureExpired):pass
        return None
    def reader(fn):
        @wraps(fn)
        def wrapped(*a,**k):
            t=ticket()
            if not t:
                if request.method!='GET':return jsonify(error='请重新登录。'),401
                return redirect('/materials/login')
            if request.method=='POST' and not hmac.compare_digest(request.headers.get('X-Material-CSRF',request.form.get('csrf','')),t['csrf']):return jsonify(error='请刷新页面重试。'),403
            return fn(*a,**k)
        return wrapped
    @app.after_request
    def private_headers(response):
        if request.path.startswith(('/materials','/api/material-')):
            response.headers['Cache-Control']='private, no-store';response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer';response.headers['X-Frame-Options']='DENY'
        return response
    @app.route('/materials/login',methods=['GET','POST'])
    def materials_login():
        s=signer()
        if not s:return '素材中心尚未配置领取密码，请联系管理员。',503
        error=''
        if request.method=='POST':
            ip=request.remote_addr or 'unknown';now=time.monotonic();bucket=failures[ip]
            while bucket and bucket[0]<now-900:bucket.popleft()
            if len(bucket)>=10:return '尝试次数过多，请15分钟后再试。',429
            if hmac.compare_digest(request.form.get('password','').encode(),os.environ['MATERIAL_READER_PASSWORD'].encode()):
                failures.pop(ip,None);r=make_response(redirect('/materials'));r.set_cookie('materials_login',s.dumps({'csrf':secrets.token_urlsafe(24)}),max_age=7*86400,httponly=True,secure=True,samesite='Lax');return r
            bucket.append(now);error='密码不正确，请重试。'
            if len(failures)>10000:failures.clear()
        return render_template_string(LOGIN,style=STYLE,error=error)
    @app.post('/materials/logout')
    @reader
    def materials_logout():
        r=make_response(redirect('/materials/login'));r.delete_cookie('materials_login',secure=True,httponly=True,samesite='Lax');return r
    @app.post('/api/material-start')
    def materials_start():
        if not auth_publish():return jsonify(error='发布验证失败。'),401
        if (request.content_length or 0)>200000:return jsonify(error='资料过大。'),413
        d=request.get_json(silent=True) or {};title=d.get('title');copy=d.get('copy','');files=d.get('files');template=d.get('template','');links=d.get('links',[])
        if not isinstance(title,str) or not 1<=len(title.strip())<=120 or not isinstance(copy,str) or len(copy)>16000 or not isinstance(files,list) or not 1<=len(files)<=100:return jsonify(error='请填写名称并选择1–100张商品图片。'),400
        if not isinstance(template,str) or len(template)>24000 or not isinstance(links,list) or len(links)>20:return jsonify(error='模板或链接资料无效。'),400
        import re
        for link in links:
            if not isinstance(link,dict) or not isinstance(link.get('title'),str) or len(link['title'])>200 or not isinstance(link.get('url'),str) or not re.fullmatch(r'https://wanwan-dwt0\.onrender\.com/[cd]/[A-Za-z0-9_-]+/?',link['url']):return jsonify(error='客户提取链接无效。'),400
        names=set();total=0
        for f in files:
            if not isinstance(f,dict):return jsonify(error='图片资料无效。'),400
            name=f.get('name');sha=f.get('sha');size=f.get('size')
            if not isinstance(name,str) or not name.lower().endswith('.png') or not 1<=len(name)<=200 or any(c in name for c in '/\\\x00\r\n') or name in names or not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha) or type(size)!=int or not 1<=size<=8*1024*1024:return jsonify(error='每张图片最多8MB，且名称不能重复。'),400
            if f.get('kind','product') not in ['scene','product']:return jsonify(error='图片分类无效。'),400
            names.add(name);total+=size
        if total>80*1024*1024:return jsonify(error='每组最多80MB，请分组发布。'),413
        normalized=[dict(name=f['name'],sha=f['sha'],size=f['size'],kind=f.get('kind','product')) for f in files]
        digest=hashlib.sha256(json.dumps([title.strip(),copy,normalized,template,links],ensure_ascii=False,sort_keys=True).encode()).hexdigest();conn=connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    schema(cur);cur.execute('SELECT pg_advisory_xact_lock(%s)',(int(digest[:15],16),));cur.execute('SELECT id,complete FROM material_sets WHERE digest=%s',(digest,));row=cur.fetchone()
                    if row:return jsonify(id=row[0],complete=bool(row[1]))
                    identity=secrets.token_hex(16);cur.execute('INSERT INTO material_sets(id,digest,title,copy,created,manifest) VALUES(%s,%s,%s,%s,%s,%s)',(identity,digest,title.strip(),copy,time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime()),json.dumps(normalized,ensure_ascii=False)))
                    cur.execute('INSERT INTO material_bundle_meta(id,content) VALUES(%s,%s)',(identity,json.dumps(dict(template=template,links=links),ensure_ascii=False)))
            return jsonify(id=identity,complete=False)
        finally:conn.close()
    @app.put('/api/material-upload/<identity>/<int:index>')
    def materials_upload(identity,index):
        if not auth_publish():return jsonify(error='发布验证失败。'),401
        if request.content_length is None or not 1<=request.content_length<=8*1024*1024:return jsonify(error='每张图片最多8MB。'),413
        conn=connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT manifest FROM material_sets WHERE id=%s',(identity,));row=cur.fetchone()
                    if not row:return jsonify(error='发布记录不存在。'),404
                    manifest=json.loads(row[0])
                    if not 0<=index<len(manifest):return jsonify(error='图片序号无效。'),400
                    f=manifest[index];raw=request.get_data();sha=hashlib.sha256(raw).hexdigest()
                    if sha!=f['sha'] or len(raw)!=f['size']:return jsonify(error='图片校验失败。'),400
                    try:
                        with Image.open(io.BytesIO(raw)) as im:
                            if im.format!='PNG' or im.width*im.height>16_000_000:raise ValueError()
                            im.verify()
                        with Image.open(io.BytesIO(raw)) as im:
                            im.thumbnail((320,420));preview=io.BytesIO();im.save(preview,'PNG')
                    except Exception:return jsonify(error='图片无效或超过1600万像素。'),400
                    fid=hashlib.sha256((identity+':'+str(index)).encode()).hexdigest()[:32]
                    cur.execute('INSERT INTO material_files(id,set_id,filename,sha,data,preview) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING',(fid,identity,f['name'],sha,raw,preview.getvalue()))
            return jsonify(ok=True)
        finally:conn.close()
    @app.post('/api/material-finish/<identity>')
    def materials_finish(identity):
        if not auth_publish():return jsonify(error='发布验证失败。'),401
        conn=connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT manifest FROM material_sets WHERE id=%s',(identity,));row=cur.fetchone()
                    if not row:return jsonify(error='发布记录不存在。'),404
                    cur.execute('SELECT COUNT(*) FROM material_files WHERE set_id=%s',(identity,))
                    if cur.fetchone()[0]!=len(json.loads(row[0])):return jsonify(error='还有图片未上传，请重试发布。'),409
                    cur.execute('UPDATE material_sets SET complete=1 WHERE id=%s',(identity,))
            return jsonify(url='/materials',id=identity)
        finally:conn.close()
    @app.get('/materials')
    @reader
    def materials_list():
        q=request.args.get('q','').strip()[:120];status=request.args.get('status','all');labels=dict(ready='待发布',downloaded='已下载',published='已发布');states=dict(all='全部状态',**labels)
        try:page=max(1,min(100000,int(request.args.get('page','1'))))
        except ValueError:page=1
        where=' WHERE complete=1';args=[]
        if q:where+=" AND LOWER(title) LIKE LOWER(%s) ESCAPE '!'";args.append('%'+q.replace('!','!!').replace('%','!%').replace('_','!_')+'%')
        if status in labels:where+=' AND status=%s';args.append(status)
        conn=connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    schema(cur);cur.execute('SELECT COUNT(*) FROM material_sets'+where,tuple(args));total=cur.fetchone()[0];page=min(page,max(1,(total+11)//12));cur.execute('SELECT id,title,copy,status,created FROM material_sets'+where+' ORDER BY created DESC,id DESC LIMIT 12 OFFSET %s',tuple(args+[(page-1)*12]));rows=cur.fetchall();items=[]
                    for row in rows:
                        item=dict(zip(['id','title','copy','status','created'],row));cur.execute('SELECT id,filename FROM material_files WHERE set_id=%s ORDER BY filename',(row[0],));item['files']=cur.fetchall();cur.execute('SELECT content FROM material_bundle_meta WHERE id=%s',(row[0],));meta=cur.fetchone();meta=json.loads(meta[0]) if meta else {};item['template']=meta.get('template','');item['links']=meta.get('links',[]);item['link_copy']=customer_link_copy(item['links']);cur.execute('SELECT manifest FROM material_sets WHERE id=%s',(row[0],));manifest=json.loads(cur.fetchone()[0]);kinds={f['name']:f.get('kind','product') for f in manifest};item['groups']=[dict(label=label,files=[f for f in item['files'] if kinds.get(f[1],'product')==kind]) for kind,label in [('scene','场景图'),('product','商品图')]];items.append(item)
            return render_template_string(PAGE,style=STYLE,csrf=ticket()['csrf'],items=items,q=q,status=status,states=states,labels=labels,total=total,page=page)
        finally:conn.close()
    @app.post('/materials/<identity>/status')
    @reader
    def materials_status(identity):
        status=(request.get_json(silent=True) or {}).get('status')
        if status not in ['ready','downloaded','published']:return jsonify(error='状态无效。'),400
        conn=connect()
        try:
            with conn:
                with conn.cursor() as cur:cur.execute('UPDATE material_sets SET status=%s WHERE id=%s AND complete=1',(status,identity));count=cur.rowcount
            return (jsonify(ok=True),200) if count else (jsonify(error='素材不存在。'),404)
        finally:conn.close()
    @app.get('/materials/<identity>/file/<fid>')
    @reader
    def materials_file(identity,fid):
        conn=connect()
        try:
            with conn.cursor() as cur:
                field='f.preview' if request.args.get('preview')=='1' else 'f.data'
                cur.execute('SELECT f.filename,'+field+' FROM material_files f JOIN material_sets s ON s.id=f.set_id WHERE s.complete=1 AND f.set_id=%s AND f.id=%s',(identity,fid));row=cur.fetchone()
            if not row:return '素材不存在',404
            return send_file(io.BytesIO(bytes(row[1])),mimetype='image/png',as_attachment=request.args.get('download')=='1',download_name=row[0])
        finally:conn.close()
    @app.get('/materials/<identity>/zip')
    @reader
    def materials_zip(identity):
        conn=connect();archive=tempfile.SpooledTemporaryFile(max_size=1024*1024,mode='w+b')
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT title,copy FROM material_sets WHERE id=%s AND complete=1',(identity,));row=cur.fetchone()
                if not row:archive.close();return '素材不存在',404
                cur.execute('SELECT id,filename FROM material_files WHERE set_id=%s ORDER BY filename',(identity,));files=cur.fetchall()
                cur.execute('SELECT content FROM material_bundle_meta WHERE id=%s',(identity,));meta=cur.fetchone();meta=json.loads(meta[0]) if meta else {}
                cur.execute('SELECT manifest FROM material_sets WHERE id=%s',(identity,));manifest=json.loads(cur.fetchone()[0]);kinds={f['name']:f.get('kind','product') for f in manifest}
                # Old published sets retain the original flat ZIP layout.
                structured=bool(meta.get('template') or meta.get('links') or any(f.get('kind')=='scene' for f in manifest))
                with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED) as z:
                    z.writestr('发布文案.txt',row[1].encode('utf-8-sig'))
                    if meta.get('template'):z.writestr('小红书固定模板.txt',meta['template'].encode('utf-8-sig'))
                    if meta.get('links'):z.writestr('客户云端链接.txt',customer_link_copy(meta['links']).encode('utf-8-sig'))
                    for fid,name in files:
                        folder=('场景图/' if kinds.get(name)=='scene' else '商品图/') if structured else ''
                        cur.execute('SELECT data FROM material_files WHERE id=%s AND set_id=%s',(fid,identity));z.writestr(folder+name,bytes(cur.fetchone()[0]))
            archive.seek(0);response=send_file(archive,mimetype='application/zip',as_attachment=True,download_name='素材-'+identity[:8]+'.zip');response.call_on_close(archive.close);return response
        except Exception:archive.close();raise
        finally:conn.close()
