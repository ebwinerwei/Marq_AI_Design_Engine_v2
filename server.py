#!/usr/bin/env python3
"""M.A.D.E. isolated local service. Standard library, Python 3.9+."""
import threading
import argparse,base64,concurrent.futures,datetime,getpass,hashlib,hmac,io,json,os,re,secrets,sqlite3,threading,time,urllib.request,urllib.parse,webbrowser,zipfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from contextlib import contextmanager
from engine.layout import solve,digest
from engine import jobs as artifact_jobs
from engine.formats import dxf,xlsx,glb
ROOT=Path(__file__).resolve().parent
WEB=ROOT/'web'
DATA=ROOT/'private'
PREFIX='/api/made/v1/'
roles=('admin','designer','reviewer','sales','procurement','cg')
pilot_jobs_active=threading.Event()
pool=concurrent.futures.ThreadPoolExecutor(max_workers=2)
def js(x):return json.dumps(x,ensure_ascii=False,allow_nan=False)
def code():return secrets.token_hex(10)
def need(condition,msg):
    if not condition:raise ValueError(msg)
def allow(condition):
    if not condition:raise PermissionError('操作権限をご確認ください')
@contextmanager
def db():
    c=sqlite3.connect(DATA/'made.sqlite',timeout=20)
    c.row_factory=sqlite3.Row
    try:
        c.execute('PRAGMA foreign_keys=ON')
        yield c
        c.commit()
    except Exception:
        c.rollback();raise
    finally:c.close()

