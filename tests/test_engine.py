import copy,io,json,struct,unittest,zipfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.layout import calculate,solve,WAVES,RULE
from engine.formats import dxf,xlsx,glb
from engine.geometry import rect
def project(mode='H',floors=None,spans=None):
    return dict(name='受入試験',rules='p18-baseline',mode=mode,stock='dry',pitch=750,floors=floors or [6500,7100,8300],faces=[dict(id='A',spans=spans or [9000,7200,9000],origin=[0,0,0],azimuth=0,features=[])])
class Industrial(unittest.TestCase):
    def test_sequences_modules(self):
        self.assertEqual(list(map(len,RULE['seq'])),[329,265])
        for h,typ in [(600,'A'),(750,'A'),(751,'B'),(900,'B')]:
            p=project();p['pitch']=h;r=solve(p);self.assertEqual(r['type'],typ)
            self.assertAlmostEqual(sum(r['faces'][0]['finishes'].values()),25200*21900)
    def test_all_floor_counts(self):
        for n in [1,2,3,4,5,6,8,11]:
            p=project('V',list(range(6000,6000+n)));r=solve(p)
            self.assertEqual(r['type'],'C');self.assertAlmostEqual(sum(r['faces'][0]['finishes'].values()),25200*sum(p['floors']))
    def test_extreme(self):
        p=project(spans=[9000]*331);p['tenantTop']=True
        r=calculate(p,0);self.assertTrue(all(a['finish']=='Silver' for a in r['pieces'] if '/1.' in a['panel']))
    def test_wave(self):
        for wave in WAVES:
            p=project('wave');p['wave']=wave
            a=solve(p);self.assertEqual(a['resultId'],solve(p)['resultId'])
        p['wave']='25252525'
        with self.assertRaises(ValueError):solve(p)
    def test_real_areas(self):
        p=project();f=p['faces'][0];f['features']=[{'kind':'opening','poly':rect(100,100,1000,500)}]*2
        r=solve(p);self.assertAlmostEqual(sum(r['faces'][0]['finishes'].values()),25200*21900-500000)
    def test_band(self):
        p=project('V');p['faces'][0]['features']=[dict(kind='band',poly=rect(50,7400,4200,500))]
        r=solve(p);self.assertAlmostEqual(sum(r['faces'][0]['finishes'].values()),25200*21900-4200*500)
    def test_polygon(self):
        p=project();p['faces'][0]['outline']=[[0,0],[10000,0],[10000,5000],[5000,5000],[5000,10000],[0,10000]]
        self.assertAlmostEqual(sum(solve(p)['faces'][0]['finishes'].values()),75000000)
    def test_budget(self):
        p=project();p['budget']=5;self.assertEqual(solve(p)['status'],'conflict')
        p['prices']={k:1 for k in ['Silver','Slate Navy']};p['budget']=10000
        self.assertEqual(solve(p)['status'],'feasible')
    def test_stock_ramp_and_formats(self):
        for mode in ['H','V']:
            for stock in ['dry','cs']:
                p=project(mode);p['stock']=stock;p['faces'][0]['features']=[dict(kind='ramp',poly=rect(0,0,9000,1000)),dict(kind='berth',number=1,poly=rect(2500,15000,4000,3000))]
                r=solve(p);self.assertAlmostEqual(r['faces'][0]['finishes']['Electric Blue'],1530000)
                self.assertIn(b'SOLID',dxf(p,r,'draft'));self.assertIn('xl/worksheets/sheet6.xml',zipfile.ZipFile(io.BytesIO(xlsx(p,r,'draft'))).namelist())
                data=glb(p,r);self.assertEqual(data[:4],b'glTF');self.assertEqual(struct.unpack_from('<I',data,8)[0],len(data))
