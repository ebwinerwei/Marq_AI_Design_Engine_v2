"""Deterministic strip takeoff and supplier quotes; only confirmed dimensions enter orders."""
from collections import defaultdict
from datetime import date
import math
from .geometry import bounds,classify,rect,area

def takeoff(p,result):
    pieces=defaultdict(list)
    for a in result['pieces']:pieces[(a['panel'],a['finish'])].append(a['poly'])
    specs=p.get('fabrication',{});dirx=p['mode']=='H'
    out=[]
    for (panel,color),polys in pieces.items():
        spec=specs.get(color,{})
        pure=all(isinstance(spec.get(k),(int,float)) and math.isfinite(spec[k]) for k in ('maxLength','fold','kerf','wastePct','pack')) and spec.get('confirmed') is True
        if pure and (min(spec['fold'],spec['kerf'],spec['wastePct'])<0 or spec['pack']<1 or int(spec['pack'])!=spec['pack'] or spec['maxLength']<=2*spec['fold']+spec['kerf']):raise ValueError('加工限度・折返し・ロス・梱包単位を確認してください')
        # A full-width opening separates stock even if both sides have the same panel ID.
        axis=0 if dirx else 1
        runs=[]
        for poly in sorted(polys,key=lambda q:min(v[axis] for v in q)):
            low=min(v[axis] for v in poly); high=max(v[axis] for v in poly)
            if not runs or low>runs[-1][0]+1e-7:
                runs.append([high,[poly]])
            else:
                runs[-1][0]=max(high,runs[-1][0])
                runs[-1][1].append(poly)
        cut_no=0
        for _,polys in runs:
            L,T,R,B=bounds([v for poly in polys for v in poly])
            axis0,axis1=(L,R) if dirx else (T,B)
            step=spec['maxLength']-2*spec['fold']-spec['kerf'] if pure else axis1-axis0
            qty=math.ceil((axis1-axis0)/step)
            if qty>500:raise ValueError('板長制約が細かすぎます')
            for i in range(qty):
                start=axis0+i*step;stop=min(axis1,start+step)
                strip=rect(start,T,stop-start,B-T) if dirx else rect(L,start,R-L,stop-start)
                # The cut strip may contain holes; bounding stock is conservative and repeatable.
                inside=[q for poly in polys for q,yes in classify(poly,strip) if yes] if qty>1 else polys
                if not inside:continue
                l,t,r,b=bounds([v for poly in inside for v in poly]);length=(r-l if dirx else b-t)+(2*spec['fold'] if pure else 0)
                width=b-t if dirx else r-l
                cut_no+=1
                out.append(dict(id=panel+'/'+color+'/'+str(cut_no),panel=panel,finish=color,net=sum(area(q) for q in inside)/1e6,length=length,width=width,stockArea=length*width/1e6,status='加工条件確認済' if pure else '要深化',pack=spec['pack'] if pure else 1,waste=spec['wastePct'] if pure else 0))
    return out