def setup(resume=True):
    DATA.mkdir(mode=0o700,parents=True,exist_ok=True)
    (DATA/'files').mkdir(exist_ok=True)
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(name text primary key, role text, salt text, hash text);
        CREATE TABLE IF NOT EXISTS sessions(key text primary key, name text, expiry integer);
        CREATE TABLE IF NOT EXISTS project(id text primary key, name text, head integer default 0, creator text);
        CREATE TABLE IF NOT EXISTS policies(id text primary key, type text, contents text, author text, reviewer text, evidence text);
        CREATE TABLE IF NOT EXISTS membership(pid text,name text,primary key(pid,name));
        CREATE TABLE IF NOT EXISTS revision(pid text,n integer,state text,spec text,result text,author text,primary key(pid,n));
        CREATE TABLE IF NOT EXISTS audit(pid text,n int,actor text,action text,ts datetime default current_timestamp);
        CREATE TABLE IF NOT EXISTS file(id text primary key,pid text,name text,sha text,size integer);
        CREATE TABLE IF NOT EXISTS task(id text primary key,pid text,n int,kind text,status text,msg text,args text,created datetime default current_timestamp,unique(pid,n,kind,args));
        """)
        if artifact_jobs.installed(c):pilot_jobs_active.set()
        if resume:
            legacy_filter=' and id not in (select id from artifact_lease)' if artifact_jobs.installed(c) else ''
            c.execute("update task set status='queued' where status='running'"+legacy_filter)
        ids=[r[0] for r in c.execute("select id from task where status='queued'")]
    if resume:
        for k in ids:pool.submit(run_job,k)

def add_user(user,role,pwd):
    need(re.fullmatch(r'[\w.-]{1,50}',user) and role in roles and len(pwd)>=12,'ユーザー名またはパスワード（12文字以上）をご確認ください')
    salt=secrets.token_hex(16)
    with db() as c:
        c.execute('insert or replace into users values(?,?,?,?)',(user,role,salt,hashlib.pbkdf2_hmac('sha256',pwd.encode(),salt.encode(),240000).hex()))
        c.execute('delete from sessions where name=?',(user,))

def audit(c,p,n,user,event):c.execute('insert into audit(pid,n,actor,action) values(?,?,?,?)',(p,n,user,event))
def get_project(c,p,u):
    row=c.execute('select * from project where id=?',(p,)).fetchone()
    allow(row and (u['role']=='admin' or c.execute('select 1 from membership where pid=? and name=?',(p,u['name'])).fetchone()))
    return row
def config():return json.loads((DATA/'gateway.json').read_text()) if (DATA/'gateway.json').is_file() else {}
def pilot_channels(cfg):
    channels={}
    if cfg.get('approved') is not True:return channels
    for kind,record in cfg.get('verifiedChannels',{}).items():
        if kind not in ('text','image') or not isinstance(record,dict):continue
        provider=cfg.get('provider','gateway')
        url=('https://api.openai.com/v1/'+('responses' if kind=='text' else 'images/edits')
             if provider=='openai' else cfg.get(kind+'Url',''))
        if not url.startswith('https://') or record.get('endpoint')!=url:continue
        if record.get('model')!=cfg.get(kind+'Model') or not record.get('model'):continue
        if not all(isinstance(record.get(k),str) and record[k].strip()
                   for k in ('account','contract','region','retention','sampleTest','expires')):continue
        try:expires=datetime.date.fromisoformat(record['expires'])
        except ValueError:continue
        if expires<datetime.datetime.now(datetime.timezone.utc).date():continue
        channels[kind]=dict(id=digest([provider,kind,record,cfg.get('token','')]),model=record['model'],account=record['account'],
                            region=record['region'],expires=record['expires'])
    return channels


def authorized_channel(cfg,kind,spec):
    channel=pilot_channels(cfg).get(kind)
    need(channel and spec.get('externalConsent') is True and
         spec.get('channelGrants',{}).get(kind)==channel['id'],'案件の接続先・契約と外部送信許諾を確認してください')
    return channel


def external(kind,body,p,cfg=None):
    if cfg is None:cfg=config()
    url=cfg.get(kind+'Url','')
    need(p.get('externalConsent') is True and cfg.get('approved') is True,'外部処理は未承認または未設定です')
    if cfg.get('provider')=='openai':
        from engine.gateway import commercial
        return commercial(cfg,kind,body)
    need(url.startswith('https://'),'承認済み接続先の設定が必要です')
    req=urllib.request.Request(url,data=js(body).encode(),headers={'Authorization':'Bearer '+cfg.get('token',''),'Content-Type':'application/json'})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=90) as resp:
        raw=resp.read(32*1024*1024+1);need(len(raw)<=32*1024*1024,'応答サイズの上限です')
        return json.loads(raw)

def asset(c,p,key):
    row=c.execute('select * from file where id=? and pid=?',(key,p)).fetchone()
    need(row,'この案件に素材がありません')
    return row,DATA/'files'/row['sha']

def solve_revision(c, project, spec):
    from engine.intent import enabled, geometry_input, solve_intent
    active=enabled(spec)
    if active and 'intentDraft' not in spec and spec.get('forkedIntentResult'):
        row=c.execute('select spec,result from revision where pid=? and n=1',(project['id'],)).fetchone()
        need(row,'派生元の版がありません')
        source=json.loads(row['spec'])
        result=json.loads(row['result'])
        need(source.get('forkedIntentResult')==spec['forkedIntentResult']==result['resultId']
             and geometry_input(source)==geometry_input(spec),'派生元の条件が変わりました。意図計画を解除してください')
        return result
    if not active or 'intentDraft' not in spec:
        return solve(spec)
    draft=spec['intentDraft']
    need(isinstance(draft,dict) and type(draft.get('revisionId')) is int,'基準版を選択してください')
    row=c.execute('select spec,result from revision where pid=? and n=?',
                  (project['id'],draft['revisionId'])).fetchone()
    need(row,'案件内の基準版を選択してください')
    source=json.loads(row['spec'])
    need(enabled(source) and geometry_input(source)==geometry_input(spec),
         '設計条件が変わりました。意図計画を解除して基準版を保存し、再作成してください')
    # Reuse the archived selection for presentation-only edits and historical replay.
    for saved in c.execute('select n,spec from revision where pid=? and n>? order by n desc',
                           (project['id'],draft['revisionId'])):
        archived=json.loads(saved['spec'])
        if archived.get('intentPlanVersion')==spec['intentPlanVersion'] and digest(archived.get('intentDraft'))==digest(draft) and geometry_input(archived)==geometry_input(spec):
            return json.loads(c.execute('select result from revision where pid=? and n=?',
                                        (project['id'],saved['n'])).fetchone()[0])
    base=json.loads(row['result'])
    from engine.intent import RULE_HASH
    need(base.get('dependencies',{}).get('ruleHash',RULE_HASH)==RULE_HASH,
         '基準版の規則内容が異なります。規則の更新を照査してください')
    return solve_intent(spec,draft,base)


def renew_job(key,token,stop):
    while not stop.wait(artifact_jobs.LEASE_SECONDS/3):
        with db() as c:
            if not artifact_jobs.renew(c,key,token):return


class PilotHTTPServer(ThreadingHTTPServer):
    next_recovery=0
    def service_actions(self):
        if not pilot_jobs_active.is_set() or time.monotonic()<self.next_recovery:return
        self.next_recovery=time.monotonic()+10
        try:
            with db() as c:pending=artifact_jobs.recover(c)
        except sqlite3.OperationalError:
            return
        outstanding=getattr(self,'pending_exports',{})
        self.pending_exports={k:v for k,v in outstanding.items() if not v.done()}
        for key in pending:
            if key not in self.pending_exports:self.pending_exports[key]=pool.submit(run_job,key)


def run_job(key):
    lease=code();tmp=DATA/(key+'-'+lease+'.tmp');final=DATA/(key+'.bin')
    heartbeat=None
    try:
        with db() as c:
            c.execute('begin immediate')
            if not c.execute("select 1 from task where id=? and status='queued'",(key,)).fetchone():return
            ownership=artifact_jobs.acquire(c,key,lease)
            if ownership=='wait':return
            if not c.execute("update task set status='running',msg=? where id=? and status='queued'",(lease,key)).rowcount:return
            job=dict(c.execute('select * from task where id=?',(key,)).fetchone())
            row=c.execute('select * from revision where pid=? and n=?',(job['pid'],job['n'])).fetchone()
            p=json.loads(row['spec']);r=json.loads(row['result']);state=row['state'];args=json.loads(job['args'])
        if ownership=='owned':
            heartbeat=threading.Event()
            threading.Thread(target=renew_job,args=(key,lease,heartbeat),daemon=True).start()
        kind=job['kind'];state=args.get('exportState',state)
        def load_asset(aid):
            with db() as conn:return asset(conn,job['pid'],aid)[1].read_bytes()
        if kind in ('dxf','xlsx','glb'):
            raw={'dxf':lambda:dxf(p,r,state),'xlsx':lambda:xlsx(p,r,state),'glb':lambda:glb(p,r,load_asset)}[kind]()
        elif kind=='cadbom':
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('drawing.dxf',dxf(p,r,state))
                z.writestr('materials.xlsx',xlsx(p,r,state))
                z.writestr('manifest.json',js(dict(project=job['pid'],revision=job['n'],resultId=r['resultId'],state=state,
                    usage='承認済' if state=='approved' else '検討用',engine=r.get('engineVersion','3.0.x'),exportVersion=args.get('exportVersion','3.1.0'),rules=p['rules'],masters=p.get('policyRefs',{}),drawingSource=p.get('drawingSource',''),units='mm',**({'dependencies':r['dependencies']} if r.get('dependencies') else {}))))
            raw=out.getvalue()
        elif kind=='cg':
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('drawing.dxf',dxf(p,r,state));z.writestr('materials.xlsx',xlsx(p,r,state));z.writestr('facade.glb',glb(p,r,load_asset))
                if p.get('model',{}).get('key')=='sample':z.write(WEB/'building01_facade_clean.glb','assets/building01_facade_clean.glb')
                z.writestr('project.json',js(p));z.writestr('layout.json',js(r))
                z.writestr('commission.json',js(dict(order=key,revision=job['n'],resultId=r['resultId'],delivery=args,units='mm',target='7680x4320')))
                with db() as c:
                    for aid in args.get('assets',p.get('assets',[])):
                        info,path=asset(c,job['pid'],aid);z.write(path,'assets/'+aid+'_'+Path(info['name']).name)
            raw=out.getvalue()
        else:raise ValueError('形式が不正です')
        tmp.write_bytes(raw)
        checksum=None
        if ownership=='owned':
            checksum=hashlib.sha256(raw).hexdigest()
            with tmp.open('rb') as stream:
                actual=hashlib.sha256()
                for chunk in iter(lambda:stream.read(1024*1024),b''):actual.update(chunk)
            need(actual.hexdigest()==checksum,'一時出力の内容が一致しません')
        with db() as c:
            if ownership=='owned' and not artifact_jobs.renew(c,key,lease):return
            if c.execute("update task set status='ready',msg='' where id=? and status='running' and msg=?",(key,lease)).rowcount:
                if ownership=='owned':
                    c.execute('update artifact_lease set sha256=?,token=null,until=0 where id=? and token=?',
                              (checksum,key,lease))
                tmp.replace(final)
    except Exception as e:
        with db() as c:c.execute("update task set status='failed',msg=? where id=? and status='running' and msg=?",(str(e)[:200],key,lease))
    finally:
        if heartbeat is not None:heartbeat.set()
        if tmp.exists():tmp.unlink()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def reply(self,body,ctype='application/json',status=200,headers=None):
        if ctype=='application/json':body=js(body).encode()
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def run(self):
        host=self.headers.get('Host','')
        allow(host in self.server.allowed_hosts)
        path=urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if self.command=='GET' and not path.startswith(PREFIX):
            file=(WEB/(path.strip('/') or 'index.html')).resolve()
            if WEB not in file.parents or not file.is_file():self.reply({},status=404);return
            mime={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.glb':'model/gltf-binary','.json':'application/json; charset=utf-8','.png':'image/png'}.get(file.suffix,'application/octet-stream')
            self.reply(file.read_bytes(),mime);return
        need(path.startswith(PREFIX),'未知の経路')
        if self.command=='POST':
            origin=self.headers.get('Origin')
            allow(not origin or urllib.parse.urlsplit(origin).netloc==host)
            allow(self.headers.get('X-Made-Request')=='1')
        route=path[len(PREFIX):]
        q=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        if self.command=='POST':
            n=int(self.headers.get('Content-Length','0'));need(0<=n<=(60*1024*1024 if route=='file' else (32 if route=='ai' else 6)*1024*1024),'ファイルサイズが上限を超えています')
            data=self.rfile.read(n)
            b={} if route=='file' else json.loads(data or b'{}')
        else:b={}
        with db() as c:
            team=c.execute('select count(*) from users').fetchone()[0]>0
            u={'name':'local','role':'admin'} if not team else None
            session=self.headers.get('Cookie','');sm=re.search(r'(?:^|; *)made_s=([0-9a-f]+)',session)
            if team and sm:
                user=c.execute('select u.name,u.role from sessions s join users u on u.name=s.name where s.key=? and expiry>?',(digest(sm[1]),time.time())).fetchone()
                if user:u=dict(user)
            if route=='login' and self.command=='POST':
                user=c.execute('select * from users where name=?',(b['name'],)).fetchone()
                allow(user and hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',b['password'].encode(),user['salt'].encode(),240000).hex(),user['hash']))
                token=secrets.token_hex(32);c.execute('insert into sessions values(?,?,?)',(digest(token),user['name'],int(time.time())+28800));c.commit()
                self.reply({'ok':True},headers={'Set-Cookie':'made_s='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'});return
            if route=='me':self.reply(dict(user=u,team=team));return
            allow(u)
            name=u['name'];role=u['role']
            if route=='logout' and self.command=='POST':
                if sm:c.execute('delete from sessions where key=?',(digest(sm[1]),))
                self.reply({'ok':True},headers={'Set-Cookie':'made_s=; Max-Age=0; Path=/; SameSite=Strict'});return
            if route=='patterns' and self.command=='GET':
                from engine.layout import RULE,pattern
                from engine.formats import CAT
                self.reply(dict(baseline=pattern({}),proposal=pattern({'rules':'word-comparison'}),sequence=RULE['seq'],catalog=CAT));return
            if route=='policies' and self.command=='GET':
                self.reply([dict(r) for r in c.execute('select * from policies order by rowid desc')]);return
            if route=='policy' and self.command=='POST':
                allow(role in ('admin','reviewer','procurement'))
                if b.get('action')=='publish':
                    row=c.execute('select * from policies where id=?',(b['id'],)).fetchone()
                    allow(row and not row['reviewer'] and (not team or row['author']!=name))
                    need(b.get('evidence','').strip(),'承認根拠を入力してください')
                    c.execute('update policies set reviewer=?,evidence=? where id=? and reviewer is null',(name,b['evidence'][:500],b['id']));key=b['id']
                else:
                    typ=b['type'];need(typ in ('rules','catalog','landscape'),'種別が不正です');contents=b['contents']
                    need(isinstance(contents,dict) and contents.get('source') and contents.get('version'),'版名・出典を入力してください')
                    if typ=='rules':
                        need(contents.get('bitsVersion') in ('p18-baseline','word-comparison'),'有効な位図版を選択してください')
                    elif typ=='catalog':
                        products=contents.get('products',{});prices=contents.get('prices',{})
                        need(isinstance(products,dict) and all(isinstance(v,list) and len(v)==6 and all(c is None or isinstance(c,str) for c in v) for v in products.values()),'各仕上の品番は3社の横・縦6欄で登録してください')
                        need(isinstance(prices,dict) and all(type(v) in (int,float) and 0<=v<float('inf') for v in prices.values()),'単価は0以上の有限値で入力してください')
                    else:
                        limit=contents.get('limit')
                        need(contents.get('denominator','net') in ('net','visible') and (limit is None or type(limit) in (int,float) and 0<=limit<=100),'面積の分母・上限を確認してください')
                    key=digest(dict(type=typ,contents=contents))[:24]
                    c.execute('insert or ignore into policies values(?,?,?,?,null,null)',(key,typ,js(contents),name))
                audit(c,'@policy',0,name,'policy '+key);c.commit();self.reply({'id':key});return
            if self.command=='GET' and route=='projects':
                query='select p.* from project p' if role=='admin' else 'select p.* from project p join membership m on p.id=m.pid where m.name=?'
                self.reply([dict(v) for v in c.execute(query,() if role=='admin' else (name,))]);return
            if route=='new' and self.command=='POST':
                allow(role in ('admin','designer'));pid=code()
                c.execute('insert into project values(?,?,0,?)',(pid,b['name'][:100],name));c.execute('insert into membership values(?,?)',(pid,name));c.commit()
                self.reply(dict(id=pid));return
            if route=='migrate' and self.command=='POST':
                from engine.legacy import migrate
                self.reply(migrate(b['document']));return
            if route=='solve' and self.command=='POST':
                spec=b['spec']
                if spec.get('intentPlanVersion') is not None:
                    project=get_project(c,b.get('pid',''),u)
                    self.reply(solve_revision(c,project,spec))
                else:self.reply(solve(spec))
                return
            pid=q.get('pid',[b.get('pid','')])[0];project=get_project(c,pid,u)
            if self.command=='GET':
                if route=='project':
                    self.reply(dict(project=dict(project),revisions=[dict(x) for x in c.execute('select n,state,author from revision where pid=? order by n desc',(pid,))],audit=[dict(x) for x in c.execute('select * from audit where pid=? order by rowid desc limit 100',(pid,))],files=[dict(x) for x in c.execute('select * from file where pid=?',(pid,))],jobs=[dict(x) for x in c.execute('select * from task where pid=? order by rowid desc',(pid,))]));return
                if route=='revision':
                    rr=c.execute('select * from revision where pid=? and n=?',(pid,int(q['n'][0]))).fetchone();need(rr,'版がありません')
                    self.reply(dict(spec=json.loads(rr['spec']),result=json.loads(rr['result']),state=rr['state']));return
                if route=='asset':
                    row,path=asset(c,pid,q['id'][0]);self.reply(path.read_bytes(),'application/octet-stream');return
                if route=='download':
                    row=c.execute('select * from task where id=? and pid=?',(q['id'][0],pid)).fetchone()
                    need(row and row['status'] in ('ready','accepted','proof','changes','delivered','verified'),'ファイル準備中です')
                    ext='zip' if row['kind'] in ('cg','cadbom') else row['kind']
                    self.reply((DATA/(row['id']+'.bin')).read_bytes(),'application/octet-stream',headers={'Content-Disposition':f'attachment; filename="Marq-r{row["n"]}-{row["id"]}.{ext}"'});return
            if self.command!='POST':raise ValueError('未知の操作')
            if route=='pilot-channels':
                allow(role in ('admin','designer'));self.reply(pilot_channels(config()));return
            if route=='intent-plan':
                from engine.intent import propose
                allow(role in ('admin','designer'))
                row=c.execute('select spec from revision where pid=? and n=?',(pid,b['n'])).fetchone()
                need(row,'保存済みの案件版を選択してください')
                spec=json.loads(row['spec'])
                plan=propose(spec,b['n'],b['faceId'],b['goal'])
                if b.get('via')=='text':
                    from engine.intent import validate
                    need(b['n']==project['head'],'外部送信は保存済みの最新版から実行してください')
                    cfg=config();authorized_channel(cfg,'text',spec)
                    suggestion=external('text',dict(task='intent-regions-v1',goal=plan['goal'],
                        observer=plan['observer'],quietIntervals=plan['quietIntervals'],peaks=plan['peaks']),spec,cfg)
                    need(isinstance(suggestion,dict) and set(suggestion)=={'quietIntervals','peaks'},'AI案の範囲を確認してください')
                    plan.update(suggestion);validate(spec,plan)
                    audit(c,pid,b['n'],name,'gateway intent-regions-v1');c.commit()
                self.reply(plan);return
            if route=='file':
                allow(role in ('admin','designer','cg','reviewer'));size=len(data);sha=hashlib.sha256(data).hexdigest();aid=code();dest=DATA/'files'/sha
                temp=DATA/'files'/aid;temp.write_bytes(data);temp.replace(dest)
                c.execute('insert into file values(?,?,?,?,?)',(aid,pid,Path(q.get('name',['asset'])[0]).name,sha,size));out=dict(id=aid)
            elif route=='save':
                allow(role in ('admin','designer','sales'));p=b['spec']
                if role=='sales':
                    ref=c.execute("select spec from revision where pid=? and state='approved' order by n desc limit 1",(pid,)).fetchone()
                    if not ref:
                        ref=c.execute('select spec from revision where pid=? and n=1',(pid,)).fetchone();allow(ref and json.loads(ref[0]).get('sourceRevision'))
                    base=json.loads(ref[0]);editable={'name','mode','seed','wave','intent','light','camera'}
                    allow({k:v for k,v in p.items() if k not in editable}=={k:v for k,v in base.items() if k not in editable})
                for aid in p.get('assets',[]):asset(c,pid,aid)
                policies=p.get('policyRefs',{})
                for typ,ref in policies.items():
                    row=c.execute('select * from policies where id=? and type=? and reviewer is not null',(ref,typ)).fetchone()
                    need(row,'承認済みマスタの版を選択してください')
                    policy=json.loads(row['contents'])
                    if typ=='rules':need(p['rules']==policy.get('bitsVersion'),'選択した位図が承認マスタと異なります')
                    if typ=='landscape':need(p.get('landscape')==policy and all(f.get('limit',p.get('limit'))==policy.get('limit') and f.get('denominator','net')==policy.get('denominator','net') for f in p['faces']),'景観条件が承認版と異なります')
                    if typ=='catalog':need(all(p.get(a,{})==policy.get(b,{}) for a,b in [('catalog','products'),('prices','prices'),('fabrication','fabrication'),('approvedSamples','approvedSamples')]),'単価・品番が承認マスタと異なります')
                result=solve_revision(c,project,p);n=b['expectedRevision']+1
                if not c.execute('update project set head=?,name=? where id=? and head=?',(n,p['name'][:100],pid,n-1)).rowcount:raise FileExistsError('他の担当者が保存済みです。最新版を確認してください')
                if p.get('intentPlanVersion')==1:
                    from engine.intent import revision_dependencies
                    snapshot=revision_dependencies(p,result,n-1 or None)
                    if n>1:
                        parent=c.execute('select state,result from revision where pid=? and n=?',(pid,n-1)).fetchone()
                        previous=json.loads(parent['result']).get('dependencies',{})
                        if previous.get('geometryHash')==snapshot['geometryHash'] and previous.get('quantityHash')==snapshot['quantityHash']:
                            snapshot['geometryReviewRevision']=n-1 if parent['state']=='approved' else previous.get('geometryReviewRevision')
                    result['dependencies']=snapshot
                c.execute('insert into revision values(?,?,?,?,?,?)',(pid,n,'draft',js(p),js(result),name))
                audit(c,pid,n,name,'save');out=dict(n=n,resultId=result['resultId'])
            elif route=='fork':
                allow(role in ('admin','designer','sales'))
                rr=c.execute('select * from revision where pid=? and n=?',(pid,b['n'])).fetchone();need(rr,'版がありません')
                if role=='sales':allow(rr['state']=='approved')
                new=code();spec=json.loads(rr['spec']);spec['name']=b['name'][:100];spec['sourceRevision']=dict(pid=pid,n=b['n'])
                result=json.loads(rr['result']);remap={}
                c.execute('insert into project values(?,?,1,?)',(new,spec['name'],name));c.execute('insert into membership values(?,?)',(new,name))
                for aid in spec.get('assets',[]):
                    row,_=asset(c,pid,aid);nid=code();remap[aid]=nid
                    c.execute('insert into file values(?,?,?,?,?)',(nid,new,row['name'],row['sha'],row['size']))
                def maprefs(v):
                    if isinstance(v,dict):return {k:maprefs(w) for k,w in v.items()}
                    if isinstance(v,list):return [maprefs(w) for w in v]
                    return remap.get(v,v) if isinstance(v,str) else v
                spec=maprefs(spec)
                if 'intentFacts' in result:
                    # The immutable source belongs to the old project. Carry its verified selection into the branch.
                    spec.pop('intentDraft',None)
                    spec['forkedIntentResult']=result['resultId']
                else:result=solve(spec)
                if spec.get('intentPlanVersion')==1:
                    from engine.intent import revision_dependencies
                    result['dependencies']=revision_dependencies(spec,result,None)
                c.execute('insert into revision values(?,?,?,?,?,?)',(new,1,'draft',js(spec),js(result),name));audit(c,new,1,name,'fork '+pid);out=dict(id=new)
            elif route=='member':
                allow(role=='admin');need(c.execute('select name from users where name=?',(b['name'],)).fetchone(),'登録済みユーザーを指定してください')
                c.execute('insert or ignore into membership values(?,?)',(pid,b['name']));audit(c,pid,0,name,'member '+b['name']);out={'ok':True}
            elif route=='review':
                allow(role in ('reviewer','admin','designer'));n=b['n'];rr=c.execute('select * from revision where pid=? and n=?',(pid,n)).fetchone();need(rr,'版がありません')
                target=b['state']
                if target=='review':need(rr['state']=='draft','草案を指定してください')
                elif target=='approved':
                    allow(role in ('admin','reviewer') and (not team or name!=rr['author']))
                    need(rr['state']=='review' and json.loads(rr['result'])['status']=='feasible','照査状態・計算結果を確認してください')
                    spec=json.loads(rr['spec']);refs=spec.get('policyRefs',{})
                    if team:need(all(k in refs for k in ('rules','catalog','landscape')),'チーム承認にはルール・カタログ・景観条件の承認版が必要です')
                    if spec.get('importReview') and not spec.get('migrationConfirmed'):raise ValueError('移行した条件・壁面の確認が必要です')
                    need(len(b.get('evidence','').strip())>=4,'ルール・単位・図面・景観条件の承認根拠を記録してください')
                else:raise ValueError('状態が不正です')
                need(c.execute('update revision set state=? where pid=? and n=? and state=?',(target,pid,n,rr['state'])).rowcount,'状態が更新されました')
                audit(c,pid,n,name,target+' '+b.get('evidence','')[:300]);out={'ok':True}
            elif route=='job':
                n=b['n'];kind=b['kind'];args=b.get('args',{});need(kind in ('cg','xlsx','glb','dxf','cadbom'),'形式が不正です')
                rr=c.execute('select state,spec from revision where pid=? and n=?',(pid,n)).fetchone();need(rr,'版がありません')
                if kind=='cg':
                    allow(role in ('admin','designer','sales'));need(rr[0]=='approved' and args.get('team') and args.get('due'),'承認済みの版・宛先・希望納期を指定してください')
                    spec=json.loads(c.execute('select spec from revision where pid=? and n=?',(pid,n)).fetchone()[0])
                    need(set(args.get('assets',[]))<=set(spec.get('assets',[])),'承認版に含まれる素材のみ指定できます')
                    if team:need(args.get('rightsConfirmed') is True,'委託先・素材利用条件を確認してください')
                if args.get('approvedOnly') is True:need(rr['state']=='approved','承認済みの版を選択してください')
                pilot=json.loads(rr['spec']).get('intentPlanVersion')==1
                args=dict(args,exportState=rr[0])
                if kind in ('dxf','xlsx','cadbom'):args['exportVersion']='3.1.0+intent1' if pilot else '3.1.0'
                canon=json.dumps(args,sort_keys=True,ensure_ascii=False)
                c.execute('begin immediate')
                if kind=='cg':
                    old=c.execute("select id from task where pid=? and n=? and kind='cg'",(pid,n)).fetchone()
                else:old=None
                key=old[0] if old else code()
                c.execute('insert or ignore into task(id,pid,n,kind,status,msg,args) values(?,?,?,?,?,?,?)',(key,pid,n,kind,'queued','',canon))
                row=c.execute('select id from task where pid=? and n=? and kind=? and args=?',(pid,n,kind,canon)).fetchone()
                key=old[0] if old else row[0]
                if pilot:
                    artifact_jobs.register(c,key);pilot_jobs_active.set()
                audit(c,pid,n,name,'job '+key);c.commit();pool.submit(run_job,key);out=dict(id=key)
            elif route=='jobStatus':
                job=c.execute('select * from task where id=? and pid=?',(b['id'],pid)).fetchone();need(job,'発注がありません')
                target=b['state'];valid={'queued':['cancelled'],'running':['cancelled'],'failed':['queued'],'cancelled':['queued'],'ready':['accepted'],'accepted':['proof'],'proof':['changes','delivered'],'changes':['proof'],'delivered':['verified']}
                need(target in valid.get(job['status'],[]) and (job['kind']=='cg' or target in ('queued','cancelled')),'状態が更新されました')
                allow(role in ('admin','cg','reviewer','designer'))
                if target=='delivered':
                    info,source=asset(c,pid,b['asset'])
                    need(info['size']>=24,'8K納品画像の寸法を確認してください')
                    with source.open('rb') as stream:header=stream.read(24)
                    need(header[:8]==bytes.fromhex('89504e470d0a1a0a') and max(int.from_bytes(header[16:20],'big'),int.from_bytes(header[20:24],'big'))>=7680,'8K納品は長辺7680px以上のPNGを指定してください')
                if target=='queued' and artifact_jobs.installed(c):
                    c.execute('update artifact_lease set attempts=0,until=0,token=null where id=?',(job['id'],))
                message=job['msg'] if target=='verified' else (b['asset'] if target=='delivered' else '')
                need(c.execute('update task set status=?,msg=? where id=? and status=?',(target,message,job['id'],job['status'])).rowcount,'状態が更新されました')
                audit(c,pid,job['n'],name,'order '+target);c.commit()
                if target=='queued':pool.submit(run_job,job['id'])
                out={'ok':True}
            elif route=='ai':
                allow(role in ('admin','designer','sales'));purpose=b['kind'];need(purpose in ('image','text'),'AI種別が不正です')
                p=b['spec'];need(project['head']>0,'外部送信を許可した版を保存してください')
                saved=json.loads(c.execute('select spec from revision where pid=? and n=?',(pid,project['head'])).fetchone()[0])
                need(saved.get('externalConsent') and p.get('externalConsent'),'現在版の外部送信が許可されていません')
                cfg=config()
                if saved.get('intentPlanVersion') or p.get('intentPlanVersion'):
                    need(purpose=='image','意図計画から承認済みの文章接続先を選択してください')
                    authorized_channel(cfg,purpose,saved)
                    need(b.get('n')==project['head'],'対象版を保存して選び直してください')
                    photo=saved.get('photo',{});rights=photo.get('rights',{})
                    need(isinstance(rights.get('source'),str) and rights['source'].strip() and rights.get('external') is True and
                         photo.get('background') and rights.get('background')==photo['background'] and
                         rights.get('foreground')==photo.get('foreground'),'写真・前景の使用許諾を確認してください')
                    for key in ('photo','model','light','faces','intentDraft','camera'):
                        need(p.get(key)==saved.get(key),'保存版と構図・素材が異なります。新しい版を保存してください')
                out=external(purpose,b['payload'],p,cfg);audit(c,pid,project['head'],name,'gateway '+purpose)
            else:raise ValueError('未知の操作')
            c.commit();self.reply(out)
    def do_GET(self):self.guarded()
    def do_POST(self):self.guarded()
    def guarded(self):
        try:self.run()
        except (BrokenPipeError,ConnectionResetError):pass
        except PermissionError:self.reply({'error':'アクセス権限またはログイン状態をご確認ください'},status=403)
        except FileExistsError as e:self.reply({'error':str(e)},status=409)
        except (ValueError,KeyError,IndexError,TypeError,OverflowError) as e:self.reply({'error':str(e)[:220]},status=422)
        except Exception:self.reply({'error':'処理に失敗しました。データ・接続先を確認してください'},status=500)

def main():
    global DATA
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8081);ap.add_argument('--data',type=Path,default=DATA);ap.add_argument('--open',action='store_true');ap.add_argument('--add-user',nargs=2,metavar=('NAME','ROLE'));ap.add_argument('--backup',type=Path);ap.add_argument('--configure-ai',action='store_true');ap.add_argument('--public-host',help='Approved reverse proxy host with optional port')
    ap.add_argument('--restore',type=Path)
    a=ap.parse_args();DATA=a.data.resolve()
    if a.restore:
        import shutil,tempfile
        need(not DATA.exists(),'復元先は未使用のディレクトリを指定してください')
        DATA.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=DATA.parent) as tmp:
            folder=Path(tmp)/'restore';folder.mkdir()
            with zipfile.ZipFile(a.restore) as z:
                need('made.sqlite' in z.namelist(),'案件DBがありません')
                for info in z.infolist():
                    nm=info.filename
                    need(nm=='made.sqlite' or re.fullmatch(r'(?:files/[a-f0-9]{64}|[a-f0-9]{20}\.bin)',nm),'未知のバックアップ要素')
                    z.extract(info,folder)
            with sqlite3.connect(folder/'made.sqlite') as c:
                need(c.execute('pragma integrity_check').fetchone()[0]=='ok','DBの整合性を確認できません');c.execute('delete from sessions')
                if artifact_jobs.installed(c):
                    for key,sha in c.execute('select id,sha256 from artifact_lease where sha256 is not null'):
                        obj=folder/(key+'.bin')
                        need(obj.is_file() and hashlib.sha256(obj.read_bytes()).hexdigest()==sha,'出力ファイル不整合')
                for sha, in c.execute('select distinct sha from file'):need((folder/'files'/sha).is_file() and hashlib.sha256((folder/'files'/sha).read_bytes()).hexdigest()==sha,'素材ファイル不整合')
            folder.rename(DATA)
        return
    setup(resume=not (a.configure_ai or a.add_user or a.backup))
    if a.configure_ai:
        print('Enter the models approved for this project. Empty entries disable that service.')
        cfg=dict(provider='openai',token=getpass.getpass('OpenAI API key: '),textModel=input('Text model: ').strip(),imageModel=input('Image edit model: ').strip(),approved=input('Contract, account, endpoints and retention verified? type YES: ').strip()=='YES')
        with os.fdopen(os.open(str(DATA/'gateway.json'),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:json.dump(cfg,f)
        return
    if a.add_user:add_user(*a.add_user,getpass.getpass('Password (12+): '));return
    if a.backup:
        # Offline maintenance: archive immutable blobs and a consistent SQLite snapshot.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            snap=Path(d)/'made.sqlite'
            with db() as c,sqlite3.connect(snap) as dest:c.backup(dest)
            with zipfile.ZipFile(a.backup,'x',zipfile.ZIP_DEFLATED) as z:
                z.write(snap,'made.sqlite')
                for f in list((DATA/'files').glob('*'))+list(DATA.glob('*.bin')):z.write(f,str(f.relative_to(DATA)))
        return
    http=PilotHTTPServer(('127.0.0.1',a.port),Handler)
    http.allowed_hosts={'localhost:'+str(a.port),'127.0.0.1:'+str(a.port)}
    if a.public_host:
        with db() as c:need(c.execute('select count(*) from users').fetchone()[0]>0,'外部ホストには組織ユーザーの設定が必要です')
        http.allowed_hosts.add(a.public_host)
    url='http://127.0.0.1:'+str(a.port);print('Marq M.A.D.E.  '+url,flush=True)
    if a.open:threading.Timer(.4,lambda:webbrowser.open(url)).start()
    http.serve_forever()
if __name__=='__main__':main()
