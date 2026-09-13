"""Arabic Telegram presentation layer: stateless inline navigation and escaped HTML."""
from html import escape
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from engine import select, POSITIONS, utc, fixture_text

VERSION='2.0'
ICONS={1:'🧤',2:'🛡',3:'🎯',4:'⚡'}
KINDS={'gw':'مرشحو الجولة','budget':'القيمة مقابل السعر','captain':'شارة الكابتن','differentials':'تحت الرادار'}

def h(value): return escape(str(value),quote=False)
def button(text,data): return {'text':text,'callback_data':data}
def markup(rows): return {'inline_keyboard':rows}
def home_button(): return button('⌂ الرئيسية','ui:home')
def nav(kind,gw,pos=0,price=0,page=0): return f'ui:list:{kind}:{gw}:{pos}:{price:g}:{page}'

def stamp(r):
    return utc(r['updated']).astimezone(ZoneInfo('Asia/Muscat')).strftime('%d/%m · %H:%M')
def deadline(r):
    dt=utc(r['event']['deadline_time']).astimezone(ZoneInfo('Asia/Muscat'))
    left=max(0,int((dt-datetime.now(timezone.utc)).total_seconds()))
    days,rem=divmod(left,86400);hours,rem=divmod(rem,3600);mins=rem//60
    remaining=f'{days} يوم · {hours} ساعة' if days else f'{hours} ساعة · {mins} دقيقة'
    return dt.strftime('%d/%m/%Y · %H:%M'),remaining

def reason(p):
    reasons=[]
    if len(p['fixtures'])>1:reasons.append('فرصتان في جولة مزدوجة' if len(p['fixtures'])==2 else 'أكثر من مباراة')
    if p['form']>=5:reasons.append('فورمة جيدة')
    if p['reliability']>=75:reasons.append('دقائق مرتفعة')
    if min((g['difficulty'] for g in p['fixtures']),default=5)<=2:reasons.append('مواجهة ميسّرة نسبيًا')
    return ' · '.join(reasons[:3]) or 'يتقدم نسبيًا في المؤشر المركب'

def shortlist(p,index):
    badge=['①','②','③'][index%3]
    warning=' · ⚠️ راجع الخبر' if p.get('news') else ''
    return (f"{badge} <b>{h(p['name'])}</b> · {h(p['team'])}\n"
            f"<b>£{p['price']:.1f}m</b>   |   مؤشر <b>{p['score']:.1f}</b>/100{warning}\n"
            f"{h(fixture_text(p))}\n<i>{h(reason(p))}</i>")

