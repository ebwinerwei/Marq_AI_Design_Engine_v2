"""Millimetre planar overlay. Split convex cells only near feature boundaries."""
import math

EPS = 1e-7

def rect(x,y,w,h):
    return [[x,y],[x+w,y],[x+w,y+h],[x,y+h]]

def area(p):
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in edges(p)))/2

def edges(p):
    return zip(p,p[1:]+p[:1])

def bounds(p):
    x,y=zip(*p)
    return min(x),min(y),max(x),max(y)

def overlaps(a,b):
    return a[0]<b[2]-EPS and b[0]<a[2]-EPS and a[1]<b[3]-EPS and b[1]<a[3]-EPS

def side(a,b,p):
    return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])

def inside(p,shape):
    x,y=p
    return sum(1 for a,b in edges(shape) if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])%2==1

def split(poly,a,b):
    signs=[side(a,b,p) for p in poly]
    if max(signs)<=EPS or min(signs)>=-EPS:
        return [poly]
    left,right=[],[]
    for i,(p,q) in enumerate(edges(poly)):
        s,t=signs[i],signs[(i+1)%len(poly)]
        if s>=-EPS:left.append(p)
        if s<=EPS:right.append(p)
        if s*t<0 and abs(s)>EPS and abs(t)>EPS:
            f=s/(s-t)
            xy=[p[k]+f*(q[k]-p[k]) for k in (0,1)]
            left.append(xy);right.append(xy)
    return [s for s in (left,right) if len(s)>=3 and area(s)>EPS]

def classify(poly,shape):
    if not overlaps(bounds(poly),bounds(shape)):return [(poly,False)]
    pieces=[poly]
    x,y,X,Y=bounds(poly)
    for a,b in edges(shape):
        if max(a[0],b[0])<x or min(a[0],b[0])>X or max(a[1],b[1])<y or min(a[1],b[1])>Y:continue
        pieces=[part for piece in pieces for part in split(piece,a,b)]
        if len(pieces)>1000:raise ValueError('形状が複雑です。立面を分割してください。')
    return [(p,inside([sum(q[i] for q in p)/len(p) for i in (0,1)],shape)) for p in pieces]

def polygon(points):
    if not isinstance(points,list) or not 3<=len(points)<=160:raise ValueError('輪郭の頂点数を確認してください')
    if any(len(p)!=2 or any(not isinstance(v,(float,int)) or not math.isfinite(v) or abs(v)>1e8 for v in p) for p in points):raise ValueError('座標が不正です')
    if area(points)<EPS:raise ValueError('面積がゼロです')
    segments=list(edges(points))
    for i,(a,b) in enumerate(segments):
        if a==b:raise ValueError('重複頂点があります')
        for j,(c,d) in enumerate(segments[i+2:],i+2):
            if i==0 and j==len(segments)-1:continue
            if side(a,b,c)*side(a,b,d)<0 and side(c,d,a)*side(c,d,b)<0:raise ValueError('輪郭が自己交差しています')
    return points

def perimeter(polygons):
    """Cancel interior collinear edges, including partial shared edges at T-junctions."""
    lines={}
    for poly in polygons:
        for a,b in edges(poly):
            dx,dy=b[0]-a[0],b[1]-a[1]
            length=math.hypot(dx,dy)
            if length<.00001:continue
            dx/=length;dy/=length
            if dx<-.00000001 or abs(dx)<.00000001 and dy<0:dx,dy=-dx,-dy
            norm=-dy*a[0]+dx*a[1]
            key=(round(dx,8),round(dy,8),round(norm,4))
            entry=lines.setdefault(key,({},dx,dy,norm));events=entry[0]
            start,stop=sorted([round(dx*a[0]+dy*a[1],5),round(dx*b[0]+dy*b[1],5)])
            events[start]=events.get(start,0)+1;events[stop]=events.get(stop,0)-1
    out=[]
    for events,dx,dy,norm in lines.values():
        count=0;begin=None
        for t,change in sorted(events.items()):
            count+=change
            if count%2 and begin is None:begin=t
            elif count%2==0 and begin is not None:
                out.append([[dx*x-dy*norm,dy*x+dx*norm] for x in [begin,t]]);begin=None
    return out
