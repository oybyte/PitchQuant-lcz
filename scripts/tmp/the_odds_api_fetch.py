# -*- coding: utf-8 -*-
"""the-odds-api 欧亚盘多机构拉取（2026-09-27 · 用户选定数据源）

🔴 能力实测（2026-09-27）:
  ✅ current : 当前多机构赔率 —— h2h + spreads(亚盘·可多档) + totals(大小球) · 免费可用
  ❌ history : 历史逐时点快照 —— 免费计划返回 401 HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN（需付费）
  ⚠️ range   : 多时点遍历构造「逐T」 —— 同样需付费计划

免费额度: 500 次/月（响应头 x-requests-remaining 可查）

用法:
  python data/tmp/the_odds_api_fetch.py current [--sport soccer_uefa_nations_league] [--case 206] [--regions eu,uk]
  python data/tmp/the_odds_api_fetch.py history --date 2026-09-26T15:00:00Z [--sport X]
  python data/tmp/the_odds_api_fetch.py range --from 2026-09-26T12:00:00Z --to 2026-09-26T16:00:00Z --step 60
  python data/tmp/the_odds_api_fetch.py quota          # 只看剩余额度

输出（current）:
  data/tmp/snapshots/<case|sport>.json —— 与 odds_snapshot.py 同结构（snapshots[] 追加一个时点）
  · 每个时点: {t, source:"the-odds-api", n_books, events:[{home,away,commence,h2h:[...],spreads:[...],totals:[...]}]}
"""
import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP_DIR = os.path.join(HERE, 'snapshots')
BASE = 'https://api.the-odds-api.com/v4'
DEFAULT_SPORT = 'soccer_uefa_nations_league'


def load_key():
    """key 来源: 环境变量 THE_ODDS_API_KEY → data/tmp/api_keys.json"""
    k = os.environ.get('THE_ODDS_API_KEY', '')
    if k:
        return k
    p = os.path.join(HERE, 'api_keys.json')
    try:
        with io.open(p, encoding='utf-8') as f:
            return (json.load(f) or {}).get('the_odds_api', '')
    except Exception:
        return ''


def fetch(url):
    """直连优先 → 代理回退（真直连须空 ProxyHandler）"""
    last = None
    for opener in (urllib.request.build_opener(urllib.request.ProxyHandler({})),
                   urllib.request.build_opener(urllib.request.ProxyHandler(
                       {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}))):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with opener.open(req, timeout=35) as r:
                hdr = {k.lower(): v for k, v in r.getheaders()}
                return json.loads(r.read().decode('utf-8')), hdr
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', 'replace')
            return {'_http_error': e.code, '_body': body}, {}
        except Exception as e:
            last = e
    raise last


def normalize(events):
    """按场次整理: 每场 → {home, away, commence, markets:{h2h:[...], spreads:[...], totals:[...]}}"""
    out = []
    for e in events or []:
        row = {'home': e.get('home_team'), 'away': e.get('away_team'),
               'commence': e.get('commence_time'), 'id': e.get('id'), 'markets': {}}
        for b in (e.get('bookmakers') or []):
            for m in (b.get('markets') or []):
                row['markets'].setdefault(m.get('key'), []).append(
                    {'book': b.get('key'), 'last_update': m.get('last_update'),
                     'outcomes': m.get('outcomes')})
        out.append(row)
    return out


def save_snapshot(tag, t, rows, n_books, extra=None):
    os.makedirs(SNAP_DIR, exist_ok=True)
    p = os.path.join(SNAP_DIR, '%s.json' % tag)
    d = {'case_id': tag, 'snapshots': []}
    if os.path.exists(p):
        try:
            with io.open(p, encoding='utf-8') as f:
                d = json.load(f)
        except Exception:
            pass
    rec = {'t': t, 'source': 'the-odds-api', 'n_books': n_books, 'events': rows}
    if extra:
        rec.update(extra)
    d.setdefault('snapshots', []).append(rec)
    with io.open(p, 'w', encoding='utf-8') as f:
        f.write(json.dumps(d, ensure_ascii=False, indent=1))
    return p, len(d['snapshots'])


