"""Input provenance, adjacent corner rules and stable group boundaries."""
import math,copy
from .modules import corner_width
from .geometry import bounds,rect
def normalize(spec):
    p=copy.deepcopy(spec)
    if 'name' not in p or not isinstance(p['name'],str) or not p['name'].strip():raise ValueError('案件名を入力してください')
    faces=p.get('faces')
    if not isinstance(faces,list) or not 1<=len(faces)<=64:
        raise ValueError('案件全体で立面を1〜64面指定してください')
    if len(set(f.get('id') for f in faces))!=len(faces):
        raise ValueError('展開グループをまたぐ場合も立面名を一意にしてください')
    for f in p['faces']:
        if not f.get('id') or not isinstance(f['id'],str) or len(f['id'])>80:raise ValueError('立面名が不正です')
        xyz=f.get('origin',[0,0,0])
        if len(xyz)!=3 or any(not math.isfinite(v) for v in xyz) or not math.isfinite(f.get('azimuth',0)):raise ValueError('原点・方位が不正です')
        if f.get('denominator','net') not in ('visible','net'):raise ValueError('面積分母を指定してください')
        if f.get('outline'):
            high=sum(f.get('floors',p['floors']))+f.get('parapet',0);lo,top,hi,bt=bounds(f['outline'])
            if lo<0 or top<0 or hi>sum(f['spans'])+.0001 or bt>high+.0001:raise ValueError('輪郭が軸網・階高範囲を超えています')
    def ends(f):
        x,y,z=f.get('origin',[0,0,0]);a=math.radians(f.get('azimuth',0));w=sum(f['spans'])
        return [(x,y,z),(x+w*math.cos(a),y,z+w*math.sin(a))]
    groups={}
    for f in p['faces']:
        code=f.get('group',f['id']);prev=groups.get(code)
        if prev and math.dist(ends(prev)[1],ends(f)[0])>1 and not f.get('projectionEvidence'):
            raise ValueError(code+'：連続面の接続辺が一致しません。雁行投影なら projectionEvidence を記録してください')
        groups[code]=f
    for f in p['faces']:
        for feat in list(f.get('features',[])):
            corner=feat.get('corner')
            if feat['kind']!='logo' or corner not in ('left','right'):continue
            endpoint=ends(f)[int(corner=='right')]
            for adj in p['faces']:
                if adj is f:continue
                for index,pos in enumerate(ends(adj)):
                    if math.dist(endpoint,pos)>1:continue
                    w=sum(adj['spans']);vert=p['mode']!='H';mw=15*p['pitch'] if vert else adj['spans'][-1 if index else 0]/2
                    bg=corner_width(adj['spans'],bool(index),vert,p['pitch']);floors=adj.get('floors',p['floors']);h=floors[-1]+adj.get('parapet',0)
                    bh=h+(floors[-2] if len(floors)>1 else h)/2 if vert else (12 if p['pitch']<=750 else 8)*p['pitch']*1.5
                    adj.setdefault('features',[]).append(dict(kind='silver',poly=rect(w-bg if index else 0,0,bg,min(bh,sum(floors)+adj.get('parapet',0)))))
    return p