class Interface:
    def __init__(self,bot): self.bot=bot
    def show(self,chat,text,rows,mid=None):
        payload={'chat_id':chat,'text':text,'parse_mode':'HTML','reply_markup':markup(rows)}
        if mid:
            payload['message_id']=mid
            try:return self.bot.api('editMessageText',payload)
            except Exception as err:
                # Telegram returns 400 for unchanged/expired messages; fallback only
                # when a prior identical screen is not already on display.
                if getattr(err,'not_modified',False):return
                if getattr(err,'code',None)!=400:raise
                payload.pop('message_id')
        return self.bot.api('sendMessage',payload)
    def home(self,chat,mid=None,with_banner=False):
        text=('📡 <b>راداراتي</b>  /  RADARATI\n'
              '<i>اقرأ الجولة. اختر بثقة.</i>\n\n'
              'مساحتك لتحليل فانتازي الدوري الإنجليزي: ترشيحات واضحة، أسعار، ومواجهات في مكان واحد.\n\n'
              '<b>من أين نبدأ؟</b>\n'
              '🏟 الجولة — الأفضل في كل مركز\n'
              '© الكابتن — مرشحو الشارة\n'
              '💎 تحت الرادار — أسماء قليلة الملكية\n\n'
              '<i>تحليل للعبة المجانية · الأسعار من الميزانية الافتراضية.</i>')
        rows=[[button('🏟 استكشف الجولة','ui:overview')],
            [button('© الكابتن','ui:list:captain:0:0:0:0'),button('💰 اقتصادي','ui:list:budget:0:0:0:0')],
            [button('💎 تحت الرادار','ui:list:differentials:0:0:0:0'),button('🎨 بطاقة الجولة','ui:card:0')],
            [button('🔔 تنبيهاتي','ui:settings'),button('📁 الأرشيف','ui:history')],
            [button('🗓 المواجهات','ui:fixtures'),button('كيف نحلّل؟','ui:method')]]
        if with_banner:
            from card import welcome
            return self.bot.send_image(chat,welcome(),text,rows)
        return self.show(chat,text,rows,mid)
    def overview(self,chat,gw=0,mid=None):
        r=self.bot.report(gw or None);gw=r['event']['id'];end,left=deadline(r)
        text=f'🏟 <b>غرفة الجولة {gw:02}</b>\n\n⏳ {left} حتى الإغلاق\n<b>{end}</b> · عُمان\n\n'
        for pos,label in POSITIONS.items():
            rows=select(r,pos=pos)
            text+=f'{ICONS[pos]} <b>{label}</b>\n'
            if rows:
                p=rows[0];text+=f"{h(p['name'])} · £{p['price']:.1f}m · <b>{p['score']}</b>/100\n\n"
            else:text+='لا توجد خيارات مؤهلة\n\n'
        text+=f'<i>افتح المركز لمشاهدة البدائل وتفاصيل اللاعبين.\nآخر تحديث {stamp(r)} · عُمان\nالمؤشر للمقارنة، وليس نقاطًا متوقعة.</i>'
        keyboard=[[button('🧤 حراس',nav('gw',gw,1)),button('🛡 دفاع',nav('gw',gw,2))],
                  [button('🎯 وسط',nav('gw',gw,3)),button('⚡ هجوم',nav('gw',gw,4))],
                  [button('🎨 البطاقة',f'ui:card:{gw}'),button('© الكابتن',nav('captain',gw))],
                  [button('🗓 اختر جولة','ui:weeks'),home_button()]]
        return self.show(chat,text,keyboard,mid)
    def listing(self,chat,kind='gw',gw=0,pos=0,price=0,page=0,mid=None):
        if kind not in KINDS or pos not in range(5) or not 0<=price<=25 or not 0<=page<=100:raise ValueError('اختيار غير صالح؛ عد إلى الرئيسية.')
        r=self.bot.report(gw or None);gw=r['event']['id']
        players=select(r,kind,pos or None,price or None)
        pages=max(1,(len(players)+2)//3);page=min(page,pages-1);items=players[page*3:page*3+3]
        label=POSITIONS.get(pos,'كل المراكز');budget=f' · حتى £{price:g}m' if price else ''
        text=f"<b>{h(KINDS[kind])}</b>  /  GW {gw:02}\n{h(label)}{budget}\n\n"
        text+='\n\n'.join(shortlist(p,i) for i,p in enumerate(items)) or 'لا توجد خيارات ضمن هذا السعر. جرّب توسيع الميزانية.'
        text+=f'\n\n<i>صفحة {page+1} من {pages} · {len(players)} خيار\nمؤشر مقارن، وليس نقاطًا متوقعة. تحديث {stamp(r)} · عُمان</i>'
        keyboard=[[button(f"↗ {p['name']}",f"ui:player:{gw}:{p['id']}:{kind}:{pos}:{price:g}:{page}")] for p in items]
        arrows=[]
        if page>0:arrows.append(button('→ السابق',nav(kind,gw,pos,price,page-1)))
        if page+1<pages:arrows.append(button('التالي ←',nav(kind,gw,pos,price,page+1)))
        if arrows:keyboard.append(arrows)
        keyboard.append([button('🧤',nav(kind,gw,1,price)),button('🛡',nav(kind,gw,2,price)),button('🎯',nav(kind,gw,3,price)),button('⚡',nav(kind,gw,4,price)),button('الكل',nav(kind,gw,0,price))])
        keyboard.append([button('حتى 5',nav(kind,gw,pos,5)),button('حتى 7.5',nav(kind,gw,pos,7.5)),button('حتى 10',nav(kind,gw,pos,10)),button('أي سعر',nav(kind,gw,pos))])
        keyboard.append([button('🏟 الجولة',f'ui:overview:{gw}'),home_button()])
        return self.show(chat,text,keyboard,mid)
    def player(self,chat,gw,pid,kind,pos,price,page,mid=None):
        r=self.bot.report(gw);p=next((p for p in r['players'] if p['id']==pid),None)
        if not p:raise ValueError('تغيّرت حالة اللاعب ولم يعد ضمن الخيارات المؤهلة. افتح الجولة مجددًا.')
        chance=f"{p['chance']}%" if p.get('availability_known') else 'غير محددة من المصدر'
        text=(f"{ICONS[p['position']]} <b>{h(p['name'])}</b>\n{h(p['team'])} · {POSITIONS[p['position']]}\n\n"
              f"<b>£{p['price']:.1f}m</b>  |  مؤشر <b>{p['score']:.1f}/100</b>\n\n"
              f"<b>لماذا يظهر على الرادار؟</b>\n{h(reason(p))}\n\n"
              f"📈 الفورمة: <b>{p['form']:g}</b>\n🎯 نقاط/مباراة: <b>{p['ppg']:g}</b>\n"
              f"👥 الملكية: <b>{p['ownership']:g}%</b>\n⏱ حصة الدقائق الموسمية: <b>{p['reliability']}%</b>\n"
              f"🟢 إتاحة المشاركة: {chance}\n🔎 ثقة المؤشر: {p['confidence']}\n\n<b>المواجهات القادمة</b>\n")
        for outlook in p['outlook']:
            games=[]
            for g in outlook['games']:
                color='🟢' if g['difficulty']<=2 else ('🟡' if g['difficulty']==3 else '🔴')
                games.append(f"{color} {h(g['opponent'])} · {'أرضه' if g['home'] else 'خارج'} · {g['difficulty']:g}/5")
            text+=f"GW {outlook['gw']}  |  "+(' + '.join(games) or 'بلا مباراة مجدولة')+'\n'
        if p.get('news'):text+='\n⚠️ <b>خبر اللاعب</b>\n'+h(p['news'][:500])+'\n'
        text+=f'\n<i>الدقائق موسمية ولا تضمن بدء المباراة.\nآخر تحديث {stamp(r)} · عُمان</i>'
        return self.show(chat,text,[[button('↩ العودة للقائمة',nav(kind,gw,pos,price,page)),home_button()]],mid)
    def fixtures(self,chat,mid=None):
        r=self.bot.report();text='<b>🗓 خريطة المواجهات</b>\nأفضل خيارين من كل مركز · ثلاث جولات\n🟢 ١–٢ أسهل  🟡 ٣  🔴 ٤–٥ أصعب\n\n'
        for pos,label in POSITIONS.items():
            text+=f'<b>{ICONS[pos]} {label}</b>\n'
            for p in select(r,pos=pos)[:2]:
                text+=f"<b>{h(p['name'])}</b> · £{p['price']:.1f}m\n"
                for outlook in p['outlook']:
                    games=[]
                    for g in outlook['games']:
                        color='🟢' if g['difficulty']<=2 else ('🟡' if g['difficulty']==3 else '🔴')
                        games.append(f"{color}{h(g['opponent'])} {'H' if g['home'] else 'A'}")
                    text+=f"GW{outlook['gw']}  "+(' + '.join(games) or 'بلا مباراة')+'\n'
                text+='\n'
        text+='<i>H أرضه / A خارج · المواعيد قد تتغير.</i>'
        return self.show(chat,text,[[button('🏟 الجولة','ui:overview'),home_button()]],mid)
    def digest(self,r,kind):
        # Concise scheduled report; opt-in and delivery tracking stay in Bot.
        text=f"📡 راداراتي · الجولة {r['event']['id']}\n\n"
        if kind=='1h':
            for i,p in enumerate(select(r,'captain')[:3]):
                text+=f"{i+1}. {p['name']} · £{p['price']:.1f}m · مؤشر {p['score']}/100\n"
        else:
            for pos,label in POSITIONS.items():
                rows=select(r,pos=pos)
                if rows:
                    p=rows[0];text+=f"{ICONS[pos]} {label}\n{p['name']} · £{p['price']:.1f}m · مؤشر {p['score']}/100\n\n"
        return text+'افتح /gw للتفاصيل أو /card للبطاقة.\nالمؤشر مقارن؛ راجع أخبار التشكيل. /stop لإيقاف التنبيهات.'
    def settings(self,chat,mid=None):
        enabled=bool(self.bot.store.db.execute('SELECT 1 FROM chats WHERE id=?',(chat,)).fetchone())
        text=('<b>🔔 تنبيهاتك</b>\n\n'+('🟢 مفعّلة' if enabled else '⚪ متوقفة')+
              '\n\nتقرير قبل إغلاق الجولة بـ24 ساعة، وتذكير بالكابتن قبل ساعة.\nالموعد يتبع إغلاق الجولة الفعلي بتوقيت عُمان.')
        return self.show(chat,text,[[button('إيقاف التنبيهات' if enabled else 'تفعيل التنبيهات','ui:stop' if enabled else 'ui:subscribe')],[home_button()]],mid)
    def weeks(self,chat,mid=None):
        b,_,_=self.bot.source.load();now=datetime.now(timezone.utc)
        events=[e for e in b['events'] if utc(e['deadline_time'])>now][:6]
        rows=[[button(f"الجولة {e['id']}",f"ui:overview:{e['id']}")] for e in events]
        return self.show(chat,'<b>🗓 اختر الجولة</b>\n\nالجولات الأبعد تُحلّل بالأداء وحالة الإتاحة الحاليين. المواعيد قد تتغير.',rows+[[home_button()]],mid)
    def history(self,chat,mid=None):
        rows=self.bot.store.db.execute('SELECT season,gw,payload FROM reports ORDER BY season DESC,gw DESC LIMIT 8').fetchall()
        buttons=[[button(f"{season} · الجولة {gw}",f'ui:archive:{season}:{gw}')] for season,gw,_ in rows]
        return self.show(chat,'<b>📁 أرشيف الرادار</b>\n\nآخر نسخة محفوظة لكل جولة. البيانات تعود إلى تاريخ التقرير وليست تحديثًا مباشرًا.' if rows else '<b>📁 الأرشيف فارغ</b>\nافتح تقرير الجولة لحفظ أول نسخة.',buttons+[[home_button()]],mid)
    def archived(self,chat,season,gw,mid=None):
        import json
        row=self.bot.store.db.execute('SELECT payload FROM reports WHERE season=? AND gw=?',(season,gw)).fetchone()
        if not row:raise ValueError('التقرير غير موجود.')
        r=json.loads(row[0]);text=f'<b>📁 نسخة محفوظة · الجولة {gw}</b>\nبيانات بتاريخ {stamp(r)} · عُمان\n\n'
        for pos,label in POSITIONS.items():
            text+=f'<b>{ICONS[pos]} {label}</b>\n'
            text+='\n'.join(f"{h(p['name'])} · £{p['price']:.1f}m · {p['score']}/100" for p in select(r,pos=pos)[:2])+'\n\n'
        return self.show(chat,text+'<i>لقطة محفوظة؛ ليست توصية حديثة ولا تقييمًا لنتائج الجولة.</i>',[[button('↩ الأرشيف','ui:history'),home_button()]],mid)
    def dispatch(self,chat,data,mid=None):
        parts=data.split(':');action=parts[1]
        if action=='home':return self.home(chat,mid)
        if action=='overview':return self.overview(chat,int(parts[2]) if len(parts)>2 else 0,mid)
        if action=='list':return self.listing(chat,parts[2],int(parts[3]),int(parts[4]),float(parts[5]),int(parts[6]),mid)
        if action=='player':return self.player(chat,int(parts[2]),int(parts[3]),parts[4],int(parts[5]),float(parts[6]),int(parts[7]),mid)
        if action=='fixtures':return self.fixtures(chat,mid)
        if action=='settings':return self.settings(chat,mid)
        if action in ('subscribe','stop'):
            (self.bot.store.subscribe if action=='subscribe' else self.bot.store.stop)(chat)
            return self.settings(chat,mid)
        if action=='weeks':return self.weeks(chat,mid)
        if action=='history':return self.history(chat,mid)
        if action=='archive':return self.archived(chat,parts[2],int(parts[3]),mid)
        if action=='method':
            from bot import METHOD
            return self.show(chat,'<b>🔬 خلف الترشيح</b>\n\n'+h(METHOD),[[home_button()]],mid)
        if action=='card':
            r=self.bot.report(int(parts[2]) or None)
            return self.bot.photo(chat,r)
        raise ValueError('القائمة قديمة؛ افتح /start لتحديثها.')
