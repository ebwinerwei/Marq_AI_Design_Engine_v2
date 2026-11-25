import http.cookiejar,unittest,urllib.request,urllib.error,threading,tempfile,time,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from test_engine import project
class Team(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();server.DATA=Path(self.tmp.name);server.setup()
        for name,role in [('d','designer'),('r','reviewer'),('a','admin'),('s','sales')]:server.add_user(name,role,'test-local-account')
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);h='127.0.0.1:'+str(self.http.server_address[1]);self.http.allowed_hosts={h};self.url='http://'+h+server.PREFIX
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.agents={n:urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())) for n in 'adrs'}
        for n in self.agents:self.call(n,'login',{'name':n,'password':'test-local-account'})
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.tmp.cleanup()
    def call(self,who,url,b=None):
        req=urllib.request.Request(self.url+url,data=json.dumps(b).encode() if b is not None else None,headers={'X-Made-Request':'1'})
        return json.load(self.agents[who].open(req))
    def test_review_and_visibility(self):
        pid=self.call('d','new',{'name':'project'})['id'];self.assertEqual(self.call('s','projects'),[])
        with self.assertRaises(urllib.error.HTTPError):self.call('s','project?pid='+pid)
        self.call('a','member',dict(pid=pid,name='r'))
        p=project();p['policyRefs']={}
        for kind,values in [('rules',{'bitsVersion':'p18-baseline'}),('catalog',{'products':{},'prices':{}}),('landscape',{'limit':None,'denominator':'net'})]:
            vals=dict(version='1',source='verified test',**values)
            key=self.call('a','policy',dict(type=kind,contents=vals))['id']
            with self.assertRaises(urllib.error.HTTPError):self.call('a','policy',dict(action='publish',id=key,evidence='self'))
            self.call('r','policy',dict(action='publish',id=key,evidence='fixture'));p['policyRefs'][kind]=key
            if kind=='landscape':p['landscape']=vals
        self.call('d','save',dict(pid=pid,expectedRevision=0,spec=p));self.call('d','review',dict(pid=pid,n=1,state='review'))
        self.call('r','review',dict(pid=pid,n=1,state='approved',evidence='verified test'))
        self.assertEqual(self.call('r','revision?pid='+pid+'&n=1')['state'],'approved')
        self.call('d','logout',{})
        with self.assertRaises(urllib.error.HTTPError):self.call('d','projects')

    def test_catalog_shape_and_project_binding(self):
        bad={'version':'A','source':'確認用','products':{'Silver':['1']},'prices':{}}
        with self.assertRaises(urllib.error.HTTPError):
            self.call('a','policy',dict(type='catalog',contents=bad))
        pid=self.call('d','new',{'name':'project'})['id']
        catalog=dict(version='B',source='基準図',products={},prices={},fabrication={'Silver':{'confirmed':False}})
        key=self.call('a','policy',dict(type='catalog',contents=catalog))['id']
        self.call('r','policy',dict(action='publish',id=key,evidence='図番確認'))
        p=project();p['policyRefs']={'catalog':key}
        with self.assertRaises(urllib.error.HTTPError):
            self.call('d','save',dict(pid=pid,expectedRevision=0,spec=p))
        p['fabrication']=catalog['fabrication']
        self.assertEqual(self.call('d','save',dict(pid=pid,expectedRevision=0,spec=p))['n'],1)
        result=self.call('d','patterns')
        self.assertEqual(len(result['sequence'][0]),329)
        self.assertNotEqual(result['baseline']['C'][4],result['proposal']['C'][4])
