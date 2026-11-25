"""Independent oracles from V2 §3 (G18/G20) and the unmodified 3.1.1 A4 run."""
import hashlib
import io
import re
import unittest
import zipfile
from pathlib import Path

from engine.formats import dxf, glb, xlsx
from engine.geometry import rect
from engine.layout import RULE, digest, solve


def fixture():
    return dict(name="立面検証", mode="H", rules="p18-baseline", stock="dry", pitch=600,
                floors=[7200, 7200], faces=[dict(id="E", spans=[9000]*6, features=[])])


class ReleasedRules(unittest.TestCase):
    def test_all_patterns_against_confirmed_document(self):
        path = Path(__file__).resolve().parents[1] / "docs/Marq_MADE_Codex_Build_CN_v2.md"
        rows = re.findall(r'^\| ([0-8]) \| ([01]+|—) \| ([01]+|—) \| ([01]+) \|$', path.read_text(), re.M)
        self.assertEqual(len(rows), 9)
        for i, kind in enumerate("ABC", 1):
            self.assertEqual([''.join(map(str, bits)) for bits in RULE['bits'][kind]],
                             [row[i] for row in rows if row[i] != '—'])

    def test_sequence_hash_and_wrap(self):
        for mode, length, fingerprint in [
            ('H', 329, '7aad473c28ef48dd89b8ac48090098873a68d7cbcd23c2063a53b67f4314051d'),
            ('V', 265, '8d73887d152a19f29d89b7f8280c42816854c33ed3baacde0a8f632b6ca946ed')
        ]:
            seq = RULE['seq'][int(mode == 'V')]
            self.assertEqual((len(seq), hashlib.sha256(seq.encode('ascii')).hexdigest()), (length, fingerprint))
            p = fixture()
            p.update(mode=mode, floors=[7200], scan='right')
            p['faces'][0]['spans'] = [9000] * (length + 2)
            pieces = solve(p)['pieces']
            for piece in pieces:
                row, col, _ = map(int, piece['panel'].split('/')[1].split('.'))
                self.assertEqual(row, 1)
                self.assertEqual(piece['level'], int(seq[(col-1) % length]))
            self.assertGreater(pieces[0]['poly'][0][0], pieces[-1]['poly'][0][0])

    def test_released_snapshot_and_exports(self):
        p = fixture()
        for opened, navy, count, rid, geometry in [
            (False,129600000,288,'b062b58b179a63c4135fd663','df2bfe3de27fcebd70d53a7cf5ef9bea0dacd7c4bc5abb109e62efa3b2fe0f2e'),
            (True,126900000,287,'2a3a7764ba6ff617fab18125','09fe380947835ebcf4a36c6296a066b18316a20aa19409d54798b7dae9141447')
        ]:
            if opened:
                p['faces'][0]['features'] = [dict(kind='opening', poly=rect(18000,1800,4500,600))]
            r = solve(p)
            self.assertEqual((r['resultId'],digest(r['pieces'])), (rid,geometry))
            cells = {v['panel'].split('/')[1].rsplit('.',1)[0]:v['level'] for v in r['pieces']}
            self.assertEqual(''.join(str(cells[f'1.{c}']) for c in range(1,13)), '000034565452')
            self.assertEqual(cells['2.1'], 3)
            self.assertEqual(r['faces'][0]['finishes'],{'Silver':648000000,'Slate Navy':navy})
            self.assertEqual(r['faces'][0]['panels'],count)
            self.assertIn(b'$INSUNITS', dxf(p,r,'draft'))
            self.assertEqual(glb(p,r)[:4],b'glTF')
            with zipfile.ZipFile(io.BytesIO(xlsx(p,r,'draft'))) as workbook:
                self.assertIn(rid.encode(),workbook.read('xl/worksheets/sheet1.xml'))

    def test_horizontal_half_span_boundaries_and_terminal_vertical_cut(self):
        for pitch, kind, courses in [(600,'A',12),(750,'A',12),(751,'B',8),(900,'B',8)]:
            p=fixture()
            p.update(pitch=pitch,floors=[9001])
            p['faces'][0]['spans']=[8000,10000]
            r=solve(p)
            self.assertEqual(r['type'],kind)
            spans=[(0,4000),(4000,8000),(8000,13000),(13000,18000)]
            for q in r['pieces']:
                row,col,k=map(int,q['panel'].split('/')[1].split('.'))
                lo,hi=spans[col-1]
                top=((row-1)*courses+k-1)*pitch
                self.assertEqual(q['poly'],rect(lo,top,hi-lo,min(9001-top,pitch)))
        p=fixture()
        p.update(mode='V',floors=[5100,6900])
        p['faces'][0]['spans']=[9300]
        r=solve(p)
        for q in r['pieces']:
            row,col,k=map(int,q['panel'].split('/')[1].split('.'))
            x=((col-1)*15+k-1)*600
            self.assertEqual(q['poly'],rect(x,0 if row==1 else 6900,min(600,9300-x),6900 if row==1 else 5100))
