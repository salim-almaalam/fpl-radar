import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from engine import analyze, next_event, select
from bot import Store, Bot, notification_kind, RemoteError, Source

NOW=datetime(2026,9,13,tzinfo=timezone.utc)
E={'id':5,'deadline_time':'2026-09-18T17:30:00Z'}
P={'id':1,'web_name':'Player A','element_type':3,'team':1,'now_cost':65,'status':'a','minutes':270,'form':'5','points_per_game':'5','expected_goal_involvements_per_90':'.6','selected_by_percent':'5','chance_of_playing_next_round':None}
F={'id':1,'event':5,'team_h':1,'team_a':2,'team_h_difficulty':2,'team_a_difficulty':4,'finished':False}
B={'events':[E],'teams':[{'id':1,'short_name':'AAA'},{'id':2,'short_name':'BBB'}],'elements':[P]}

class Tests(unittest.TestCase):
    def test_price_and_form(self):
        p=analyze(B,[F],now=NOW)['players'][0]
        self.assertEqual(p['price'],6.5);self.assertEqual(p['form'],5)
    def test_blank_and_unassigned(self):
        self.assertEqual(analyze(B,[],now=NOW)['players'],[])
        f=dict(F,event=None)
        self.assertEqual(analyze(B,[f],now=NOW)['players'],[])
    def test_double_gameweek(self):
        single=analyze(B,[F],now=NOW)['players'][0]
        double=analyze(B,[F,dict(F,id=2)],now=NOW)['players'][0]
        self.assertEqual(len(double['fixtures']),2);self.assertGreater(double['score'],single['score'])
    def test_unavailable(self):
        for patch in ({'status':'i'},{'status':'s'},{'chance_of_playing_next_round':50},{'minutes':0},{'can_select':False}):
            b=copy.deepcopy(B);b['elements'][0].update(patch)
            self.assertFalse(analyze(b,[F],now=NOW)['players'])
    def test_unknown_availability_is_not_captain_if_doubtful(self):
        b=copy.deepcopy(B);b['elements'][0]['status']='d'
        self.assertFalse(select(analyze(b,[F],now=NOW),'captain'))
    def test_no_historical_leakage(self):
        with self.assertRaises(ValueError):analyze(B,[F],E,now=NOW+timedelta(days=20))
        self.assertIsNone(next_event(B,NOW+timedelta(days=20)))
    def test_budget_filter(self):
        r=analyze(B,[F],now=NOW)
        self.assertEqual(len(select(r,'budget')),1)
        self.assertEqual(select(r,max_price=6),[])
    def test_notification_boundaries(self):
        deadline=datetime(2026,9,18,17,30,tzinfo=timezone.utc)
        for seconds,expected in [(86401,None),(86400,'24h'),(3601,'24h'),(3600,'1h'),(1,'1h'),(0,None),(-1,None)]:
            self.assertEqual(notification_kind(E,deadline-timedelta(seconds=seconds)),expected)
    def test_persistent_opt_out_and_duplicate_subscription(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(tmp+'/test.sqlite');s.subscribe(1);s.subscribe(1)
            self.assertEqual(s.db.execute('SELECT count(*) FROM chats').fetchone()[0],1)
            s.set('offset',321);s.db.close();s=Store(tmp+'/test.sqlite');self.assertEqual(s.get('offset'),'321')
            s.stop(1);self.assertFalse(s.db.execute('SELECT * FROM chats').fetchall())
    def test_telegram_transport_private_and_utf16(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot=Bot('fake',Store(tmp+'/test.sqlite'),None);calls=[]
            bot.api=lambda method,payload:calls.append((method,payload))
            bot.handle({'message':{'chat':{'id':1,'type':'group'},'text':'/subscribe'}})
            self.assertFalse(calls)
            bot.say(1,('📡 Arabic العربية\n')*500)
            self.assertGreater(len(calls),1)
            for _,p in calls:self.assertLessEqual(len(p['text'].encode('utf-16-le'))//2,4096)
    def test_source_does_not_fall_back_to_stale(self):
        from unittest.mock import patch
        s=Source();s.cached=(B,[F],'old');s.at=-99999
        with patch('bot.request_json',side_effect=RemoteError()):
            with self.assertRaises(RemoteError):s.load()
    def test_notifications_sent_once(self):
        from unittest.mock import patch
        now=datetime.now(timezone.utc);event=dict(E,deadline_time=(now+timedelta(hours=2)).isoformat())
        b=copy.deepcopy(B);b['events']=[event]
        r=analyze(b,[F]);source=Source();source.load=lambda:(b,[F],now.isoformat());source.report=lambda gw=None:r
        with tempfile.TemporaryDirectory() as tmp:
            bot=Bot('fake',Store(tmp+'/test.sqlite'),source);bot.store.subscribe(1);calls=[];bot.say=lambda *args:calls.append(args)
            with patch('bot.time.sleep'):
                bot.schedule();bot.schedule()
            self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
