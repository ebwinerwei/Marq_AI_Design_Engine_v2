"""Portable OOXML, real-scale GLB and DXF writers. No install on the client."""
import io,json,struct,zipfile,math,collections
from xml.sax.saxutils import escape,quoteattr
from .layout import COLORS
from .geometry import edges,bounds
CAT={'Silver':['OF321S','FA107S','F204SE','YT20H','CFシルバーS',None],'White':['OF201S','FW201S','F802SE','YT45H','CFホワイト',None],'Medium Gray':['OF301S','FA106S','F902SE','YT85H','CFグレー',None]}
MAN=['日鉄鋼板','ヨドコウ','アイジー工業']
def xmlfile(sheets):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        def rels(rows):return '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="r{i}" Type="{rel}/{t}" Target="{target}"/>' for i,t,target in rows)+'</Relationships>'
        z.writestr('_rels/.rels',rels([(1,'officeDocument','xl/workbook.xml')]))
        manifest=['<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
        tabs=[]
        for i,(name,rows) in enumerate(sheets,1):
            path=f'worksheets/sheet{i}.xml'
            tabs.append(f'<sheet name={quoteattr(name)} sheetId="{i}" r:id="r{i}"/>')
            manifest.append(f'<Override PartName="/xl/{path}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
            cells=[]
            for n,row in enumerate(rows,1):
                fields=[]
                for k,v in enumerate(row):
                    ref=chr(65+k)+str(n)
                    if isinstance(v,(int,float)):fields.append(f'<c r="{ref}"><v>{v}</v></c>')
                    else:fields.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>')
                cells.append('<row r="%d">%s</row>'%(n,''.join(fields)))
            z.writestr('xl/'+path,f'<worksheet xmlns="{ns}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="14" width="24" customWidth="1"/></cols><sheetData>'+''.join(cells)+'</sheetData></worksheet>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'+''.join(tabs)+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',rels([(i,'worksheet',f'worksheets/sheet{i}.xml') for i in range(1,len(tabs)+1)]))
        z.writestr('[Content_Types].xml',''.join(manifest)+'</Types>')
    return out.getvalue()

def xlsx(p,r,state):
    state={'draft':'検討用（草案）','review':'検討用（照査中）','approved':'承認済'}.get(state,state)
    rows=[['立面','仕上','設計純量 m²','可視 m²','アクセント %','異なる原板ID数（面単位）']]
    for f in r['faces']:
        for col,v in f['finishes'].items():rows.append([f['face'],col,v/1e6,f['visible'].get(col,0)/1e6,f['ratio'],f['panels']])
    detail=[['原板ID','図形片ID','面','番号','仕上','面積 m²','規則','輪郭 mm']]
    counts=collections.defaultdict(set);areas=collections.Counter()
    for a in r['pieces']:
        detail.append([a['panel'],a['id'],a['face'],a['level'],a['finish'],a['area']/1e6,','.join(a['trace']),str(a['poly'])])
        counts[a['finish']].add(a['panel']);areas[a['finish']]+=a['area']/1e6
    meta=[['項目','値'],['案件',p['name']],['基準図・改訂',p.get('drawingSource','未記入')],['resultId',r['resultId']],['状態',state],['規則',p['rules']],['カタログ','P38 / '+str(p.get('priceSource','単価未確認'))],['予算推計 円',r['cost'] if r['cost'] is not None else '未確定'],['発注数量','加工・見積条件を要確認']]
    sheets=[('案件',meta),('立面別',rows),('板明細',detail)]
    from .procurement import takeoff
    cuts=takeoff(p,r)
    cut_counts=collections.Counter(a['finish'] for a in cuts)
    classifications={'Slate Navy':'特注色','Dark Gray':'塗装','Electric Blue':'塗装','Column':'部位仕様確認'}
    panel_area=sum(v for col,v in areas.items() if col in CAT or col=='Slate Navy')
    special_area=areas['Slate Navy']
    meta.extend([['用途','冷凍冷蔵' if p['stock']=='cs' else 'ドライ'],['貼り方向','横' if p['mode']=='H' else '縦'],
                 ['特注 Slate Navy 面積 m²',special_area],['外壁パネル純面積 m²（塗装・柱を除く）',panel_area],
                 ['特注色比率 %（特注面積／外壁パネル純面積）',100*special_area/panel_area if panel_area else '対象なし']])
    for i,m in enumerate(MAN):
        rr=[['仕上','品番','純面積 m²','関連原板数','単価 円/m²','概算 円','備考','仕上区分','加工検討枚数']]
        for col,v in areas.items():
            code=p.get('catalog',{}).get(col,CAT.get(col,[None]*6))[2*i+int(p['mode']!='H')]
            unit=p.get('prices',{}).get(col)
            rr.append([col,code or '要照会',v,len(counts[col]),unit if unit is not None else '',v*unit if unit is not None else '', '代替メーカー比較・数量を合算しない',classifications.get(col,'標準色'),cut_counts[col]])
        sheets.append((m,rr))
    sheets.append(('下料明細',[['切件ID','原板','仕上','正味 m²','取り寸長 mm','幅 mm','必要素材 m²','加工確認']]+[[a['id'],a['panel'],a['finish'],a['net'],a['length'],a['width'],a['stockArea'],a['status']] for a in cuts]))
    groups=collections.defaultdict(list)
    for a in cuts:groups[(a['finish'],a['length'],a['width'])].append(a)
    quantity=[['仕上','取寸長 mm','幅 mm','加工枚数','予備込梱包枚数','判定']]
    for (col,length,width),items in groups.items():
        sample=items[0];num=len(items)
        qty=math.ceil(num*(1+sample['waste']/100)/sample['pack'])*sample['pack'] if sample['status']=='加工条件確認済' else '要深化'
        quantity.append([col,length,width,num,qty,sample['status']])
    sheets.append(('発注検討',quantity))
    sheets.append(('納まり・審査',[['項目','内容']]+[[t['face'],f"{t['length']:.2f} mm 見切り"] for t in r['trims']]+[['要確認',x] for x in r['issues']]+[['設計説明',r['meaning']]]))
    if 'intentFacts' in r:
        facts=r['intentFacts']
        comparison=[['比較項目','保存版の値'],['対象立面',facts['faceId']],['比較元の版',facts['baseRevision']],
                    ['比較元の結果',facts['baseResultId']],['結果',r['resultId']],['事実ID',facts['factId']],
                    ['規則の内容 SHA-256',facts['ruleHash']],['出典',' / '.join(facts['source'])],
                    ['比較元アクセント m²',facts['baseAccentMM2']/1e6],['選定案アクセント m²',facts['accentMM2']/1e6],
                    ['分母',facts['denominator']],['分母 m²',facts['denominatorMM2']/1e6],
                    ['設定上限 %',facts['limitPercent'] if facts['limitPercent'] is not None else '未設定'],
                    ['面積上限の判定',facts['limitStatus']],['状態',state],['設計説明',r['meaning']]]
        comparison.extend([['出力版',r.get('dependencies',{}).get('revisionNumber','試算')],['親版',r.get('dependencies',{}).get('parentRevision','試算')],
                           ['幾何ハッシュ',r.get('dependencies',{}).get('geometryHash','試算')]])
        comparison.extend(['仕上変更板',panel] for panel in facts['changedPanels'])
        sheets.append(('意図案比較',comparison))
    return xmlfile(sheets)

def world(f,H,xy):
    a=f.get('origin',[0,0,0]);ang=math.radians(f.get('azimuth',0));u,v=xy
    return [(a[0]+u*math.cos(ang))/1000,(a[1]+H-v)/1000,(a[2]+u*math.sin(ang))/1000]

def glb(p,r,load_asset=None):
    data=bytearray();views=[];attrs=[];primitives=[]
    face={f['id']:f for f in p['faces']};heights={s['face']:s['height'] for s in r['faces']}
    grouped=collections.defaultdict(list)
    for piece in r['pieces']:
        if piece['hidden']:continue
        poly=[world(face[piece['face']],heights[piece['face']],v) for v in piece['poly']]
        for i in range(1,len(poly)-1):grouped[piece['finish']].extend([poly[0],poly[i],poly[i+1]])
    from .signs import labels_as_quads
    from .geometry import rect
    for fid,name,rectangle,lift in labels_as_quads(r['labels']):
        f=face[fid];ang=math.radians(f.get('azimuth',0))
        pts=[world(f,heights[fid],v) for v in rect(*rectangle)]
        for pt in pts:pt[0]-=math.sin(ang)*lift;pt[2]+=math.cos(ang)*lift
        grouped[name].extend(pts[i] for i in [0,1,2,0,2,3])
    for trim in r['trims']:
        fid=trim['face'];a,b=trim['points'];dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
        if length:
            width=p.get('trimWidth',40)/2;ox=-dy*width/length;oy=dx*width/length
            poly=[[a[0]+ox,a[1]+oy],[b[0]+ox,b[1]+oy],[b[0]-ox,b[1]-oy],[a[0]-ox,a[1]-oy]]
            pts=[world(face[fid],heights[fid],v) for v in poly];grouped['Trim'].extend(pts[i] for i in [0,1,2,0,2,3])
    mats=[]
    for k,(name,positions) in enumerate(grouped.items()):
        color={**COLORS,'Sign Black':'#181d22','Sign White':'#ffffff','Trim':'#858a90'}[name][1:]
        rgb=[(int(color[i:i+2],16)/255)**2.2 for i in [0,2,4]]
        mats.append({'name':name,'doubleSided':True,'pbrMetallicRoughness':{'baseColorFactor':rgb+[1],'metallicFactor':.15,'roughnessFactor':.7}})
        offset=len(data)
        for v in positions:data.extend(struct.pack('<3f',*v))
        views.append(dict(buffer=0,byteOffset=offset,byteLength=len(data)-offset,target=34962))
        attrs.append(dict(bufferView=k,componentType=5126,count=len(positions),type='VEC3',min=list(map(min,zip(*positions))),max=list(map(max,zip(*positions)))))
        primitives.append(dict(attributes={'POSITION':k},material=k))
    if not primitives:raise ValueError('出力可能な立面がありません')
    obj=dict(asset=dict(version='2.0',generator='Blue Light M.A.D.E.'),extras=dict(resultId=r['resultId'],units='m',labels=r['labels'],trims=r['trims']),scene=0,scenes=[dict(nodes=[0])],nodes=[dict(mesh=0)],meshes=[dict(primitives=primitives)],materials=mats,buffers=[dict(byteLength=len(data))],bufferViews=views,accessors=attrs)
    images=[];textures=[]
    for item in r['labels']:
        if not item.get('asset') or load_asset is None:continue
        image=load_asset(item['asset'])
        if not image.startswith(bytes.fromhex('89504e470d0a1a0a')):raise ValueError('正式ロゴはPNGを指定してください')
        offset=len(data);data.extend(image);data.extend(b'\0'*(-len(data)%4))
        image_view=len(views);views.append(dict(buffer=0,byteOffset=offset,byteLength=len(image)))
        images.append(dict(bufferView=image_view,mimeType='image/png'));textures.append(dict(source=len(images)-1))
        f=face[item['face']];x,y,X,Y=bounds(item['poly']);verts=[world(f,heights[item['face']],pt) for pt in rect(x,y,X-x,Y-y)]
        angle=math.radians(f.get('azimuth',0))
        for pt in verts:pt[0]-=math.sin(angle)*.012;pt[2]+=math.cos(angle)*.012
        indices=[0,1,2,0,2,3];attr_ids=[]
        for values,dim in [(verts,3),([[0,0],[1,0],[1,1],[0,1]],2)]:
            offset=len(data)
            for idx in indices:data.extend(struct.pack('<'+'f'*dim,*values[idx]))
            views.append(dict(buffer=0,byteOffset=offset,byteLength=len(data)-offset,target=34962))
            attr_ids.append(len(attrs));attrs.append(dict(bufferView=len(views)-1,componentType=5126,count=6,type='VEC'+str(dim),min=list(map(min,zip(*values))),max=list(map(max,zip(*values)))))
        primitives.append(dict(attributes=dict(POSITION=attr_ids[0],TEXCOORD_0=attr_ids[1]),material=len(mats)))
        mats.append(dict(name='Approved sign',alphaMode='MASK',doubleSided=True,pbrMetallicRoughness=dict(baseColorTexture=dict(index=len(textures)-1),metallicFactor=0,roughnessFactor=1)))
    if images:obj.update(images=images,textures=textures)
    obj['buffers'][0]['byteLength']=len(data)
    header=json.dumps(obj,separators=(',',':')).encode();header+=b' '*(-len(header)%4)
    return struct.pack('<4sII',b'glTF',2,28+len(header)+len(data))+struct.pack('<I4s',len(header),b'JSON')+header+struct.pack('<I4s',len(data),b'BIN\0')+data

def dxf(p,r,state):
    state={'draft':'DRAFT','review':'IN REVIEW','approved':'APPROVED'}.get(state,state)
    out=[];offsets={};h={};cursor=0
    def emit(*pairs):out.extend(str(x) for x in pairs)
    def text(layer,x,y,value,size=200):
        emit(0,'TEXT',8,layer,10,x,20,y,40,size,1,str(value).replace('\n',' '))
    def line(layer,a,b):emit(0,'LINE',8,layer,10,a[0],20,a[1],11,b[0],21,b[1])
    emit(0,'SECTION',2,'HEADER',9,'$ACADVER',1,'AC1009',9,'$INSUNITS',70,4,0,'ENDSEC',0,'SECTION',2,'ENTITIES')
    for f,s in zip(p['faces'],[next(s for s in r['faces'] if s['face']==f['id']) for f in p['faces']]):
        fid=f['id'];offsets[fid]=cursor;h[fid]=s['height']
        text('TITLE',cursor,-900,f"{fid} / {r['resultId']} / {state} / mm",350)
        cur=cursor
        for j,span in enumerate(f['spans']):
            line('GRID',(cur,-400),(cur,s['height']+300));text('DIM',cur,-420,span);cur+=span
        z=0
        for fh in f.get('floors',p['floors']):
            line('LEVEL',(cursor-300,z),(cur,z));text('LEVEL',cursor-1200,z,z);z+=fh
        if p.get('intentPlanVersion')==1:
            if state!='APPROVED':text('TITLE',cursor,-1450,'DRAFT / DESIGN COORDINATION ONLY',300)
            contour=f.get('outline') or [[0,0],[s['width'],0],[s['width'],s['height']],[0,s['height']]]
            for a,b in edges([[cursor+u,h[fid]-v] for u,v in contour]):line('WALL',a,b)
        for feat in f.get('features',[]):
            points=[[cursor+u,h[fid]-v] for u,v in feat['poly']]
            layer='F_'+feat['kind']
            if p.get('intentPlanVersion')==1:
                if feat['kind'] in ('opening','band','entrance','berth','slope') or (feat['kind']=='smoke' and feat.get('physicalHole')):layer='OPENING'
                elif feat['kind'] in ('logo','ramp'):layer=feat['kind'].upper()
            for a,b in edges(points):line(layer,a,b)
        cursor+=s['width']+4000
    palette={'Silver':9,'Slate Navy':5,'White':7,'Electric Blue':5,'Dark Gray':8,'Medium Gray':9,'Column':8}
    for a in r['pieces']:
        pts=[[offsets[a['face']]+x,h[a['face']]-y] for x,y in a['poly']]
        for j in range(1,len(pts)-1):
            emit(0,'SOLID',8,'FIN_'+a['finish'].replace(' ','_'),62,palette[a['finish']])
            for k,pt in enumerate([pts[0],pts[j],pts[j+1],pts[j+1]]):emit(10+k,pt[0],20+k,pt[1])

        text('PANEL_ID',*pts[0],a['id'],65)
    for seam in r.get('seams',[]):
        fid=seam['face']
        for seg in seam['segments']:line('PANEL',*[[offsets[fid]+x,h[fid]-y] for x,y in seg])
    for a in r['labels']:text('SIGN',offsets[a['face']]+a['poly'][0][0],h[a['face']]-a['poly'][0][1],a['text'],350)
    for a in r['trims']:line('TRIM',*[[offsets[a['face']]+x,h[a['face']]-y] for x,y in a['points']])
    emit(0,'ENDSEC',0,'EOF')
    # R12 uses the local codepage; preserve non-ASCII signs with AutoCAD escapes.
    return ('\r\n'.join(out)+'\r\n').encode('ascii','backslashreplace').replace(b'\\u',b'\\U+')
