import io
from itertools import product
import unittest
import zipfile

from engine import intent
from engine.formats import xlsx
from engine.geometry import rect
from engine.layout import solve
from test_rule_baseline import fixture


class IntentPilot(unittest.TestCase):
    def project(self, mode='wave'):
        p=fixture()
        p.update(mode=mode,intentPlanVersion=1)
        return p

    def candidate(self,p,goal='entrance',edit=True):
        d=intent.propose(p,1,'E',goal)
        d['approvedEditable']=['moduleLevels'] if edit else []
        return intent.solve_intent(p,d,solve(p))

    def test_fixed_sequences_and_archived_comparison(self):
        for mode in ['H','V']:
            p=self.project(mode)
            r=self.candidate(p,edit=False)
            self.assertEqual(r['pieces'],solve(p)['pieces'])
            self.assertEqual(r['intentFacts']['limitStatus'],'未設定')
            with zipfile.ZipFile(io.BytesIO(xlsx(p,r,'draft'))) as z:
                self.assertIn('意図案比較'.encode(),z.read('xl/workbook.xml'))
                self.assertIn(r['resultId'].encode(),z.read('xl/worksheets/sheet10.xml'))
            with self.assertRaises(ValueError):
                self.candidate(p)

    def test_changed_area_only_on_selected_face(self):
        p=self.project()
        p['faces'].append(dict(id='N',spans=[9000]*6,features=[]))
        p['faces'][0]['features']=[dict(kind='entrance',poly=rect(400,6000,800,900))]
        base=solve(p)
        results=[self.candidate(p,goal) for goal in intent.PRESETS]
        self.assertNotEqual(results[0]['pieces'],results[1]['pieces'])
        for r in results:
            self.assertEqual([x for x in r['pieces'] if x['face']=='N'],[x for x in base['pieces'] if x['face']=='N'])
            self.assertTrue(r['intentFacts']['changedPanels'])
            self.assertEqual(r['intentFacts']['denominatorMM2'],54000*14400-800*900)
        self.assertEqual(results[0]['resultId'],self.candidate(p)['resultId'])

    def test_missing_zero_empty_and_frozen_conflict(self):
        p=self.project()
        p['faces'][0]['limit']=0
        facts=self.candidate(p)['intentFacts']
        self.assertEqual((facts['accentMM2'],facts['limitStatus']),(0,'上限内'))
        p['locks']={'E/1.1.1':'Slate Navy'}
        with self.assertRaisesRegex(ValueError,'両立'):
            self.candidate(p)
        p['faces'][0]['features']=[dict(kind='opening',poly=rect(0,0,54000,14400))]
        facts=self.candidate(p)['intentFacts']
        self.assertEqual((facts['denominatorMM2'],facts['limitStatus']),(0,'対象なし'))

    def test_scope_references_and_limits(self):
        p=self.project()
        p['faces'][0]['features']=[dict(kind='entrance',poly=rect(1,1,500,500))]
        original=intent.propose(p,1,'E','entrance')
        for key,value in [('anchors',['invented']),('quietIntervals',[dict(start=.3,end=.3)]),
                          ('peaks',[dict(center=.5,width=0,strength=1)]),('peaks',['bad']),
                          ('priority','overwrite'),('unknownField',True)]:
            d=dict(original,**{key:value})
            with self.assertRaises(ValueError):
                intent.solve_intent(p,d,solve(p))
        del p['faces'][0]['features'][:]
        with self.assertRaises(ValueError):
            intent.solve_intent(p,original,solve(p))
        d=intent.propose(p,1,'E','twoPeaks');d['approvedEditable']=['moduleLevels']
        d['quietIntervals']=[dict(start=0,end=.001)]
        with self.assertRaisesRegex(ValueError,'余白'):
            intent.solve_intent(p,d,solve(p))

    def test_bounded_optimizer_against_exhaustive_oracle(self):
        options=[[(0,3,12),(3,2,9),(8,0,0)],[(0,3,14),(2,4,7),(8,0,0)],
                 [(0,3,14),(4,2,6),(7,0,0)],[(0,3,12),(4,4,6),(7,0,0)]]
        for limit in [0,13,27,39,50,100]:
            for cols in [0,2]:
                chosen,state=intent.choose(options,limit,100,500,cols)
                feasible=[v for v in product(*options) if sum(q[2] for q in v)<=limit
                          and not any(cols and i>=cols and q[1]>=2 and q[1]==v[i-cols][1] for i,q in enumerate(v))]
                self.assertEqual(state,'optimal')
                chosenCost=sum(next(q[0] for q in row if q[1]==n) for row,n in zip(options,chosen))
                self.assertEqual(chosenCost,min(sum(q[0] for q in v) for v in feasible))
        self.assertEqual(intent.choose(options,20,100,0)[1],'budgetFeasible')
        impossible=[[(0,3,1)],[(0,3,1)]]
        self.assertEqual(intent.choose(impossible,100,2,0,1),(None,'incomplete'))
        self.assertEqual(intent.choose(impossible,100,2,10,1),(None,'conflict'))

    def test_dxf_and_excel_independently_measure_cut_panels(self):
        from collections import Counter
        from xml.etree import ElementTree as ET
        from engine.formats import dxf
        p=self.project('H')
        p['faces'][0]['features']=[dict(kind='opening',poly=rect(18000,1800,4500,600))]
        r=self.candidate(p,edit=False)
        lines=dxf(p,r,'draft').decode('ascii').splitlines()
        entities=[];entity={}
        for code,value in zip(lines[::2],lines[1::2]):
            if code=='0':
                entities.append(entity);entity={}
            entity[code]=value
        areas=Counter()
        for e in entities:
            if e.get('0')=='SOLID':
                x,y,X,Y,u,v=(float(e[k]) for k in ('10','20','11','21','12','22'))
                areas[e['8']]+=abs((X-x)*(v-y)-(Y-y)*(u-x))/2
        self.assertEqual(areas,{'FIN_Silver':648000000,'FIN_Slate_Navy':126900000})
        self.assertTrue({'OPENING','WALL','PANEL','DIM'}<={e.get('8') for e in entities})
        self.assertIn(b'DRAFT / DESIGN COORDINATION ONLY',dxf(p,r,'draft'))
        self.assertNotIn(b'DRAFT / DESIGN COORDINATION ONLY',dxf(p,r,'approved'))
        with zipfile.ZipFile(io.BytesIO(xlsx(p,r,'draft'))) as z:
            rows=ET.fromstring(z.read('xl/worksheets/sheet3.xml')).findall('.//{*}row')
            totals=Counter()
            for row in rows[1:]:
                cells=list(row)
                totals[cells[4].find('.//{*}t').text]+=float(cells[5].find('{*}v').text)
            self.assertAlmostEqual(totals['Silver'],648)
            self.assertAlmostEqual(totals['Slate Navy'],126.9)
