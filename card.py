"""RADARATI matchweek editorial cards. All numbers come from the analysis report."""
from io import BytesIO
import math
import os
from PIL import Image, ImageDraw, ImageFont
from engine import POSITIONS, select, utc
from zoneinfo import ZoneInfo

BG='#091522'; PANEL='#132535'; LINE='#284253'; INK='#eef3e8'; MUTED='#9aafbb'; LIME='#ccfa68'

class Canvas:
    def __init__(self,w=1080,h=1640):
        self.im=Image.new('RGB',(w,h),BG);self.d=ImageDraw.Draw(self.im)
        self.font=os.getenv('FONT_PATH','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    def text(self,x,y,value,size=26,color=INK,right=False,width=None):
        value=str(value)
        while True:
            f=ImageFont.truetype(self.font,size)
            if not width or self.d.textlength(value,font=f)<=width or size<=16:break
            size-=1
        if width and self.d.textlength(value,font=f)>width:
            while value and self.d.textlength(value+'…',font=f)>width:value=value[:-1]
            value+='…'
        self.d.text((x,y),value,font=f,fill=color,anchor='ra' if right else 'la',direction='rtl' if right else 'ltr')
    def box(self,xy,fill=PANEL,radius=24,outline=None):self.d.rounded_rectangle(xy,radius,fill=fill,outline=outline,width=2)
    def png(self):
        b=BytesIO();self.im.save(b,format='PNG',optimize=True);return b.getvalue()
    def radar(self,cx,cy,r=100):
        for step in (.33,.66,1):
            a=r*step;self.d.ellipse((cx-a,cy-a,cx+a,cy+a),outline=LINE,width=2)
        self.d.line((cx-r,cy,cx+r,cy),fill=LINE,width=1)
        self.d.line((cx,cy-r,cx,cy+r),fill=LINE,width=1)
        self.d.pieslice((cx-r,cy-r,cx+r,cy+r),280,335,fill='#274133')
        self.d.line((cx,cy,cx+int(r*.9),cy-int(r*.42)),fill=LIME,width=3)
        for dx,dy in [(28,-30),(-46,20),(66,-20)]:self.d.ellipse((cx+dx-5,cy+dy-5,cx+dx+5,cy+dy+5),fill=LIME)

def render(report):
    c=Canvas();d=c.d;gw=report['event']['id']
    # Editorial masthead and index strip.
    c.text(48,42,'RADARATI',28,LIME)
    c.text(1032,28,'راداراتي',60,right=True)
    c.text(1032,107,'اقرأ الجولة. اختر بثقة.',25,MUTED,True)
    d.line((48,162,1032,162),fill=LINE,width=2)
    c.text(48,182,f'MATCHWEEK {gw:02}',20,MUTED)
    c.text(1032,178,'دليل اختيارات الجولة',26,INK,True)
    # Captain feature.
    c.box((48,237,1032,610),fill=LIME)
    c.text(992,257,'اختيار الشارة',29,BG,True)
    captains=select(report,'captain');captain=captains[0] if captains else None
    c.text(81,271,'CAPTAIN / 01',18,'#3b512c')
    if captain:
        p=captain
        c.text(82,324,p['name'],64,BG,width=680)
        c.text(85,412,f"{p['team']}   /   £{p['price']:.1f}m",33,BG)
        c.text(989,452,'مؤشر الترشيح',19,'#3b512c',True)
        c.text(826,476,f"{p['score']:.1f}",54,BG)
        c.text(84,494,' + '.join(g['opponent']+(' [H]' if g['home'] else ' [A]') for g in p['fixtures']),24,BG,width=670)
        c.text(988,559,'مرشح وفق الأداء والدقائق؛ راجع أخبار التشكيل',22,'#3b512c',True,width=900)
        # A restrained captain badge, separate from the score.
        d.ellipse((880,320,990,430),outline=BG,width=3)
        c.text(910,332,'C',60,BG)
    else:
        c.text(990,365,'لا يوجد مرشح كابتن مؤهل حاليًا',36,BG,True,width=860)
    c.text(1032,638,'أفضل ٣ في كل مركز',30,INK,True)
    c.text(48,645,'THE SHORTLIST',19,MUTED)
    # Four independent positional shortlists; these are not a legal XI.
    for i,(pos,label) in enumerate(POSITIONS.items()):
        x=48+(i%2)*506;y=700+(i//2)*345;w=478
        c.box((x,y,x+w,y+321),outline=LINE)
        c.text(x+24,y+21,['GK','DEF','MID','FWD'][i],18,LIME)
        c.text(x+w-23,y+16,label,28,INK,True)
        c.text(x+24,y+61,'اللاعب',16,MUTED)
        c.text(x+280,y+61,'السعر',16,MUTED)
        c.text(x+w-24,y+61,'المؤشر',16,MUTED,True)
        players=select(report,pos=pos)[:3]
        for j,p in enumerate(players):
            yy=y+96+j*70
            c.text(x+24,yy,p['name'],25,INK,width=241)
            c.text(x+24,yy+31,p['team'],15,MUTED)
            c.text(x+281,yy,f"£{p['price']:.1f}",24,INK)
            c.text(x+w-24,yy,f"{p['score']:.1f}",24,LIME,True)
            if j<2:d.line((x+24,yy+59,x+w-24,yy+59),fill=LINE,width=1)
        if not players:c.text(x+w-24,y+142,'لا توجد خيارات مؤهلة',25,MUTED,True,width=415)
    # Deadline and provenance.
    c.box((48,1404,1032,1500),fill='#1f3444')
    end=utc(report['event']['deadline_time']).astimezone(ZoneInfo('Asia/Muscat'))
    c.text(1005,1420,'إغلاق الجولة · توقيت عُمان',22,INK,True)
    c.text(76,1430,end.strftime('%d/%m/%Y  ·  %H:%M'),31,LIME)
    c.text(1032,1524,'المؤشر / ١٠٠ للمقارنة، وليس توقعًا للنقاط',22,MUTED,True)
    c.text(1032,1561,'قوائم مستقلة · H أرضه / A خارج · أسعار اللعبة الافتراضية',19,MUTED,True)
    updated=utc(report['updated']).astimezone(ZoneInfo('Asia/Muscat')).strftime('%d %b %Y / %H:%M +04')
    c.text(48,1604,'@RadaratiBot  ·  '+updated,16,MUTED)
    return c.png()

def welcome():
    c=Canvas(1080,600);d=c.d
    c.radar(210,295,148)
    c.text(1005,96,'RADARATI',24,LIME,right=True)
    c.text(1005,157,'راداراتي',89,INK,True)
    c.text(1005,286,'اقرأ الجولة. اختر بثقة.',36,LIME,True)
    c.text(1005,375,'مراكز  /  أسعار  /  كابتن  /  مواجهات',26,MUTED,True)
    d.line((75,493,1005,493),fill=LINE,width=2)
    c.text(75,526,'FANTASY PREMIER LEAGUE',20,MUTED)
    c.text(1005,522,'دليلك للجولة القادمة',23,INK,True)
    return c.png()
