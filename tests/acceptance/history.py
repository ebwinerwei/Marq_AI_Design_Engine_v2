import contextlib, hashlib, io, json, pathlib, subprocess, sys, tempfile, time, urllib.request, zipfile
import argparse
import socket

parser=argparse.ArgumentParser(description='Round-trip approved 3.1.1 snapshots through a disposable V2 database.')
parser.add_argument('archive',type=pathlib.Path)
args=parser.parse_args()
if hashlib.sha256(args.archive.read_bytes()).hexdigest()!='362e9b1e2f4cfd7ca9bd7a7f02eb19ac7a82cb1d68914010ef5ef5ccab9ecb51':
    parser.error('The supplied file is not the verified 3.1.1 archive.')
temp=tempfile.TemporaryDirectory(prefix='marq-historical-')
root=pathlib.Path(temp.name)
with zipfile.ZipFile(args.archive) as source:source.extractall(root)
original=root/'Marq-MADE'
pilot=pathlib.Path(__file__).resolve().parents[2]
@contextlib.contextmanager
def serve(app,data):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    process=subprocess.Popen([sys.executable,'server.py','--port',str(port),'--data',str(data)],cwd=app,stdout=subprocess.PIPE)
    try:
        assert process.stdout.readline().startswith(b'Marq')
        def call(path,body=None,raw=False):
            req=urllib.request.Request(f'http://127.0.0.1:{port}/api/made/v1/'+path,data=json.dumps(body).encode() if body else None,headers={'X-Made-Request':'1'})
            with urllib.request.urlopen(req,timeout=20) as res:return res.read() if raw else json.load(res)
        yield call
    finally:
        process.terminate();process.wait()
def output(call,pid,kind,variant):
    key=call('job',dict(pid=pid,n=1,kind=kind,args=dict(qa=variant)))['id']
    for _ in range(80):
        job=next(j for j in call('project?pid='+pid)['jobs'] if j['id']==key)
        if job['status']=='ready':break
        assert job['status'] in ('queued','running'),job
        time.sleep(.05)
    data=call('download?pid='+pid+'&id='+key,raw=True)
    if kind=='xlsx':
        with zipfile.ZipFile(io.BytesIO(data)) as book:return {p:book.read(p) for p in book.namelist()}
    return data

with serve(original,root/'original') as call:
    pid=call('new',dict(name='既存版'))['id']
    p=dict(name='立面検証',mode='H',rules='p18-baseline',stock='dry',pitch=600,floors=[7200,7200],faces=[dict(id='E',spans=[9000]*6,features=[])])
    call('save',dict(pid=pid,expectedRevision=0,spec=p))
    call('review',dict(pid=pid,n=1,state='review'));call('review',dict(pid=pid,n=1,state='approved',evidence='独立試験'))
    old=call('revision?pid='+pid+'&n=1')
    exported={k:output(call,pid,k,'before') for k in ('dxf','xlsx','glb')}
subprocess.run([sys.executable,'server.py','--data',str(root/'original'),'--backup',str(root/'original.zip')],cwd=original,check=True)
subprocess.run([sys.executable,'server.py','--data',str(root/'restored'),'--restore',str(root/'original.zip')],cwd=pilot,check=True)
with serve(pilot,root/'restored') as call:
    assert call('revision?pid='+pid+'&n=1')==old
    for k,v in exported.items():assert output(call,pid,k,'after')==v,k
    p['intentPlanVersion']=1
    call('save',dict(pid=pid,expectedRevision=1,spec=p))
    p['intentDraft']=call('intent-plan',dict(pid=pid,n=2,faceId='E',goal='twoPeaks'))
    saved=call('save',dict(pid=pid,expectedRevision=2,spec=p))
    key=call('job',dict(pid=pid,n=3,kind='cadbom'))['id']
    for _ in range(80):
        if next(j for j in call('project?pid='+pid)['jobs'] if j['id']==key)['status']=='ready':break
        time.sleep(.05)
    data=call('download?pid='+pid+'&id='+key,raw=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest=json.loads(z.read('manifest.json'));assert manifest['resultId']==saved['resultId'] and manifest['dependencies']['parentRevision']==2
subprocess.run([sys.executable,'server.py','--data',str(root/'restored'),'--backup',str(root/'pilot.zip')],cwd=pilot,check=True)
subprocess.run([sys.executable,'server.py','--data',str(root/'v2-restore'),'--restore',str(root/'pilot.zip')],cwd=pilot,check=True)
with serve(pilot,root/'v2-restore') as call:
    assert call('download?pid='+pid+'&id='+key,raw=True)==data
    assert call('revision?pid='+pid+'&n=1')==old
print('PASS original approved revision',old['result']['resultId'],'DXF/GLB bytes, every Excel XML member, restored pilot artifact',hashlib.sha256(data).hexdigest())