def cmd_current(a):
    key = load_key()
    if not key:
        print('❌ 缺 key（env THE_ODDS_API_KEY 或 data/tmp/api_keys.json 的 the_odds_api）')
        return
    url = ('%s/sports/%s/odds/?apiKey=%s&regions=%s&markets=h2h,spreads,totals&oddsFormat=decimal'
           % (BASE, a.sport, key, a.regions))
    d, h = fetch(url)
    if isinstance(d, dict) and d.get('_http_error'):
        print('❌ HTTP%s | %s' % (d['_http_error'], d['_body'][:200]))
        return
    rows = normalize(d)
    nb = max([len(e.get('bookmakers') or []) for e in d] or [0])
    mk = sorted({k for r in rows for k in r['markets']})
    print('✅ current: %d 场 | 最多 %d 家机构 | markets=%s | 额度剩余 %s'
          % (len(rows), nb, mk, h.get('x-requests-remaining')))
    for r in rows[:6]:
        sp = (r['markets'].get('spreads') or [{}])[0].get('outcomes')
        print('   %-34s 亚盘 %s' % ('%s vs %s' % (r['home'], r['away']), sp))
    tag = a.case or a.sport
    import datetime as dt
    t = a.t or dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    p, n = save_snapshot(tag, t, rows, nb, extra={'sport': a.sport, 'markets': mk,
                                                  'quota_remaining': h.get('x-requests-remaining')})
    print('   已落盘 %s（第 %d 个时点）' % (p, n))
    if n < 2:
        print('   ⚠️ 时序需 ≥2 个时点 → 多次运行本命令即可累积（免费计划可行）')


def cmd_history(a):
    key = load_key()
    if not key:
        print('❌ 缺 key')
        return
    url = ('%s/historical/sports/%s/odds?apiKey=%s&regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal&date=%s'
           % (BASE, a.sport, key, a.date))
    d, h = fetch(url)
    if isinstance(d, dict) and d.get('_http_error'):
        code = d['_http_error']
        body = d['_body']
        if 'HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN' in body:
            print('🔴 历史逐时点需付费计划（免费额度不含 historical）')
            print('   → 免费替代: 多次运行 `current` 自行累积时序（每次 +1 时点）')
        else:
            print('❌ HTTP%s | %s' % (code, body[:200]))
        return
    ts = d.get('timestamp')
    arr = d.get('data') if isinstance(d, dict) else d
    print('✅ history @ %s → %d 场 | prev=%s next=%s | 额度 %s'
          % (ts, len(arr or []), d.get('previous_timestamp'), d.get('next_timestamp'),
             h.get('x-requests-remaining')))
    for r in normalize(arr)[:6]:
        print('   %s vs %s' % (r['home'], r['away']))


def cmd_range(a):
    key = load_key()
    if not key:
        print('❌ 缺 key')
        return
    import datetime as dt
    t0 = dt.datetime.strptime(a.f, '%Y-%m-%dT%H:%M:%SZ')
    t1 = dt.datetime.strptime(a.t, '%Y-%m-%dT%H:%M:%SZ')
    n = 0
    cur = t0
    while cur <= t1:
        url = ('%s/historical/sports/%s/odds?apiKey=%s&regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal&date=%s'
               % (BASE, a.sport, key, cur.strftime('%Y-%m-%dT%H:%M:%SZ')))
        d, h = fetch(url)
        if isinstance(d, dict) and d.get('_http_error'):
            if 'HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN' in d.get('_body', ''):
                print('🔴 range 需付费计划（historical）→ 请改用多次 `current` 累积')
            else:
                print('❌ HTTP%s' % d['_http_error'])
            return
        n += 1
        print('   %s → %d 场（额度 %s）' % (cur.strftime('%m-%d %H:%M'), len(d.get('data') or []),
                                        h.get('x-requests-remaining')))
        cur += dt.timedelta(minutes=a.step)
    print('✅ 遍历 %d 个时点完成' % n)


