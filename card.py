"""Exact, data-driven PNG, no generated or invented statistics."""
from io import BytesIO
import os
from PIL import Image, ImageDraw, ImageFont
from engine import POSITIONS, select, utc
from zoneinfo import ZoneInfo

def render(report):
    im = Image.new('RGB', (1080, 1480), '#080f20')
    d = ImageDraw.Draw(im)
    font = os.getenv('FONT_PATH', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    def write(x, y, s, size=26, color='#ffffff', right=False):
        f = ImageFont.truetype(font, size)
        # RAQM shapes Arabic and handles mixed English/numbers correctly.
        d.text((x,y), str(s), font=f, fill=color, anchor='ra' if right else 'la', direction='rtl' if right else 'ltr')
    d.rounded_rectangle((42, 40, 1038, 235), 26, fill='#112b39')
    write(80, 66, 'FPL / RADAR', 24, '#51f0b2')
    write(995, 102, 'رادار الجولة', 56, right=True)
    write(80, 125, f"GW {report['event']['id']:02}", 62)
    deadline = utc(report['event']['deadline_time']).astimezone(ZoneInfo('Asia/Muscat')).strftime('%Y-%m-%d  %H:%M')
    write(995, 194, 'الإغلاق بتوقيت عُمان', 21, '#abc2d1', True)
    write(80, 194, deadline, 21, '#abc2d1')
    for i, (pos, label) in enumerate(POSITIONS.items()):
        y = 267 + i * 222
        d.rounded_rectangle((42, y, 1038, y+202), 18, fill='#131e33')
        write(994, y+15, label, 29, '#51f0b2', True)
        rows = [p for p in report['players'] if p['position'] == pos][:3]
        if not rows:
            write(994, y+80, 'لا توجد خيارات مؤهلة', 23, right=True)
        for x,label in [(70,'PLAYER'),(405,'CLUB'),(530,'PRICE'),(730,'VS'),(935,'INDEX')]:
            write(x,y+52,label,13,'#70839d')
        for j, p in enumerate(rows):
            yy = y+78+j*39
            name = p['name'] if len(p['name']) <= 22 else p['name'][:21]+'…'
            write(70, yy, name, 26)
            write(405, yy, p['team'], 22, '#abc2d1')
            write(530, yy, f"£{p['price']:.1f}m", 26)
            opponents = ' + '.join(g['opponent'] for g in p['fixtures'])
            write(730, yy, opponents, 19, '#abc2d1')
            write(935, yy, str(p['score']), 26, '#51f0b2')
    y=1180
    d.rounded_rectangle((42,y,1038,y+145),18,fill='#483650')
    write(995,y+16,'اختيار الكابتن',28,'#f3c7ff',True)
    captains = select(report,'captain')
    if captains:
        p=captains[0]
        write(76,y+66,f"{p['name']}  /  £{p['price']:.1f}m",35)
        write(995,y+109,'وفق المؤشر ودقائق اللعب؛ راجع أخبار التشكيل',19,'#e0c9e5',True)
    write(995,1350,'الرقم الأخضر: مؤشر ترشيح / 100، وليس نقاطًا متوقعة',22,'#9faec2',True)
    write(995,1390,'ترشيحات مستقلة · أسعار افتراضية داخل اللعبة',22,'#9faec2',True)
    write(60,1442,report['updated'][:16].replace('T',' ')+' UTC · FPL data',18,'#70839d')
    out=BytesIO(); im.save(out,format='PNG'); return out.getvalue()
