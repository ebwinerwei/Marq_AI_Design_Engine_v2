"""Local V1 pilot. Only a designer-confirmed, independent wave elevation may change."""
from collections import defaultdict
from fractions import Fraction
from itertools import accumulate
import math

from .geometry import area, bounds
from .layout import RULE, calculate, calculate_groups, digest, finish_solution
from .policy import normalize

VERSION = 1
RULE_HASH = digest(RULE)
MAX_CELLS = 96
NODE_BUDGET = 25000
PRESETS = ('entrance', 'twoPeaks')
FIELDS = {'revisionId', 'faceId', 'observer', 'goal', 'approvedEditable', 'anchors',
          'quietIntervals', 'peaks', 'layerBias', 'priority', 'evidenceRefs', 'strictLayers'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def enabled(spec):
    version = spec.get('intentPlanVersion')
    require(version is None or (type(version) is int and version == VERSION), '意図計画の版を確認してください')
    return version is not None


def geometry_input(p):
    keys = ('rules','mode','stock','pitch','floors','faces','locks','seed','scan','wave',
            'waveSequence','tenantTop','mirrorBits','prices','budget','limit','catalog','fabrication',
            'policyRefs','blankCols','landscape','approvedSamples')
    data = {k:p[k] for k in keys if k in p}
    data['faces'] = [dict(f, parapet=f.get('parapet',0), limit=f.get('limit',p.get('limit'))) for f in p['faces']]
    return digest(data)


def face_for(p, fid):
    f = next((f for f in p['faces'] if f['id'] == fid), None)
    require(f is not None, '対象立面を選び直してください')
    return f


def anchor_features(face):
    return {f"{i+1}-{digest(feat)[:16]}":feat for i,feat in enumerate(face.get('features',[]))
            if feat['kind'] in ('entrance','logo')}


def propose(spec, revision, fid, goal):
    require(enabled(spec) and goal in PRESETS, '案件の意図計画と目的を選択してください')
    face = face_for(spec, fid)
    features = anchor_features(face)
    anchor = next((k for k,v in features.items() if v['kind']=='entrance'), None)
    center = .5
    if anchor:
        left,_,right,_ = bounds(features[anchor]['poly'])
        center = (left+right)/(2*sum(face['spans']))
    half = min(.5, max(.12, 7.5*spec['pitch']/sum(face['spans'])))
    return dict(revisionId=revision,faceId=fid,observer='street',goal=goal,approvedEditable=[],
                anchors=[anchor] if anchor and goal=='entrance' else [],
                quietIntervals=[dict(start=max(0,center-half),end=min(1,center+half))] if goal=='entrance' else [],
                peaks=[dict(center=c,width=.14,strength=.7) for c in ([.22,.78] if goal=='entrance' else [.35,.85])],
                layerBias=.25,strictLayers=False,priority='area',evidenceRefs=['G18','G20'] if spec['mode']!='wave' else ['G18','V1–V3'])


def unit(v):
    return type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 1


def validate(p,d):
    require(isinstance(d,dict) and set(d)==FIELDS, '意図計画の項目を確認してください')
    f = face_for(p,d['faceId'])
    require(type(d['revisionId']) is int and d['revisionId']>0 and d['observer']=='street'
            and type(d['strictLayers']) is bool and d['goal'] in PRESETS and d['priority']=='area' and unit(d['layerBias']), '版・視点・目的を確認してください')
    require(d['approvedEditable'] in ([],['moduleLevels']) and
            (p['mode']=='wave' or not d['approvedEditable']), '指定配列は固定です')
    require(not d['strictLayers'] or d['approvedEditable'], '層間条件には番手変更の許可が必要です')
    require(d['evidenceRefs']==(['G18','V1–V3'] if p['mode']=='wave' else ['G18','G20']), '参照資料を確認してください')
    require(isinstance(d['anchors'],list) and len(d['anchors'])<=4 and
            all(isinstance(a,str) and a in anchor_features(f) for a in d['anchors']), '入口・ロゴが変更されました')
    for name,keys in [('peaks',{'center','width','strength'}),('quietIntervals',{'start','end'})]:
        entries=d[name]
        require(isinstance(entries,list) and len(entries)<=4, '範囲は各4件までです')
        for e in entries:
            require(isinstance(e,dict) and set(e)==keys and all(unit(v) for v in e.values()), '位置・幅を確認してください')
            require(e['width']>0 if name=='peaks' else e['start']<e['end'], '正の幅が必要です')
    return f


def build_target(d,u,k,floors):
    if any(q['start'] <= u <= q['end'] for q in d['quietIntervals']):
        return 0
    bias = d['layerBias']*(k/(floors-1) if floors>1 else 0)
    density = bias + sum(v['strength']*math.exp(-.5*((u-v['center'])/max(v['width'],1e-9))**2) for v in d['peaks'])
    return round(10000*min(1,density))


def grid_for(p,f):
    width=sum(f['spans'])
    columns=math.ceil(width/(15*p['pitch']))
    floors=len(f.get('floors',p['floors']))
    require(columns*floors<=MAX_CELLS,'意図試算は1面96モジュールまでです。対象範囲を確認してください')
    reverse=p.get('scan')=='right' or (p.get('scan','auto')=='auto' and any(
        a.get('corner')=='right' and a['kind']=='logo' for a in f.get('features',[])))
    centers=[(i*15*p['pitch']+min(width,(i+1)*15*p['pitch']))/(2*width) for i in range(columns)]
    return [1-v for v in centers] if reverse else centers, floors


def accent(p):
    return 'Slate Navy' if p['stock']=='dry' else 'White'


def evaluate_option(p,f,rows,cols,n,seed):
    """Use the original cutter for each selectable pattern, including holes, locks and silver overrides."""
    result=calculate(dict(p,faces=[f]),seed,[[n]*cols for _ in range(rows)])
    quantities=defaultdict(lambda:[0,0])
    visible=f.get('denominator','net')=='visible'
    for piece in result['pieces']:
        if visible and piece['hidden']:
            continue
        row,col,_=map(int,piece['panel'].rsplit('/',1)[1].split('.'))
        q=quantities[row-1,col-1]
        q[1]+=piece['area']
        if piece['finish']==accent(p):
            q[0]+=piece['area']
    return quantities


def choose(options,limit,denominator,budget,columns=0):
    """Bounded deterministic search. Columns enables the signed-off V3 adjacent-layer constraint."""
    cap=None if limit is None else Fraction(str(limit))*denominator/100
    options=[sorted(row) for row in options]
    def compatible(i,q,path):
        if not columns or i<columns:
            return True
        above=path[i-columns]
        return not (q[1]>=2 and q[1]==above[1] and q[2]>0 and above[2]>0)
    def feasible(path):
        return (cap is None or sum(q[2] for q in path)<=cap) and all(compatible(i,q,path) for i,q in enumerate(path))
    first=[row[0] for row in options]
    if feasible(first):
        return [q[1] for q in first],'optimal'
    least=[min(row,key=lambda q:(q[2],q[0],q[1])) for row in options]
    if cap is not None and sum(q[2] for q in least)>cap:
        return None,'conflict'
    best=[q[1] for q in least] if feasible(least) else None
    score=sum(q[0] for q in least) if best is not None else math.inf
    min_cost=list(reversed(list(accumulate((row[0][0] for row in reversed(options)),initial=0))))
    min_area=list(reversed(list(accumulate((q[2] for q in reversed(least)),initial=0))))
    remaining=budget
    def visit(i,cost,used,path):
        nonlocal best,score,remaining
        if remaining<=0 or cost+min_cost[i]>=score or (cap is not None and used+min_area[i]>cap):
            return
        remaining-=1
        if i==len(options):
            best=[q[1] for q in path];score=cost
            return
        for q in options[i]:
            if compatible(i,q,path):
                visit(i+1,cost+q[0],used+q[2],path+[q])
    visit(0,0,0,[])
    if remaining:
        return best,'optimal' if best is not None else 'conflict'
    return best,'budgetFeasible' if best is not None else 'incomplete'


def measures(p,f,pieces):
    selected=[x for x in pieces if x['face']==f['id'] and (f.get('denominator')!='visible' or not x['hidden'])]
    den=sum(area(x['poly']) for x in selected)
    a=sum(area(x['poly']) for x in selected if x['finish']==accent(p))
    return a,den


def validate_candidate(p,f,d,base,result,grid):
    fid=f['id']
    limit=f.get('limit',p.get('limit'))
    a,den=measures(p,f,result['pieces'])
    from .layout import pattern
    bits=pattern(p)['C']
    old={q['id']:q for q in base['pieces']}
    changed=set()
    for q in result['pieces']:
        original=old.get(q['id'])
        require(original is not None and q['poly']==original['poly'], '裁片の範囲が変わっています')
        if q['face']!=fid or grid is None:
            require(q==original,'固定範囲に変更があります')
        if q['face']==fid and grid is not None:
            row,col,k=map(int,q['panel'].rsplit('/',1)[1].split('.'))
            level=grid[row-1][col-1]
            require(q['level']==level,'選定番手の照合に失敗しました')
            if all(t in ('P18.C','V31-33','P19.clip','P23.equipment') for t in q['trace']):
                expected=accent(p) if bits[level][k-1] else 'Silver'
                expected=p.get('locks',{}).get(q['panel'],expected)
                require(q['finish']==expected,'原板の番手と仕上が一致しません')
        if q['panel'] in p.get('locks',{}) and q['finish']!=p['locks'][q['panel']]:
            message=q['panel']+'：固定色と被覆が競合します'
            if message not in result['issues']: result['issues'].append(message)
        if q['finish']!=original['finish']:changed.add(q['panel'])
    require(len(old)==len(result['pieces']), '裁片数を照合してください')
    if den and limit is not None and Fraction(str(a))*100>Fraction(str(limit))*Fraction(str(den)):
        result['issues'].append(fid+'：確定面積が上限を超えています')
    summary=next(x for x in result['faces'] if x['face']==fid)
    require(math.isclose(summary['ratio'],100*a/den if den else 0,abs_tol=1e-8),'面積集計が一致しません')
    if result['issues']:result['status']='conflict'
    if grid and d['strictLayers']:
        active=set()
        for q in result['pieces']:
            if q['face']==fid and q['finish']==accent(p) and (f.get('denominator')!='visible' or not q['hidden']):
                row,col,_=map(int,q['panel'].rsplit('/',1)[1].split('.'))
                active.add((row-1,col-1))
        for row,col in active:
            if (row-1,col) in active and grid[row][col]>=2:
                require(grid[row][col]!=grid[row-1][col], '上下層の強調番手が重複しています')
    return a,den,changed

def solve_intent(spec,d,base):
    from copy import deepcopy
    require(enabled(spec),'意図計画を有効にしてください')
    raw=validate(spec,d)
    p=normalize(spec)
    f=face_for(p,raw['id'])
    fid=f['id'];limit=f.get('limit',p.get('limit'))
    grid=None;targets=[];search='fixed'
    if d['approvedEditable']:
        require(p.get('rules','p18-baseline')=='p18-baseline','旧案比較用の位図では意図番手を変更できません')
        require(sum(x.get('group',x['id'])==f.get('group',fid) for x in p['faces'])==1,
                '連続面の番手は固定です。適用範囲を確認してください')
        require(not p.get('waveSequence'), '固定した領域波形を先に確認してください')
        centers,rows=grid_for(p,f)
        cols=len(centers)
        require(all(any(q['start']<=u<=q['end'] for u in centers) for q in d['quietIntervals']),
                fid+'：余白にモジュール中心が入りません。範囲を広げてください')
        targets=[[build_target(d,u,rows-1-r,rows) for u in centers] for r in range(rows)]
        tables=[evaluate_option(p,f,rows,cols,n,base['seed']) for n in range(9)]
        prior={}
        for piece in base['pieces']:
            if piece['face']==fid:
                row,col,_=map(int,piece['panel'].rsplit('/',1)[1].split('.'))
                prior[row-1,col-1]=piece['level']
        options=[];den=Fraction()
        for r in range(rows):
            for c,u in enumerate(centers):
                denominator=Fraction(str(tables[0][r,c][1]))
                den+=denominator
                quiet=any(q['start']<=u<=q['end'] for q in d['quietIntervals'])
                allowed=[0] if p.get('tenantTop') and r==0 else range(2) if quiet or c in (p.get('blankCols') or []) else range(9)
                values=[]
                for n in allowed:
                    a=Fraction(str(tables[n][r,c][0]))
                    cost=round(abs(a-targets[r][c]*denominator/10000))
                    penalty=cost*(8*MAX_CELLS+1)+abs(n-prior.get((r,c),0))
                    values.append((penalty,n,a))
                options.append(values)
        selected,search=choose(options,limit,den,NODE_BUDGET,cols if d['strictLayers'] else 0)
        require(search!='incomplete',fid+'：計算未完了です。範囲と層間条件を確認してください')
        require(selected is not None,fid+'：面積上限と固定条件が両立しません。固定板・上限を確認してください')
        grid=[selected[i:i+cols] for i in range(0,len(selected),cols)]
        selections=dict(base.get('intentSelections',{}), **{fid:grid})
        result=finish_solution(p,calculate_groups(p,base['seed'],selections))
        result['intentSelections']=selections
    else:
        result=deepcopy(base)
    a,den,changed=validate_candidate(p,f,d,base,result,grid)
    before,_=measures(p,f,base['pieces'])
    summary=next(x for x in result['faces'] if x['face']==fid)
    status='対象なし' if not den else '未設定' if limit is None else '上限内' if 100*a<=limit*den else '上限超過'
    facts=dict(faceId=fid,baseRevision=d['revisionId'],baseResultId=base['resultId'],ruleHash=RULE_HASH,
               selectedLevels=grid,targetBasisPoints=targets,search=search,baseAccentMM2=before,accentMM2=a,
               denominatorMM2=den,denominator=f.get('denominator','net'),limitPercent=limit,limitStatus=status,
               changedPanels=sorted(changed),source=d['evidenceRefs'])
    profile=defaultdict(lambda:[0,0,0,1,0])
    for piece in result['pieces']:
        if piece['face']!=fid or (f.get('denominator')=='visible' and piece['hidden']):
            continue
        row,col,_=map(int,piece['panel'].rsplit('/',1)[1].split('.'))
        left,top,right,bottom=bounds(piece['poly'])
        width=summary['width']
        values=profile[col]
        values[3]=min(values[3],left/width)
        values[4]=max(values[4],right/width)
        if targets:
            target=targets[row-1][col-1]
        else:
            floors=f.get('floors',p['floors'])
            height=summary['height']-(top+bottom)/2
            k=min(len(floors)-1,sum(h<=height for h in accumulate(floors)))
            target=build_target(d,(left+right)/(2*width),k,len(floors))
        values[0]+=piece['area'] if piece['finish']==accent(p) else 0
        values[1]+=piece['area']
        values[2]+=piece['area']*target/10000
    facts['profile']=sorted([dict(u=(left+right)/2,actual=a/total,target=t/total)
                             for a,total,t,left,right in profile.values() if total],key=lambda v:v['u'])
    facts['regions']=[]
    for peak in d['peaks']:
        nearby=[v for v in facts['profile'] if abs(v['u']-peak['center'])<=peak['width']]
        peak_actual=max((v['actual'] for v in nearby),default=None)
        facts['regions'].append(dict(center=peak['center'],width=peak['width'],maxAccent=peak_actual))
    facts['quietIntervals']=d['quietIntervals']
    facts['factId']=digest([d,facts])[:24]
    result['intentFacts']=facts
    result['meaning']=explain_from_facts(p,facts)
    result['resultId']=digest([result['resultId'],facts['factId']])[:24]
    return result


def explain_from_facts(p,facts):
    fid=facts['faceId'];a=facts['accentMM2'];changed=facts['changedPanels'];status=facts['limitStatus']
    description=(f"{fid}面の{accent(p)}は {a/1e6:.2f} m²、比較元 r{facts['baseRevision']} から仕上変更は"
                 f" {len(changed)} 枚です。面積上限：{status}。")
    if facts['selectedLevels'] is None:
        description+='指定条件の配列を保持しました。'
    for region in facts['regions']:
        center=region['center']*100
        ratio=region['maxAccent']
        if ratio is None or ratio==0:
            description+=f' 左端から{center:.0f}%のピーク目標には集計対象の強調部がありません。'
        else:
            description+=f' 左端から{center:.0f}%の目標範囲内で、集計列の最大強調率は{ratio*100:.1f}%です。'
    return description


def revision_dependencies(spec,result,parent,geometry_review=None):
    """Immutable per-revision references. Engineering, view and prose can be reviewed separately."""
    geometry=digest([RULE_HASH,geometry_input(spec),result['pieces'],result['labels'],result['trims']])
    quantity=digest([result['faces'],result['cost'],spec.get('fabrication'),spec.get('prices')])
    rendered=digest([geometry,spec.get('model'),spec.get('camera'),spec.get('light'),spec.get('photo')])
    statement=digest([geometry,result.get('intentFacts'),result['meaning'],spec.get('intent'),spec.get('aiNarrative')])
    return dict(revisionNumber=(parent or 0)+1,parentRevision=parent,applicationVersion='3.1.1 + intent-v1',engineVersion=result['engineVersion'],
                ruleHash=RULE_HASH,geometryHash=geometry,quantityHash=quantity,presentationHash=rendered,
                statementHash=statement,geometryReviewRevision=geometry_review)
