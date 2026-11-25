import unittest
from test_engine import project
from engine.layout import solve,prepared
from engine.geometry import rect,bounds
from engine.procurement import takeoff
from engine.policy import normalize

class FieldRelease(unittest.TestCase):
    def test_corner_width_uses_actual_spans(self):
        p=project(spans=[8000,10000,12000])
        f=p['faces'][0]
        for corner,width in [('left',18000),('right',22000)]:
            f['features']=[dict(kind='logo',corner=corner,poly=rect(500,500,1000,500))]
            e,_,_=prepared(f,'A',p,21900,9000,4000,[8300,7100,6500])
            l,_,r,_=bounds(e[0][1]);self.assertEqual(r-l,width)

    def test_duplicate_face_across_groups(self):
        p=project();p['faces'].append(dict(p['faces'][0],group='other'))
        with self.assertRaisesRegex(ValueError,'一意'):solve(p)

    def test_band_mode(self):
        p=project('V',floors=[6000,6000],spans=[9000])
        f=p['faces'][0];f['features']=[dict(kind='band',poly=rect(0,5000,3000,500))]
        for shifted,expected in [(False,6000),(True,5000)]:
            if shifted:f['features'][0]['shift']=True
            r=solve(p);self.assertAlmostEqual(sum(r['faces'][0]['finishes'].values()),106500000)
            a=[bounds(v['poly'])[3] for v in r['pieces'] if v['panel']=='A/1.1.1']
            self.assertEqual(max(a),expected)

    def test_cut_separated_by_opening(self):
        p=project(floors=[750],spans=[9000]);p['faces'][0]['features']=[dict(kind='opening',poly=rect(1000,0,1000,750))]
        cuts=takeoff(p,solve(p));self.assertEqual(sorted(v['length'] for v in cuts),[1000,2500,4500])
        self.assertAlmostEqual(sum(v['stockArea'] for v in cuts),6)

    def test_region_sequence(self):
        p=project('wave',floors=[7000],spans=[11250]*11);p.update(blankCols=[0,4,8],waveSequence=['234567','654323456'])
        r=solve(p);level={v['panel']:v['level'] for v in r['pieces']}
        self.assertEqual([level['A/1.%s.1'%i] for i in (2,6,10)],[2,6,2])
        self.assertEqual(r['resultId'],solve(p)['resultId'])

    def test_adjacent_corner(self):
        p=project(spans=[9000]);f=p['faces'][0]
        f['features']=[dict(kind='logo',corner='right',poly=rect(7700,800,800,400))]
        p['faces'].append(dict(id='B',origin=[9000,0,0],azimuth=-90,spans=[7000,11000,6000],features=[]))
        self.assertEqual(bounds(normalize(p)['faces'][1]['features'][0]['poly'])[2],18000)

    def test_new_release_does_not_inherit_budget_or_limits(self):
        p=project();p['budget']=0
        self.assertIn('見積単価未登録',solve(p)['issues'])
        del p['budget'];self.assertEqual(solve(p)['status'],'feasible')
