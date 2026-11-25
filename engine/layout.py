"""Deterministic facade development; Y points down from the top of each group."""
import hashlib,json,math,random
from .modules import corner_width
from pathlib import Path
from .geometry import rect,area,classify,polygon,bounds,overlaps

RULE=json.loads(Path(__file__).with_name('rules.json').read_text())
WAVES=['234565432','234323432','654323456','234555432','234567']
COLORS={'Silver':'#bec5cc','Slate Navy':'#607895','White':'#f8f8f5','Dark Gray':'#44433f','Electric Blue':'#0744f7','Medium Gray':'#898782','Column':'#353431'}
def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def positive(x):
    if isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) or not 0<x<=1e7:raise ValueError('寸法は正の有限値（mm）で入力してください')
    return x

def pattern(p):
    key=p.get('rules','p18-baseline')
    if key not in ('p18-baseline','word-comparison'):raise ValueError('未知のルール版')
    bits=dict(RULE['bits'])
    if key=='word-comparison':
        bits['C']=bits['C'][:]
        for i,ids in [(4,[2,5,7,13]),(6,[1,3,5,6,8,9,13])]:
            bits['C'][i]=[int(k in ids) for k in range(1,16)]
    return bits

def blanks(n,spans,anchors,rng):
    count=1 if spans<=10 else (2 if spans<20 else 3)
    if spans>10:count+=rng.randrange(2)
    size=max(1,n//max(4*count,1))
    picked=set()
    candidates=list(dict.fromkeys(anchors+[rng.randrange(n) for _ in range(3*n)]))
    for a in candidates:
        start=max(0,min(n-size,a-size//2))
        if any(i in picked for i in range(start-1,start+size+1)):continue
        picked.update(range(start,start+size))
        count-=1
        if not count:break
    return picked

def columns(faces,pitch,t):
    widths=[positive(v) for f in faces for v in f['spans']]
    W=sum(widths)
    if t=='C':
        step=15*pitch
        return [(i*step,step) for i in range(math.ceil(W/step))]
    out=[];x=0
    for w in widths:
        out.extend([(x,w/2),(x+w/2,w/2)]);x+=w
    return out

def levels(p,group,rows,cols,wave,seed):
    n=len(cols);vertical=p['mode']!='H'
    artist=p['mode']=='wave'
    blank=set()
    if artist:
        rng=random.Random(seed)
        anchors=[];offset=0
        for f in group:
            for feature in f.get('features',[]):
                if feature['kind'] in ('logo','entrance'):
                    u=offset+(bounds(feature['poly'])[0]+bounds(feature['poly'])[2])/2
                    anchors.extend(i for i,(x,w) in enumerate(cols) if x<=u<x+w)
            offset+=sum(f['spans'])
        blank=blanks(n,sum(len(f['spans']) for f in group),anchors,rng)
        if p.get('blankCols') is not None:
            blank=set(p['blankCols'])
            if any(type(j)!=int or not 0<=j<n for j in blank):raise ValueError('余白列が展開グループの範囲外です')
    values=[];seq=RULE['seq'][int(vertical)]
    skip=int(bool(p.get('tenantTop')))
    region_by_col=[]
    active_region=-1
    for col in range(n):
        if col not in blank and (col==0 or col-1 in blank):active_region+=1
        region_by_col.append(max(0,active_region))
    for r in range(rows):
        row=[];start=0
        for c in range(n):
            if r<skip:v=0
            elif not artist:v=int(seq[((r-skip)*n+c)%len(seq)])
            elif c in blank:
                v=1 if c>0 and c-1 not in blank and (c+seed)%2 else 0
                start=c+1
            else:
                selected=wave if not p.get('waveSequence') else p['waveSequence'][region_by_col[c]%len(p['waveSequence'])]
                v=max(1,int(selected[(c-start+seed)%len(selected)])-round(3*(r-skip)/max(1,rows-1-skip)))
                if r>skip and v>=2 and v==values[-1][c]:v-=1
            row.append(v)
        values.append(row)
    return values

def prepared(f,t,p,H,mh,mw,heights):
    effects=[];labels=[];trims=[]
    W=sum(f['spans']);features=f.get('features',[])
    if len(features)>200:raise ValueError('構件数の上限です')
    for k,feat in enumerate(features):
        kind=feat['kind'];shape=polygon(feat['poly']);x,y,X,Y=bounds(shape)
        if x<0 or y<0 or X>W+.01 or Y>H+.01:raise ValueError(f['id']+'：構件が立面範囲外です')
        if kind=='logo':
            corner=feat.get('corner',False)
            scale=(2 if corner else 3) if t=='C' else (4 if corner else 6)
            h=(heights[0]+(heights[1] if len(heights)>1 else heights[0])/2) if t=='C' else 1.5*mh
            if t=='C':w=scale*mw
            else:
                localX=W-.001 if corner=='right' else .001 if corner=='left' else (x+X)/2
                pos=0;moduleAt=mw
                for span in f['spans']:
                    if pos<=localX<=pos+span:moduleAt=span/2;break
                    pos+=span
                w=scale*moduleAt
            if corner in ('left','right'):
                w=corner_width(f['spans'],corner=='right',t=='C',p['pitch'])
            if feat.get('clearanceM') is not None and y<positive(feat['clearanceM']):raise ValueError(f['id']+'：ロゴ上部のM幅クリアランス不足')
            low=0 if corner=='left' else W-w if corner=='right' else (x+X-w)/2
            effects.append(('silver',rect(low,0,w,max(h,feat.get('extend',0))), 'P21.logo'))
            labels.append(dict(kind='logo',text=feat.get('text','Marq'),poly=shape,asset=feat.get('asset'),clearanceM=feat.get('clearanceM')))
        elif kind=='ramp':
            ratio=feat.get('ratio',.17)
            if not .14<=ratio<=.20 or len(shape)!=4:raise ValueError('腰壁は左上・右上・右下・左下の4点、ライン率14–20%')
            def at(a,b,v):return [a[i]+v*(b[i]-a[i]) for i in [0,1]]
            a,b,c,d=shape
            band=[at(a,d,(1-ratio)/2),at(b,c,(1-ratio)/2),at(b,c,(1+ratio)/2),at(a,d,(1+ratio)/2)]
            effects.extend([('Dark Gray',shape,'P24.ramp'),('Electric Blue',band,'P24.line')])
        elif kind=='berth':
            labels.append(dict(kind=kind,text=str(feat['number']).zfill(3),poly=shape))
            effects.append(('hole',shape,'P25.door'))
        elif kind=='slope':
            trims.append(shape[:2])
            if t=='C':effects.append(('hole',shape,'P24.slope'))
            else:
                a,b=shape[:2]
                if b[1]==a[1]:effects.append(('hole',shape,'P24.level'))
                else:
                    # Slice at real horizontal panel courses and step the inclined edge.
                    for j in range(math.floor(y/p['pitch']),math.ceil(Y/p['pitch'])):
                        yy=max(y,j*p['pitch']);bottom=min(Y,(j+1)*p['pitch'])
                        pts=[v for part,hit in classify(rect(x,yy,X-x,bottom-yy),shape) if hit for v in part]
                        if pts:
                            l,_,rr,_=bounds(pts)
                            effects.append(('hole',rect(l,yy,rr-l,bottom-yy),'P24.step'))
        else:
            modes={'opening':'hole','entrance':'hole','band':'hole','smoke':'whole','future':'whole','equipment':'hide','return':'silver','notch':'silver','silver':'silver','road':'Medium Gray','column':'Column'}
            if kind not in modes:raise ValueError('未知の構件 '+kind)
            effects.append((modes[kind],shape,'P23.'+kind if kind in ('band','opening','equipment','smoke','future') else 'finish.'+kind))
            if kind=='smoke' and feat.get('physicalHole'):effects.append(('hole',shape,'P23.smokeHole'))
    order={'whole':0,'silver':1,'Dark Gray':2,'Medium Gray':2,'Column':2,'Electric Blue':3,'hole':4,'hide':5}
    return sorted(effects,key=lambda entry:order[entry[0]]),labels,trims

def calculate(p,seed,selected_levels=None):
    pitch=positive(p['pitch']);mode=p['mode'];stock=p['stock']
    if mode not in ('H','V','wave') or stock not in ('cs','dry'):raise ValueError('工法・用途が不正です')
    t='A' if mode=='H' and pitch<=750 else 'B' if mode=='H' else 'C'
    bits=pattern(p)[t];n=len(bits[0]);mh=pitch*n;wave=p.get('wave',WAVES[0])
    if p.get('waveSequence') and (not isinstance(p['waveSequence'],list) or len(p['waveSequence'])>8 or any(w not in WAVES for w in p['waveSequence'])):raise ValueError('領域別の波形を選択してください')
    if not wave or any(c not in '2345678' for c in wave) or len(wave)>80 or any(wave[i:i+6]==wave[i:i+2]*3 and wave[i]!=wave[i+1] for i in range(len(wave)-5)):raise ValueError('波形を確認してください（千鳥反復不可）')
    faces=p['faces'];ids=[f['id'] for f in faces]
    if not 0<len(faces)<=64 or len(ids)!=len(set(ids)):raise ValueError('立面IDは一意、最大64面')
    allpieces=[];summary=[];labels=[];trims=[];issues=[];groups={};modulecount=0
    for f in faces:
        if len(f['spans'])>2000 or not f['spans']:raise ValueError('柱スパン数が不正です')
        groups.setdefault(f.get('group',f['id']),[]).append(f)
    for group in groups.values():
        floors=[positive(h) for h in group[0].get('floors',p['floors'])]
        if not floors or len(floors)>200:raise ValueError('階高の数は1〜200で入力してください')
        heights=list(reversed(floors));para=group[0].get('parapet',0)
        if para:heights[0]+=positive(para)
        H=sum(heights);cols=columns(group,pitch,t);W=sum(sum(f['spans']) for f in group)
        scan=p.get('scan','auto')
        reverse=scan=='right' or (scan=='auto' and len(group)==1 and any(k['kind']=='logo' and k.get('corner')=='right' for k in group[0].get('features',[])))
        if reverse and t=='C':cols=[(W-x-w,w) for x,w in cols]
        elif reverse:cols=list(reversed(cols))
        rows=heights if t=='C' else [mh]*math.ceil(H/mh)
        modulecount+=len(rows)*len(cols)*n
        if modulecount>100000:raise ValueError('案件の板数上限（10万枚）を超えました。展開グループを分けてください')
        lv=levels(p,group,len(rows),cols,wave,seed);offset=0
        for f in group:
            local=[positive(h) for h in f.get('floors',p['floors'])]
            if not local or len(local)>200:raise ValueError('階高の数は1〜200で入力してください')
            heights=list(reversed(local));heights[0]+=positive(f['parapet']) if f.get('parapet') else 0
            H=sum(heights);rows=heights if t=='C' else [mh]*math.ceil(H/mh)
            if len(rows)*len(cols)*n>100000:raise ValueError('板数が上限を超えています')
            lv=selected_levels if selected_levels is not None else levels(p,group,len(rows),cols,wave,seed)
            width=sum(f['spans']);fid=f['id'];end=offset+width
            outline=polygon(f.get('outline') or rect(0,0,width,H));simple=outline==rect(0,0,width,H)
            moduleW=15*pitch if t=='C' else f['spans'][0]/2
            effects,marks,trim=prepared(f,t,p,H,mh,moduleW,heights)
            labels.extend(dict(item,face=fid) for item in marks);trims.extend(dict(points=line,face=fid,length=math.dist(*line)) for line in trim)
            bands=[bounds(fe['poly']) for fe in f.get('features',[]) if fe['kind']=='band' and fe.get('shift',False) and t=='C']
            effects=[(kind,poly,rule,bounds(poly)) for kind,poly,rule in effects]
            mesh=f.get('surfaceTriangles',[])
            if len(mesh)>4000:raise ValueError('投影面の三角形数の上限です')
            triangles=[(polygon(tri),bounds(tri)) for tri in mesh]
            tally={};visible={};ids_used=set();top=0
            for r,rh in enumerate(rows):
                for c,(u,w) in enumerate(cols):
                    if u>=end or u+w<=offset:continue
                    level=lv[r][c]
                    for k in range(n):
                        mirrored=reverse and p.get('mirrorBits',False)
                        u0=u+(n-1-k if mirrored else k)*pitch if t=='C' else u
                        x=max(offset,u0)-offset;X=min(end,u0+(pitch if t=='C' else w))-offset
                        if X<=x:continue
                        y=top+(0 if t=='C' else k*pitch);Y=min(H,y+(rh if t=='C' else pitch))
                        if Y<=y:continue
                        pid=f'{fid}/{r+1}.{c+1}.{k+1}'
                        accent=bits[level][k] if not (p.get('tenantTop') and r==0) else 0
                        finish=('Slate Navy' if stock=='dry' else 'White') if accent else 'Silver'
                        finish=p.get('locks',{}).get(pid,finish)
                        if finish not in COLORS:raise ValueError('ロック色が不正です')
                        # Local strip boundaries follow window heads only within the actual band width.
                        cuts=sorted(set([x,X]+[v for lo,_,hi,_ in bands for v in (lo,hi) if x<v<X]))
                        before=len(allpieces)
                        for l,rr in zip(cuts,cuts[1:]):
                            yy,YY=y,Y
                            if bands:
                                mid=(l+rr)/2
                                for lo,bt,hi,bb in bands:
                                    if lo<=mid<hi:
                                        edgesY=[sum(rows[:j]) for j in range(1,len(rows))]
                                        if edgesY:
                                            boundary=min(edgesY,key=lambda val:abs(val-bt))
                                            if y==boundary:yy=bt
                                            if Y==boundary:YY=bt
                            if YY<=yy:continue
                            cell=rect(l,yy,rr-l,YY-yy)
                            parts=[(cell,finish,False,[])] if simple else [(a,finish,False,['P19.clip']) for a,hit in classify(cell,outline) if hit]
                            if triangles:
                                candidates=[tri for tri,bb in triangles if overlaps(bounds(cell),bb)]
                                # Union triangles before assigning material. Shared edges have zero area.
                                pending=parts;kept=[]
                                for tri in candidates:
                                    next_parts=[]
                                    for poly,col,hid,tr in pending:
                                        for piece,hit in classify(poly,tri):
                                            (kept if hit else next_parts).append((piece,col,hid,tr))
                                    pending=next_parts
                                parts=kept
                            hits=[e for e in effects if overlaps(bounds(cell),e[3])]
                            whole=any(kind=='whole' and any(hit for _,hit in classify(cell,shape)) for kind,shape,rule,bb in effects if kind=='whole' and overlaps(bounds(cell),bb))
                            if whole:parts=[(a,'Silver',hidden,tr+['P23.whole']) for a,col,hidden,tr in parts]
                            for kind,shape,rule,bb in hits:
                                if kind=='whole':continue
                                updated=[]
                                for a,col,hidden,tr in parts:
                                    for b,hit in classify(a,shape):
                                        if hit and kind=='hole':continue
                                        color=('Silver' if kind=='silver' else kind if kind in COLORS else col) if hit else col
                                        updated.append((b,color,hidden or (hit and kind=='hide'),tr+([rule] if hit else [])))
                                parts=updated
                            for poly,col,hidden,trace in parts:
                                ar=area(poly)
                                tally[col]=tally.get(col,0)+ar
                                if not hidden:visible[col]=visible.get(col,0)+ar
                                ids_used.add(pid)
                                allpieces.append(dict(panel=pid,id=pid+'-'+str(len(allpieces)-before+1),face=fid,level=level,finish=col,poly=poly,area=ar,hidden=hidden,trace=['P18.'+t,'P20' if mode!='wave' else 'V31-33']+trace))
                                if len(allpieces)>150000:raise ValueError('裁切形状の上限です')
                top+=rh
            den=sum((visible if f.get('denominator')=='visible' else tally).values())
            numer=(visible if f.get('denominator')=='visible' else tally).get('White' if stock=='cs' else 'Slate Navy',0)
            ratio=100*numer/den if den else 0
            limit=f.get('limit',p.get('limit'))
            if limit is not None and not 0<=limit<=100:raise ValueError('面積上限は0–100%')
            if limit is not None and ratio>limit+1e-8:issues.append(f'{fid}：{ratio:.2f}% > {limit}%')
            summary.append(dict(face=fid,width=width,height=H,finishes=tally,visible=visible,ratio=ratio,panels=len(ids_used)))
            offset=end
    berth=[i['text'] for i in labels if i['kind']=='berth']
    if len(berth)!=len(set(berth)):issues.append('バース番号の重複')
    costs=p.get('prices',{})
    if any(not isinstance(v,(float,int)) or v<0 or not math.isfinite(v) for v in costs.values()):raise ValueError('単価が不正です')
    used={col for f in summary for col in f['finishes']}
    cost=sum(v*costs.get(col,0)/1e6 for f in summary for col,v in f['finishes'].items())
    if p.get('budget') is not None:
        if used-costs.keys():issues.append('見積単価未登録')
        elif cost>p['budget']:issues.append('予算超過')
    return dict(type=t,pieces=allpieces,faces=summary,labels=labels,trims=trims,issues=issues,cost=cost if used<=costs.keys() else None,seed=seed)

def solve(p):
    if p.get('intentPlanVersion') is not None and ('intentDraft' in p or 'forkedIntentResult' in p):
        raise ValueError('意図案の再計算には案件内の保存版が必要です')
    from .policy import normalize
    p=normalize(p)
    seed=int(p.get('seed',0));best=None
    for i in range(12 if p['mode']=='wave' else 1):
        candidate=calculate_groups(p,seed+i)
        if best is None or len(candidate['issues'])<len(best['issues']):best=candidate
        if not best['issues']:break
    return finish_solution(p,best)

def finish_solution(p,best):
    best['status']='feasible' if not best['issues'] else ('searchLimit' if p['mode']=='wave' else 'conflict')
    from collections import defaultdict
    from .geometry import perimeter
    groups=defaultdict(list)
    for a in best['pieces']:
        if not a['hidden']:groups[(a['face'],a['panel'],a['finish'])].append(a['poly'])
    best['seams']=[dict(face=f,panel=panel,segments=perimeter(polys)) for (f,panel,col),polys in groups.items()]
    engineering={k:v for k,v in p.items() if k in ('rules','mode','stock','pitch','floors','faces','locks','seed','scan','wave','waveSequence','tenantTop','mirrorBits','prices','budget','limit','catalog','fabrication','policyRefs','blankCols','landscape','approvedSamples')}
    best['engineVersion']='3.1.0'
    best['resultId']=digest({'engine':'3.1.0','data':engineering,'solution':best})[:24]
    best['meaning']=('上層にアクセントを寄せ、余白で壁面を分節する計画です。' if p['mode']=='wave' else '規定配列を上端から展開し、シルバーとアクセントの疎密で大壁面にリズムを与えます。')+' 各面の実測比率：'+'、'.join(f"{f['face']} {f['ratio']:.1f}%" for f in best['faces'])
    return best

_group_cache={}
import threading
_cache_lock=threading.Lock()
def calculate_groups(p,seed,selected=None):
    groups={}
    for f in p['faces']:groups.setdefault(f.get('group',f['id']),[]).append(f)
    merged=dict(pieces=[],faces=[],labels=[],trims=[],issues=[],seed=seed,cost=0)
    for faces in groups.values():
        base={k:v for k,v in p.items() if k in ('seed','pitch','mode','stock','floors','rules','wave','waveSequence','tenantTop','scan','blankCols','mirrorBits','locks','limit','prices')}
        base['faces']=faces
        grid=selected.get(faces[0]['id']) if selected else None
        key=digest([base,seed] if grid is None else [base,seed,grid])
        with _cache_lock:part=_group_cache.get(key)
        if part is None:
            part=calculate(base,seed,grid)
            if len(part['pieces'])<12000:
                with _cache_lock:
                    if len(_group_cache)>=10:_group_cache.pop(next(iter(_group_cache)))
                    _group_cache[key]=part
        merged['type']=part['type']
        for field in ('pieces','faces','labels','trims','issues'):merged[field].extend(part[field])
        if merged['cost'] is not None:merged['cost']=None if part['cost'] is None else merged['cost']+part['cost']
        if len(merged['pieces'])>150000:raise ValueError('全案件の裁切形状上限です')
    berth=[m['text'] for m in merged['labels'] if m['kind']=='berth']
    if len(set(berth))!=len(berth) and 'バース番号の重複' not in merged['issues']:merged['issues'].append('バース番号の重複')
    if p.get('budget') is not None:
        if merged['cost'] is None:merged['issues'].append('見積単価未登録')
        elif merged['cost']>p['budget']:merged['issues'].append('予算超過')
    landscape=p.get('landscape',{})
    restrictions=landscape.get('colorLimits',{})
    samples=p.get('approvedSamples',{})
    for col,limit in restrictions.items():
        if not any(f['finishes'].get(col,0)>0 for f in merged['faces']):continue
        sample=samples.get(col,{})
        if not sample.get('source') or any(k not in sample for k in ('hue','value','chroma')):
            merged['issues'].append(col+'：実色見本の測色値未確認');continue
        if (limit.get('hues') and sample['hue'] not in limit['hues'] or sample['chroma']>limit.get('maxChroma',100) or not limit.get('minValue',0)<=sample['value']<=limit.get('maxValue',10)):
            merged['issues'].append(col+'：承認された景観色範囲外')
    return merged