def cmd_books(a):
    """把 the-odds-api 快照的某场 h2h 转成 books.json（喂 market_consensus / P0-1 跨机构分歧）"""
    tag = a.case or a.sport
    p = os.path.join(SNAP_DIR, '%s.json' % tag)
    if not os.path.exists(p):
        print('❌ 无快照 %s（先跑 current）' % p)
        return
    d = json.load(io.open(p, encoding='utf-8'))
    snaps = d.get('snapshots') or []
    evs = (snaps[-1].get('events') or []) if snaps else []
    books, found = [], None
    for e in evs:
        if a.home and a.home.lower() not in (e.get('home') or '').lower():
            continue
        if a.away and a.away.lower() not in (e.get('away') or '').lower():
            continue
        found = e
        for entry in (e.get('markets', {}).get('h2h') or []):
            oc = {o['name']: o['price'] for o in entry.get('outcomes', [])}
            books.append({'bookmaker': entry.get('book'), 'h': oc.get(e['home']),
                          'd': oc.get('Draw'), 'a': oc.get(e['away'])})
        break
    if not found:
        print('❌ 快照中未找到 %s vs %s（共 %d 场）' % (a.home, a.away, len(evs)))
        return
    out = a.out or os.path.join(HERE, 'fundflow_books.json')
    # 🔴2026-09-27 审计P0: 写包装 dict（含 fixture/home/away）→ market_consensus.match_check 可做场次错配校验
    obj = {'status': 'ok', 'fixture': found.get('id'), 'home': found.get('home'), 'away': found.get('away'),
           'n_books': len(books), 'key_source': 'the-odds-api', 'books': books}
    io.open(out, 'w', encoding='utf-8').write(json.dumps(obj, ensure_ascii=False, indent=1))
    print('✅ %s vs %s → %d 家机构 → %s' % (found.get('home'), found.get('away'), len(books), out))
    print('   下一步: python data/tmp/market_consensus.py --books "%s"' % out)


def cmd_quota(a):
    key = load_key()
    d, h = fetch('%s/sports/?apiKey=%s' % (BASE, key))
    print('额度剩余: %s | 已用: %s' % (h.get('x-requests-remaining'), h.get('x-requests-used')))
    if isinstance(d, dict) and d.get('_http_error'):
        print('❌ HTTP%s | %s' % (d['_http_error'], d['_body'][:160]))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd')
    p1 = sub.add_parser('current'); p1.add_argument('--sport', default=DEFAULT_SPORT)
    p1.add_argument('--case'); p1.add_argument('--regions', default='eu,uk'); p1.add_argument('--t')
    p2 = sub.add_parser('history'); p2.add_argument('--sport', default=DEFAULT_SPORT)
    p2.add_argument('--date', required=True)
    p3 = sub.add_parser('range'); p3.add_argument('--sport', default=DEFAULT_SPORT)
    p3.add_argument('--from', dest='f', required=True); p3.add_argument('--to', dest='t', required=True)
    p3.add_argument('--step', type=int, default=60)
    p4 = sub.add_parser('books'); p4.add_argument('--sport', default=DEFAULT_SPORT)
    p4.add_argument('--case'); p4.add_argument('--home'); p4.add_argument('--away'); p4.add_argument('--out')
    sub.add_parser('quota')
    a = ap.parse_args()
    {'current': cmd_current, 'history': cmd_history, 'range': cmd_range,
     'books': cmd_books, 'quota': cmd_quota}.get(
        a.cmd, lambda x: ap.print_help())(a)


if __name__ == '__main__':
    main()
