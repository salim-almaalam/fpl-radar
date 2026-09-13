"""Transparent FPL ranking. Scores are heuristic indices, never expected points."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import math

POSITIONS = {1: 'حراس المرمى', 2: 'الدفاع', 3: 'الوسط', 4: 'الهجوم'}
BUDGET = {1: 5, 2: 5, 3: 6.5, 4: 7}

def number(value, default=0):
    try:
        n = float(value)
        return n if math.isfinite(n) else default
    except (TypeError, ValueError):
        return default

def utc(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))

def next_event(bootstrap, now=None):
    now = now or datetime.now(timezone.utc)
    return next(iter(sorted((e for e in bootstrap['events'] if utc(e['deadline_time']) > now), key=lambda e: e['id'])), None)

def analyze(b, fixtures, event=None, now=None):
    now = now or datetime.now(timezone.utc)
    event = event or next_event(b, now)
    if event is None:
        raise ValueError('لا توجد جولة قادمة معلنة حاليًا.')
    if utc(event['deadline_time']) <= now:
        raise ValueError('هذه الجولة أغلقت؛ استخدم /history لعرض تقرير محفوظ بدل تحليل بأثر رجعي.')
    teams = {t['id']: t['short_name'] for t in b['teams']}
    team_games = {t: sum(bool(f.get('finished')) and t in (f['team_h'], f['team_a']) for f in fixtures) for t in teams}
    def games(team, gw):
        result = []
        for f in fixtures:
            if f.get('event') != gw or team not in (f['team_h'], f['team_a']):
                continue
            home = team == f['team_h']
            result.append({'opponent': teams[f['team_a'] if home else f['team_h']], 'home': home,
                           'difficulty': number(f.get('team_h_difficulty' if home else 'team_a_difficulty'), 3) or 3,
                           'kickoff': f.get('kickoff_time')})
        return result
    rows = []
    for p in b['elements']:
        pos = p['element_type']
        if pos not in POSITIONS or p.get('status') in ('i', 's', 'u', 'n') or p.get('removed') or p.get('can_select') is False:
            continue
        chance = p.get('chance_of_playing_next_round')
        availability = number(chance, 100) / 100
        if availability < .75:
            continue
        g = games(p['team'], event['id'])
        if not g:
            continue  # no fixture / blank gameweek
        played = max(1, team_games[p['team']])
        reliability = min(1, number(p.get('minutes')) / (90 * played))
        # No performance history: do not invent confidence for debutants.
        if number(p.get('minutes')) <= 0:
            continue
        form = min(1, max(0, number(p.get('form'))) / 10)
        ppg = min(1, max(0, number(p.get('points_per_game'))) / 8)
        fixture = sum(max(.2, (6 - x['difficulty']) / 5) for x in g)
        involvement = number(p.get('expected_goal_involvements_per_90'))
        if pos in (1, 2):
            underlying = .7 * max(0, 1 - number(p.get('expected_goals_conceded_per_90'), 2) / 3) + .3 * min(1, involvement / .5)
        else:
            underlying = min(1, involvement / .8)
        score = (32 * form + 22 * ppg + 18 * reliability + 18 * fixture + 10 * underlying) * availability
        # Multiple matches affect points opportunities; cap only the displayed index.
        score = round(min(100, score), 1)
        price = number(p['now_cost']) / 10
        rows.append({'id': p['id'], 'name': p['web_name'], 'team': teams[p['team']], 'position': pos,
                     'price': price, 'score': score, 'value': round(score / max(price, .1), 2),
                     'form': number(p.get('form')), 'ppg': number(p.get('points_per_game')),
                     'minutes': int(number(p.get('minutes'))), 'reliability': round(reliability * 100),
                     'ownership': number(p.get('selected_by_percent')), 'chance': round(availability * 100),
                     'availability_known': chance is not None, 'status': p.get('status'), 'news': p.get('news', ''), 'fixtures': g,
                     'outlook': [{'gw': gw, 'games': games(p['team'], gw)} for gw in range(event['id'], min(39, event['id'] + 3))],
                     'confidence': 'محدودة' if played < 5 or reliability < .65 else 'متوسطة'})
    rows.sort(key=lambda p: (-p['score'], p['id']))
    return {'event': event, 'updated': now.isoformat(), 'players': rows,
            'source': 'https://fantasy.premierleague.com/api/', 'method': 'heuristic-v1'}

def select(report, kind='gw', pos=None, max_price=None):
    rows = report['players']
    if pos:
        rows = [p for p in rows if p['position'] == pos]
    if max_price is not None:
        rows = [p for p in rows if p['price'] <= max_price]
    if kind == 'budget':
        rows = [p for p in rows if p['price'] <= BUDGET[p['position']] and p['reliability'] >= 60]
        rows = sorted(rows, key=lambda p: (-p['value'], -p['score']))
    elif kind == 'differentials':
        rows = [p for p in rows if p['ownership'] < 10 and p['reliability'] >= 60]
    elif kind == 'captain':
        rows = [p for p in rows if p['position'] in (3, 4) and p['chance'] == 100 and p['status'] == 'a' and p['reliability'] >= 65]
    return rows

def fixture_text(p):
    return ' + '.join(f"{g['opponent']} ({'أرضه' if g['home'] else 'خارج'}) · {g['difficulty']:g}/5" for g in p['fixtures'])

def player_text(p):
    availability_text = str(p['chance']) + '%' if p.get('availability_known', True) else 'غير محددة'
    reasons = []
    if p['form'] >= 5: reasons.append('أداء حديث جيد')
    if p['reliability'] >= 75: reasons.append('دقائق موسمية مرتفعة')
    if len(p['fixtures']) > 1: reasons.append('جولة مزدوجة')
    if min(g['difficulty'] for g in p['fixtures']) <= 2: reasons.append('مواجهة سهلة نسبيًا')
    reason = '، '.join(reasons) or 'أفضلية نسبية في المؤشر المركب'
    warning = '\n⚠️ ' + p['news'][:180] if p['news'] else ''
    return (f"{p['name']} · {p['team']} · £{p['price']:.1f}m\n"
            f"{fixture_text(p)}\n"
            f"مؤشر الترشيح {p['score']}/100 | فورمة {p['form']:g} | ملكية {p['ownership']:g}%\n"
            f"حصة الدقائق التقريبية {p['reliability']}% | إتاحة المصدر {availability_text} | ثقة {p['confidence']}\n"
            f"سبب الترشيح: {reason}" + warning)

def report_text(r, kind='gw', pos=None, max_price=None):
    deadline = utc(r['event']['deadline_time']).astimezone(ZoneInfo('Asia/Muscat')).strftime('%Y-%m-%d %H:%M')
    titles = {'gw': 'ترشيحات الجولة', 'budget': 'القيمة مقابل السعر', 'captain': 'مرشحو الكابتن', 'differentials': 'اختيارات قليلة الملكية'}
    text = f"📡 رادار الجولة {r['event']['id']} — {titles.get(kind, titles['gw'])}\n⏳ الإغلاق: {deadline} بتوقيت عُمان\n"
    rows = select(r, kind, pos, max_price)
    if kind == 'captain' or pos:
        text += '\n\n'.join(player_text(p) for p in rows[:4]) or '\nلا توجد خيارات مطابقة.'
    else:
        for position, label in POSITIONS.items():
            text += f'\n\n▰ {label}\n' + ('\n\n'.join(player_text(p) for p in [x for x in rows if x['position'] == position][:3]) or 'لا توجد خيارات مطابقة.')
    text += '\n\nالأسعار من ميزانية اللعبة الافتراضية. المؤشر للمقارنة وليس نقاطًا متوقعة. راجع أخبار التشكيل قبل الإغلاق.'
    text += '\nوقت جلب البيانات: ' + r['updated'][:16].replace('T', ' ') + ' UTC'
    return text
