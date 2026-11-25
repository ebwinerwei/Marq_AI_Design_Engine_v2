"""Import the two released v1 file formats without rewriting source assets."""
def migrate(doc):
    from .geometry import rect
    from .layout import solve
    if doc.get('schema')=='made-project-3':return doc
    if doc.get('version')!=1:raise ValueError('旧版規則条件を指定してください')
    a=doc['fields'];arr=lambda k:[int(v) for v in a[k].split(',')]
    floors=arr('f');widths=arr('w');span=int(a['g']);pitch=int(a['p'])
    if min(span,pitch,*widths,*floors)<=0 or len(widths)>64 or sum(widths)/span>2000:raise ValueError('寸法またはスパン数の上限です')
    p=dict(schema='made-project-3',name='2.0 割付条件からの移行',rules='p18-baseline',mode=a['m'],stock=a['s'],pitch=pitch,floors=floors,seed=0,wave=a.get('v') or '234565432',scan='right' if a['r']=='1' else 'left',mirrorBits=a['r']=='1',tenantTop=a.get('t')=='1',faces=[],assets=[],importedConditions=doc,importReview='2.0 端部の半スパン、モジュール向き、ロゴ、連窓と実測図面を確認してください')
    if a.get('b'):
        cols=[]
        for pair in a['b'].split(','):
            lo,hi=map(int,pair.split('-'))
            if not 1<=lo<=hi<=10000:raise ValueError('余白列が不正です')
            cols.extend(range(lo-1,hi))
        p['blankCols']=cols
    pos=0;H=sum(floors)
    for i,w in enumerate(widths):
        spans=[span]*(w//span)+([w%span] if w%span else [])
        f=dict(id='F'+str(i+1),origin=[pos,0,0],azimuth=0,spans=spans,group='展開1',features=[])
        for row in a.get('k','').splitlines():
            kind,*nums=row.split(',');x,y,rw,rh=map(float,nums);l=max(pos,x);rr=min(pos+w,x+rw)
            if rr>l:f['features'].append(dict(kind=kind,poly=rect(l-pos,y,rr-l,rh)))
        band=int(a.get('d') or 0);top=0
        for rh in reversed(floors):
            if band:f['features'].append(dict(kind='band',shift=False,poly=rect(0,top+rh-band,w,band)))
            top+=rh
        p['faces'].append(f);pos+=w
    which=a.get('l','none');vertical=p['mode']!='H';mw=pitch*15 if vertical else span/2
    hh=min(H,(floors[-1]+(floors[-2] if len(floors)>1 else floors[-1])/2) if vertical else 1.5*(12 if pitch<=750 else 8)*pitch)
    if which!='none':
        w=(3 if vertical else 6)*mw if which=='center' else (2 if vertical else 4)*mw
        if which=='corner':
            seam=int(a['z']);f0=p['faces'][seam-1];f1=p['faces'][seam];w0=sum(f0['spans']);w1=sum(f1['spans'])
            for f,x,rw in [(f0,max(0,w0-w),min(w0,w)),(f1,0,min(w,w1))]:f['features'].append(dict(kind='silver',poly=rect(x,0,rw,hh)))
        else:
            full=sum(widths);left={'left':0,'center':(full-w)/2,'right':full-w}[which];pos=0
            for f in p['faces']:
                width=sum(f['spans']);l=max(pos,left);rr=min(pos+width,left+w)
                if rr>l:f['features'].append(dict(kind='silver',poly=rect(l-pos,0,rr-l,hh)))
                pos+=width
    solve(p)
    return p
