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

    def test_intent_scoped_revision_replay_and_handoff(self):
        from unittest.mock import patch
        p=project('wave',floors=[6000,7000],spans=[9000]*6)
        pid=self.call('new',{'name':p['name']})['id']
        other=self.call('new',{'name':'別案件'})['id']
        def save(n):
            return self.call('save',dict(pid=pid,expectedRevision=n,spec=p))
        old=save(0)
        p['intentPlanVersion']=1
        self.assertEqual(save(1)['resultId'],old['resultId'])
        draft=self.call('intent-plan',dict(pid=pid,n=2,faceId='A',goal='twoPeaks'))
        draft['approvedEditable']=['moduleLevels']
        p['intentDraft']=draft
        with self.assertRaises(urllib.error.HTTPError):
            self.call('solve',dict(pid=other,spec=p))
        with self.assertRaises(urllib.error.HTTPError):
            self.call('job',dict(pid=pid,n=2,kind='xlsx',args={'approvedOnly':True}))
        candidate=self.call('solve',dict(pid=pid,spec=p))
        self.assertEqual(save(2)['resultId'],candidate['resultId'])
        p['light']={'sky':'dusk'}
        with patch('engine.intent.solve_intent',side_effect=AssertionError('archived selection was recomputed')):
            self.assertEqual(save(3)['resultId'],candidate['resultId'])
        branch=self.call('fork',dict(pid=pid,n=3,name='分岐'))['id']
        archived=self.call('revision?pid='+branch+'&n=1')
        self.assertEqual(archived['result']['pieces'],candidate['pieces'])
        self.assertIsNone(archived['result']['dependencies']['parentRevision'])
        self.assertEqual(self.call('solve',dict(pid=branch,spec=archived['spec'])),archived['result'])
        self.assertEqual(self.call('revision?pid='+pid+'&n=1')['result']['resultId'],old['resultId'])
        p['faces'][0]['spans'][0]+=500
        with self.assertRaises(urllib.error.HTTPError) as stale:
            save(4)
        self.assertEqual(stale.exception.code,422)
        self.assertEqual(self.call('project?pid='+pid)['project']['head'],4)

    def test_pilot_external_suggestions_are_bounded_and_require_saved_grant(self):
        from unittest.mock import patch
        record=dict(account='QA',model='mock',endpoint='https://example.invalid/text',contract='fixture',
                    region='test',retention='test',sampleTest='local',expires='2099-01-01')
        cfg=dict(approved=True,textModel='mock',textUrl=record['endpoint'],verifiedChannels={'text':record})
        pid=self.call('new',{'name':'fixture'})['id']
        p=project();p.update(intentPlanVersion=1,externalConsent=True)
        with patch('server.config',return_value=cfg),patch('server.external') as send:
            p['channelGrants']={'text':self.call('pilot-channels',dict(pid=pid))['text']['id']}
            self.call('save',dict(pid=pid,expectedRevision=0,spec=p))
            payload=dict(pid=pid,n=1,faceId='A',goal='twoPeaks',via='text')
            send.return_value={'quietIntervals':[],'peaks':[dict(center=.3,width=.2,strength=.5)]}
            draft=self.call('intent-plan',payload)
            self.assertEqual(draft['approvedEditable'],[])
            self.assertEqual(set(send.call_args.args[1]),{'task','goal','observer','quietIntervals','peaks'})
            send.return_value={'mode':'wave'}
            with self.assertRaises(urllib.error.HTTPError):self.call('intent-plan',payload)
            send.reset_mock()
            p['externalConsent']=False
            self.call('save',dict(pid=pid,expectedRevision=1,spec=p))
            for n in (1,2):
                with self.assertRaises(urllib.error.HTTPError):self.call('intent-plan',dict(payload,n=n))
            send.assert_not_called()
