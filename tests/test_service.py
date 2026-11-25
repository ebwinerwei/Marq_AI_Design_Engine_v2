import io,json,sys,tempfile,time,threading,urllib.request,urllib.error,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from test_engine import project
class Service(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();server.DATA=Path(cls.tmp.name);server.setup()
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        host='127.0.0.1:'+str(cls.http.server_address[1]);cls.http.allowed_hosts={host};cls.url='http://'+host+server.PREFIX
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join();cls.tmp.cleanup()
    def call(self,route,b=None,raw=False):
        req=urllib.request.Request(self.url+route,data=json.dumps(b).encode() if b is not None else None,headers={'X-Made-Request':'1','Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:
            return r.read() if raw else json.load(r)
    def test_project_lifecycle(self):
        pid=self.call('new',{'name':'Test'})['id'];p=project();result=self.call('solve',{'spec':p})
        saved=self.call('save',dict(pid=pid,spec=p,expectedRevision=0));self.assertEqual(result['resultId'],saved['resultId'])
        with self.assertRaises(urllib.error.HTTPError) as conflict:self.call('save',dict(pid=pid,spec=p,expectedRevision=0))
        self.assertEqual(conflict.exception.code,409)
        self.call('review',dict(pid=pid,n=1,state='review'));self.call('review',dict(pid=pid,n=1,state='approved',evidence='基準図照合テスト'))
        for kind in ('dxf','glb','xlsx','cadbom','cg'):
            args=dict(team='CG',due='2030-01-05') if kind=='cg' else {}
            payload=dict(pid=pid,n=1,kind=kind,args=args)
            jid=self.call('job',payload)['id'];self.assertEqual(jid,self.call('job',payload)['id'])
            for _ in range(100):
                jobs=self.call('project?pid='+pid)['jobs'];j=next(t for t in jobs if t['id']==jid)
                if j['status'] not in ('queued','running'):break
                time.sleep(.03)
            self.assertEqual(j['status'],'ready',j['msg']);raw=self.call('download?pid='+pid+'&id='+jid,raw=True)
            if kind=='cadbom':
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    self.assertEqual(set(z.namelist()),{'drawing.dxf','materials.xlsx','manifest.json'})
                    self.assertIn(result['resultId'].encode(),z.read('drawing.dxf'))
                    with zipfile.ZipFile(io.BytesIO(z.read('materials.xlsx'))) as book:
                        self.assertIn(result['resultId'].encode(),book.read('xl/worksheets/sheet1.xml'))
            if kind=='cg':self.assertIn('layout.json',zipfile.ZipFile(io.BytesIO(raw)).namelist())
            if kind=='glb':self.assertEqual(raw[:4],b'glTF')
            if kind=='xlsx':self.assertTrue(zipfile.is_zipfile(io.BytesIO(raw)))
        self.assertEqual(self.call('revision?pid='+pid+'&n=1')['result']['resultId'],saved['resultId'])
        with self.assertRaises(urllib.error.HTTPError):self.call('ai',dict(pid=pid,spec=p,kind='image',payload={}))
