import unittest,sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_engine import project
from engine.layout import solve,WAVES
from engine.legacy import migrate
from engine.geometry import rect
from engine.procurement import takeoff
class Cases(unittest.TestCase):
    def test_tenant_restarts(self):
        p=project(floors=[27000],spans=[9000]*12);p['tenantTop']=True
        a=solve(p);q=project(floors=[18000],spans=[9000]*12);b=solve(q)
        first={v['panel'].split('.')[1:][0]:v['level'] for v in a['pieces'] if '/2.' in v['panel']}
        expected={v['panel'].split('.')[1:][0]:v['level'] for v in b['pieces'] if '/1.' in v['panel']}
        self.assertEqual(first,expected)
    def test_six_stages(self):
        p=project('V',floors=[6500,7200],spans=[9000]*5);a=p['faces'][0];b=dict(a,id='B',azimuth=-90,origin=[45000,0,0],features=[])
        a['group']=b['group']='AB';p['faces'].append(b);a['features']=[
            dict(kind='logo',corner='right',poly=rect(42000,550,2700,800),clearanceM=550),
            dict(kind='band',poly=rect(5000,6000,13000,800)),dict(kind='smoke',physicalHole=True,poly=rect(6000,5500,700,600)),
            dict(kind='future',poly=rect(4000,3000,900,1300)),dict(kind='equipment',poly=rect(19000,2900,3100,2000)),dict(kind='notch',poly=rect(33000,2400,600,3000)),dict(kind='return',poly=rect(0,0,600,13700))]
        b['features']=[dict(kind='berth',number=2,poly=rect(3400,9000,4200,4000)),dict(kind='ramp',poly=[[0,5800],[3500,5000],[3500,6000],[0,6800]]),dict(kind='slope',poly=[[4000,7000],[8000,8000],[8000,9000],[4000,9000]])]
        p['tenantTop']=True;r=solve(p);self.assertEqual(len(r['faces']),2);self.assertEqual(r['trims'][0]['length'],math.hypot(4000,1000));self.assertIn('Electric Blue',r['faces'][1]['finishes'])
    def test_visible_vs_material(self):
        p=project();p['faces'][0]['features']=[dict(kind='equipment',poly=rect(0,0,3000,4000))]
        a=solve(p)['faces'][0];self.assertAlmostEqual(sum(a['finishes'].values())-sum(a['visible'].values()),12000000)
    def test_group_rules_and_locks(self):
        p=project();p['locks']={'A/1.1.1':'Slate Navy'};p['faces'][0]['limit']=0
        self.assertEqual(solve(p)['status'],'conflict')
        p['faces'].append(dict(id='B',group='A',origin=[0,0,0],spans=[9000],features=[]))
        with self.assertRaises(ValueError):solve(p)
    def test_legacy_masks(self):
        a=dict(version=1,fields=dict(f='6500,7000',w='9000,9000',m='V',s='cs',g='9000',p='750',r='0',v=WAVES[0],b='',t='0',l='corner',z='1',d='300',k='opening,8500,1000,1000,500'))
        p=migrate(a);self.assertTrue(all(f['features'] for f in p['faces']));self.assertIn('importReview',p)
    def test_cutting(self):
        p=project(floors=[750],spans=[9000]);p['fabrication']={'Silver':dict(confirmed=True,maxLength=2300,fold=25,kerf=0,wastePct=0,pack=1)}
        r=solve(p);cuts=takeoff(p,r);self.assertEqual(len(cuts),4);self.assertTrue(all(c['length']<=2300 for c in cuts));self.assertAlmostEqual(sum(c['net'] for c in cuts),6.75)
    def test_sample_color(self):
        p=project();p['landscape']={'colorLimits':{'Silver':{'maxChroma':2}}}
        self.assertEqual(solve(p)['status'],'conflict')
        p['approvedSamples']={'Silver':dict(hue='N',value=7,chroma=0,source='test-swatch')};self.assertEqual(solve(p)['status'],'feasible')
    def test_keep_source_geometry(self):
        p=project(floors=[3000],spans=[3000]);tri=[[0,0],[3000,0],[0,3000]];p['faces'][0]['surfaceTriangles']=[tri,tri]
        a=solve(p)['faces'][0];self.assertAlmostEqual(sum(a['finishes'].values()),4500000)
    def test_multi_span_thresholds(self):
        for n in [10,11,19,20]:
            p=project('wave',spans=[9000]*n);r=solve(p);self.assertEqual(r['status'],'feasible')
    def test_official_and_word_versions(self):
        from engine.layout import pattern
        a=pattern({'rules':'p18-baseline'})['C'];b=pattern({'rules':'word-comparison'})['C']
        self.assertEqual([i for i in range(9) if a[i]!=b[i]],[4,6])
