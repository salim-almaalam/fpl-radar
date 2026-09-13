"""One-process Telegram bot; standard-library HTTP + SQLite, Pillow for cards."""
import argparse
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone
from engine import analyze, next_event, report_text, select, utc, POSITIONS
from card import render, welcome
from ui import Interface, h, home_button

LOG = logging.getLogger('radar')
FPL = 'https://fantasy.premierleague.com/api/'

class RemoteError(Exception):
    def __init__(self, code=0, retry_after=5, not_modified=False):
        self.code=code; self.retry_after=retry_after; self.not_modified=not_modified
        super().__init__(f'Remote request failed ({code})')  # Never log token-bearing URLs.

def request_json(url, payload=None, timeout=25, headers=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(url, data=body, headers=headers or {'User-Agent':'FPLRadar/1.0','Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        retry=5; not_modified=False
        try:
            detail=json.loads(e.read())
            retry=int(detail.get('parameters',{}).get('retry_after',5))
            not_modified='message is not modified' in detail.get('description','').lower()
        except (ValueError,TypeError): pass
        raise RemoteError(e.code,retry,not_modified) from None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        raise RemoteError() from None

class Source:
    def __init__(self):
        self.cached=None; self.at=0
    def load(self):
        if self.cached and time.monotonic()-self.at < 300:
            return self.cached
        b=request_json(FPL+'bootstrap-static/')
        f=request_json(FPL+'fixtures/')
        if not isinstance(b,dict) or not all(k in b for k in ('events','elements','teams')) or not isinstance(f,list):
            raise RemoteError()
        self.cached=(b,f,datetime.now(timezone.utc).isoformat()); self.at=time.monotonic()
        return self.cached
    def report(self, gw=None):
        b,f,updated=self.load()
        event=None
        if gw is not None:
            event=next((e for e in b['events'] if e['id']==gw),None)
            if event is None: raise ValueError('رقم الجولة غير موجود.')
        r=analyze(b,f,event); r['updated']=updated
        return r

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY, subscribed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sent(chat INTEGER, season TEXT, gw INTEGER, kind TEXT, PRIMARY KEY(chat,season,gw,kind));
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS reports(season TEXT,gw INTEGER,payload TEXT,PRIMARY KEY(season,gw));
        '''); self.db.commit()
    def set(self,key,value):
        self.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,str(value)));self.db.commit()
    def get(self,key,default='0'):
        row=self.db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        return row[0] if row else default
    def subscribe(self,chat):
        self.db.execute('INSERT OR IGNORE INTO chats VALUES(?,?)',(chat,datetime.now(timezone.utc).isoformat()));self.db.commit()
    def stop(self,chat):
        self.db.execute('DELETE FROM chats WHERE id=?',(chat,));self.db.commit()
    def archive(self,r,season):
        self.db.execute('INSERT OR REPLACE INTO reports VALUES(?,?,?)',(season,r['event']['id'],json.dumps(r,ensure_ascii=False)));self.db.commit()

def notification_kind(event, now):
    left=(utc(event['deadline_time'])-now).total_seconds()
    if 0 < left <= 3600: return '1h'
    if 3600 < left <= 86400: return '24h'
    return None

HELP='''📡 أهلًا بك في رادار الجولة
ترشيحات الفانتازي حسب المركز والسعر ومباريات الجولة.

/gw — التقرير القادم
/gw 6 — تحليل جولة مستقبلية محددة
/picks MID 7.5 — لاعبو الوسط حتى £7.5m
المراكز: GK / DEF / MID / FWD
/captain — خيارات الكابتن
/budget — خيارات اقتصادية حسب المركز
/differentials — ملكية أقل من 10%
/fixtures — مباريات أفضل الخيارات خلال 3 جولات
/card — إنفوجرافيك الجولة
/subscribe — تقرير قبل الإغلاق بـ24 ساعة وتذكير قبل ساعة
/stop — إيقاف التنبيهات
/history — آخر تقرير محفوظ (مع تاريخ بياناته)
/method — طريقة التحليل
/delete — حذف بيانات اشتراكك

اضغط الأزرار أو أرسل أحد الأوامر.'''
METHOD='''الترتيب مؤشر إرشادي من 100، وليس توقعًا معايرًا للنقاط:
32% فورمة، 22% نقاط/مباراة، 18% حصة دقائق، 18% صعوبة وعدد مباريات الجولة، 10% مؤشرات أساسية حسب المركز. تضرب النتيجة في نسبة الإتاحة من المصدر.
الحارس والمدافع: xGC ومساهمة هجومية؛ الوسط والمهاجم: xGI/90.
تُستبعد حالات الإصابة والإيقاف وعدم الإتاحة، ونسبة مشاركة أقل من 75%، ومن ليس لديه دقائق أو مباراة في الجولة.
نسبة المشاركة غير المحددة تُعامل حسابيًا بـ100%، وتُعرض للمستخدم كغير محددة. للجولات الأبعد تُستخدم حالة الإتاحة الحالية دون توقع الإصابات.
الكابتن: وسط/هجوم، إتاحة 100%، حالة متاح، وحصة دقائق ≥65%.
الدقائق موسمية تقريبية وليست توقع تشكيل. القادمون الجدد قد لا يظهرون. الثقة محدودة مع قلة المباريات. الملكية المنخفضة لا تعني تلقائيًا أفضلية.
القيمة = المؤشر ÷ السعر؛ حدود الاقتصاد GK/DEF=5، MID=6.5، FWD=7.
بيانات FPL قد تتأخر أو تتغير واجهتها. لا يستخدم البوت نموذج ذكاء اصطناعي مدفوعًا ولا ينفذ انتقالات.'''
KEYBOARD={'keyboard':[['/gw','/card'],['/captain','/budget'],['/differentials','/fixtures'],['/subscribe','/stop']],'resize_keyboard':True}

class Bot:
    def __init__(self,token,store,source):
        self.url='https://api.telegram.org/bot'+token+'/'
        self.store=store;self.source=source;self.last={};self.ui=Interface(self)
        self.allowed={int(x) for x in os.getenv('ALLOWED_USER_IDS','').split(',') if x.strip()}
    def api(self,method,payload=None):
        result=request_json(self.url+method,payload,timeout=40)
        if not result.get('ok'): raise RemoteError(result.get('error_code',0))
        return result['result']
    def say(self,chat,text,keyboard=False):
        # Split by line, retain Telegram's UTF-16 message length constraint.
        chunks=[]; chunk=''
        for line in text.splitlines(keepends=True):
            if len((chunk+line).encode('utf-16-le'))//2 > 3500:
                chunks.append(chunk);chunk=''
            chunk+=line
        if chunk: chunks.append(chunk)
        for part in chunks:
            payload={'chat_id':chat,'text':part}
            if keyboard: payload['reply_markup']=KEYBOARD
            self.api('sendMessage',payload)
    def send_image(self,chat,data,caption,keyboard):
        boundary=uuid.uuid4().hex
        fields={'chat_id':str(chat),'caption':caption,'parse_mode':'HTML','reply_markup':json.dumps({'inline_keyboard':keyboard},ensure_ascii=False)}
        body=b''
        for key,value in fields.items():
            body+=(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode()
        body+=(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="radar.png"\r\nContent-Type: image/png\r\n\r\n').encode()+data+f'\r\n--{boundary}--\r\n'.encode()
        req=urllib.request.Request(self.url+'sendPhoto',data=body,headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
        try:
            with urllib.request.urlopen(req,timeout=40) as response:result=json.load(response)
            if not result.get('ok'):raise RemoteError(result.get('error_code',0))
            return result.get('result')
        except urllib.error.HTTPError as e:raise RemoteError(e.code) from None
        except (urllib.error.URLError,TimeoutError,OSError,ValueError):raise RemoteError() from None
    def photo(self,chat,r):
        from ui import button
        return self.send_image(chat,render(r),f"📡 <b>راداراتي · الجولة {r['event']['id']}</b>\nبطاقتك للمشاركة · مؤشر مقارن، وليس نقاطًا متوقعة.",[[button('🏟 استكشف اللاعبين',f"ui:overview:{r['event']['id']}"),home_button()]])
    def report(self,gw=None):
        r=self.source.report(gw)
        b,_,_=self.source.load();season=b['events'][0]['deadline_time'][:4]
        self.store.archive(r,season)
        return r
    def handle(self,update):
        callback=update.get('callback_query')
        msg=callback.get('message',{}) if callback else update.get('message',{})
        chat=msg.get('chat',{}).get('id')
        if not chat or msg.get('chat',{}).get('type')!='private':return
        actor=(callback or msg).get('from',{}).get('id')
        if self.allowed and actor not in self.allowed:return
        if callback:
            # Acknowledge before data fetching so Telegram stops its spinner.
            self.api('answerCallbackQuery',{'callback_query_id':callback['id']})
        if time.monotonic()-self.last.get(chat,0)<.7:return
        self.last[chat]=time.monotonic()
        if len(self.last)>10000:self.last={chat:self.last[chat]}
        mid=msg.get('message_id') if callback and msg.get('text') else None
        try:
            if callback:
                data=callback.get('data','')
                if not data.startswith('ui:') or len(data.encode())>64:raise ValueError('اختيار غير صالح.')
                return self.ui.dispatch(chat,data,mid)
            raw=msg.get('text','').split()
            if not raw:return
            cmd=raw[0].split('@')[0].lower()
            if cmd=='/start':
                self.api('sendMessage',{'chat_id':chat,'text':'📡 مرحبًا بك في راداراتي — اختر من القائمة أدناه.','reply_markup':{'remove_keyboard':True}})
                return self.ui.home(chat,with_banner=True)
            if cmd in ('/help','/menu'):return self.ui.home(chat)
            if cmd=='/gw':return self.ui.overview(chat,int(raw[1]) if len(raw)>1 else 0)
            if cmd in ('/captain','/budget','/differentials'):return self.ui.listing(chat,cmd[1:])
            if cmd=='/picks':
                if len(raw)==1:return self.ui.listing(chat)
                if len(raw)!=3:raise ValueError('مثال: /picks MID 7.5')
                pos={'GK':1,'DEF':2,'MID':3,'FWD':4}.get(raw[1].upper())
                price=float(raw[2])
                if not pos or not 0<price<=25:raise ValueError('اختر GK أو DEF أو MID أو FWD وسعرًا حتى 25.')
                return self.ui.listing(chat,pos=pos,price=price)
            if cmd in ('/subscribe','/stop','/history','/method'):return self.ui.dispatch(chat,'ui:'+cmd[1:])
            if cmd=='/card':return self.ui.dispatch(chat,'ui:card:0')
            if cmd=='/fixtures':return self.ui.fixtures(chat)
            if cmd=='/delete':
                self.store.stop(chat)
                self.store.db.execute('DELETE FROM sent WHERE chat=?',(chat,));self.store.db.commit();self.last.pop(chat,None)
                return self.ui.show(chat,'تم حذف بيانات اشتراكك وسجل تنبيهاتك.',[[home_button()]])
            return self.ui.home(chat)
        except (ValueError,IndexError):
            return self.ui.show(chat,'<b>تعذر فتح هذا الاختيار</b>\nربما أغلقت الجولة أو تغيّرت حالة اللاعب. افتح الرئيسية لاختيار تقرير جديد.\nللبحث: <code>/picks MID 7.5</code>',[[home_button()]],mid)
        except RemoteError:
            return self.ui.show(chat,'<b>☁️ تعذر الاتصال مؤقتًا</b>\nحاول بعد قليل. يمكنك الرجوع للأرشيف لمشاهدة تقرير محفوظ مع تاريخه.',[[home_button()]],mid)
    def schedule(self):
        if not self.store.db.execute('SELECT 1 FROM chats LIMIT 1').fetchone(): return
        b,_,_=self.source.load();now=datetime.now(timezone.utc);e=next_event(b,now)
        if not e: return
        kind=notification_kind(e,now)
        if not kind:return
        season=b['events'][0]['deadline_time'][:4]
        chats=self.store.db.execute('SELECT id FROM chats WHERE NOT EXISTS (SELECT 1 FROM sent WHERE sent.chat=chats.id AND season=? AND gw=? AND kind=?)',(season,e['id'],kind)).fetchall()
        r=None
        for (chat,) in chats:
            # Recheck deadline so a long send queue cannot send after closing.
            if notification_kind(e,datetime.now(timezone.utc))!=kind: break
            try:
                if r is None:r=self.report()
                prefix='⏰ نافذة التقرير قبل الإغلاق بـ24 ساعة\n' if kind=='24h' else '⏰ أقل من ساعة على إغلاق الجولة؛ راجع التشكيل\n'
                self.say(chat,prefix+self.ui.digest(r,kind))
                self.store.db.execute('INSERT OR IGNORE INTO sent VALUES(?,?,?,?)',(chat,season,e['id'],kind));self.store.db.commit()
                time.sleep(.15)
            except RemoteError as err:
                if err.code==403:self.store.stop(chat)
                elif err.code==429:time.sleep(min(err.retry_after,60));break
                else:LOG.warning('Notification failed; will retry')
    def run(self):
        self.api('getMe')
        if self.api('getWebhookInfo').get('url'):
            raise ValueError('هناك Webhook مفعّل لهذا التوكن. أوقفه قبل تشغيل نسخة polling.')
        self.api('setMyCommands',{'commands':[{'command':c,'description':d} for c,d in [('gw','تقرير الجولة'),('card','بطاقة الجولة'),('picks','بحث بالمركز والسعر'),('captain','مرشحو الكابتن'),('budget','خيارات اقتصادية'),('differentials','قليلو الملكية'),('fixtures','المباريات القادمة'),('subscribe','تفعيل التنبيهات'),('stop','إيقاف التنبيهات'),('history','تقرير محفوظ'),('method','منهجية التحليل'),('help','المساعدة'),('delete','حذف بياناتي')]]})
        tick=0
        LOG.info('Bot running | RADARATI UI 2.0')
        while True:
            try:
                updates=self.api('getUpdates',{'offset':int(self.store.get('offset')),'timeout':20,'allowed_updates':['message','callback_query']})
                for u in updates:
                    try:self.handle(u)
                    except Exception:LOG.warning('Command failed (details suppressed to protect credentials)')
                    self.store.set('offset',u['update_id']+1)
                if time.monotonic()-tick>=60:
                    tick=time.monotonic()
                    try:self.schedule()
                    except Exception:LOG.warning('Scheduled refresh failed; retrying next minute')
            except RemoteError as err:
                LOG.warning('Polling unavailable (%s)',err.code)
                time.sleep(min(max(5,err.retry_after),60))

def load_env():
    if Path('.env').exists():
        for line in Path('.env').read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))

def main():
    load_env();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    parser=argparse.ArgumentParser();parser.add_argument('--preview',action='store_true');parser.add_argument('--data-dir');args=parser.parse_args()
    if args.preview:
        if args.data_dir:
            b=json.loads(Path(args.data_dir,'bootstrap-static.json').read_text());f=json.loads(Path(args.data_dir,'fixtures.json').read_text());r=analyze(b,f)
        else:r=Source().report()
        Path('examples').mkdir(exist_ok=True)
        Path('examples/radar.png').write_bytes(render(r));Path('examples/report.txt').write_text(report_text(r),encoding='utf-8')
        Path('examples/report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Created examples/radar.png and report.txt / report.json');return
    token=os.getenv('TELEGRAM_BOT_TOKEN','').strip()
    if not token or token=='replace_me':raise SystemExit('Set TELEGRAM_BOT_TOKEN in .env first.')
    Bot(token,Store(os.getenv('DATABASE_PATH','data/radar.sqlite')),Source()).run()

if __name__=='__main__':main()
