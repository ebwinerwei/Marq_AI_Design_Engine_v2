"""Small self-contained numeric signage geometry for engineering GLB."""
from .geometry import bounds
DIGITS=['111101101101111','010110010010111','111001111100111','111001111001111','101101111001001','111100111001111','111100111101111','111001001001001','111101111101111','111101111001111']
def labels_as_quads(labels):
    for item in labels:
        if item['kind']!='berth':continue
        x,y,X,Y=bounds(item['poly']);width=min(X-x,(Y-y)*.55);height=width*.28
        x=(x+X-width)/2;y-=height
        yield item['face'],'Sign Black',(x,y,width,height),.015
        text=str(item['text']);unit=min(width/(len(text)*4+1),height/7)
        start=x+(width-unit*(len(text)*4-1))/2;top=y+(height-5*unit)/2
        for i,ch in enumerate(text):
            if not ch.isascii() or not ch.isdigit():continue
            for k,bit in enumerate(DIGITS[int(ch)]):
                if bit=='1':yield item['face'],'Sign White',(start+(i*4+k%3)*unit,top+k//3*unit,unit,unit),.02
