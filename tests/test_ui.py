import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from bot import Bot, Store, Source, RemoteError
from engine import analyze
from test_radar import B, F
from ui import Interface, nav
from card import render, welcome
from PIL import Image
from io import BytesIO

class UIFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        b=copy.deepcopy(B);b['events'][0]['deadline_time']=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
        b['elements']=[dict(b['elements'][0],id=i,web_name=f'Player {i}',element_type=(i%4)+1) for i in range(1,25)]
        self.report=analyze(b,[F]);source=Source();source.load=lambda:(b,[F],self.report['updated']);source.report=lambda gw=None:self.report
        self.bot=Bot('fake',Store(self.tmp.name+'/db.sqlite'),source);self.calls=[]
        self.bot.api=lambda method,payload:self.calls.append((method,payload))
    def validate(self):
        for method,payload in self.calls:
            if 'text' in payload:self.assertLess(len(payload['text'].encode('utf-16-le'))//2,4096)
            for row in payload.get('reply_markup',{}).get('inline_keyboard',[]):
                for btn in row:self.assertLessEqual(len(btn['callback_data'].encode()),64)
    def test_screens_and_roundtrip_navigation(self):
        ui=self.bot.ui
        for data in ['ui:home','ui:overview','ui:weeks','ui:fixtures','ui:settings','ui:method','ui:history',nav('gw',5),nav('budget',5,3,7.5),nav('differentials',5),nav('captain',5)]:
            ui.dispatch(1,data,20)
        self.validate()
        ui.listing(1,page=1,mid=20)
        player_button=self.calls[-1][1]['reply_markup']['inline_keyboard'][0][0]
        ui.dispatch(1,player_button['callback_data'],20)
        self.assertIn('المواجهات القادمة',self.calls[-1][1]['text'])
        back=self.calls[-1][1]['reply_markup']['inline_keyboard'][0][0]
        ui.dispatch(1,back['callback_data'],20)
        self.assertIn('صفحة 2',self.calls[-1][1]['text'])
    def test_callback_acknowledged_before_screen(self):
        self.bot.handle({'callback_query':{'id':'cb1','from':{'id':1},'data':'ui:home','message':{'message_id':20,'text':'previous','chat':{'id':1,'type':'private'}}}})
        self.assertEqual([c[0] for c in self.calls],['answerCallbackQuery','editMessageText'])
    def test_external_text_escaped(self):
        self.report['players'][0]['name']='<b>Fake & name</b>'
        self.bot.ui.listing(1)
        self.assertIn('&lt;b&gt;Fake &amp; name&lt;/b&gt;',self.calls[-1][1]['text'])
    def test_empty_and_stale_pages(self):
        self.bot.ui.listing(1,price=.1,page=99)
        self.assertIn('لا توجد خيارات',self.calls[-1][1]['text'])
        self.assertIn('صفحة 1 من 1',self.calls[-1][1]['text'])
    def test_unchanged_edit_does_not_duplicate(self):
        self.bot.api=lambda m,p:(_ for _ in ()).throw(RemoteError(400,not_modified=True))
        self.assertIsNone(self.bot.ui.home(1,20))
    def test_subscription_buttons_idempotent(self):
        self.bot.ui.dispatch(1,'ui:subscribe',20);self.bot.ui.dispatch(1,'ui:subscribe',20)
        self.assertEqual(self.bot.store.db.execute('SELECT COUNT(*) FROM chats').fetchone()[0],1)
        self.bot.ui.dispatch(1,'ui:stop',20)
        self.assertEqual(self.bot.store.db.execute('SELECT COUNT(*) FROM chats').fetchone()[0],0)
    def test_card_assets_and_empty_roster(self):
        for data,size in [(render(self.report),(1080,1640)),(welcome(),(1080,600)),(render(dict(self.report,players=[])),(1080,1640))]:
            self.assertEqual(Image.open(BytesIO(data)).size,size)
    def test_welcome_caption_fits_and_removes_old_keyboard(self):
        photos=[];self.bot.send_image=lambda *args:photos.append(args)
        self.bot.handle({'message':{'chat':{'id':1,'type':'private'},'from':{'id':1},'text':'/start'}})
        self.assertTrue(self.calls[0][1]['reply_markup']['remove_keyboard'])
        self.assertLess(len(photos[0][2].encode('utf-16-le'))//2,1024)
    def test_scheduled_digest_is_compact(self):
        for kind in ['24h','1h']:
            self.assertLess(len(self.bot.ui.digest(self.report,kind)),1500)

if __name__=='__main__':unittest.main()
