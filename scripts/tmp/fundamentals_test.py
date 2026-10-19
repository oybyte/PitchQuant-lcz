#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fundamentals_test.py — 基本面 vs 赔率：用 clubelo 正式 Elo（极差 400，区分力充足）

三个模型对照（同批场次、同一切割）
  A 赔率热门      （市场基线，来自我方 2.5.9 快照）
  B 纯 Elo        （clubelo 赛前 Elo + 主场优势）
  C Elo+近况      （ElO + 近 5 场攻防）
关键看：B/C 在「与赔率分歧」的子集上是否更准
"""
import json
import os
import re
import ssl
import sys
import urllib.request
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'data', 'tmp', 'fundamentals.json')
LG = {'pl': '英超', 'la1': '西甲', 'bl1': '德甲'}
LAB = ('主胜', '平局', '客胜')


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
        return json.loads(r.read().decode('utf-8', 'ignore'))


def load_elo():
    """clubelo 落盘 → {(联赛中文, 队名): elo}"""
    p = os.path.join(ROOT, 'data', 'tmp', 'clubelo_20261019.json')
    d = json.load(open(p, encoding='utf-8'))
    E = {}
    for lg, v in (d.get('leagues') or {}).items():
        for t in (v.get('teams') or []):
            if t.get('name') and t.get('elo'):
                E[(lg, t['name'])] = float(t['elo'])
    return E


def norm(s):
    s = (s or '').lower()
    for a, b in (('ä', 'a'), ('ö', 'o'), ('ü', 'u'), ('é', 'e'), ('è', 'e'), ('ñ', 'n')):
        s = s.replace(a, b)
    for w in ('fc ', 'fc', 'cf ', 'club ', 'sc ', 'vfb ', 'vfl ', 'tsg ', 'sv ', '1. ', '.', '-', ' '):
        s = s.replace(w, '')
    return s


def match_elo(E, lg, team):
    """在 clubelo 里找队名（精确 → 归一化 → 包含）"""
    pool = {n: e for (l, n), e in E.items() if l == lg}
    if team in pool:
        return pool[team]
    nt = norm(team)
    for n, e in pool.items():
        if norm(n) == nt:
            return e
    for n, e in pool.items():
        nn = norm(n)
        if nt and (nt in nn or nn in nt):
            return e
    return None


def fetch_matches():
    out = []
    for slug, cn in LG.items():
        d = get('https://api.openligadb.de/getmatchdata/%s/2026' % slug)
        for x in d:
            if not x.get('matchIsFinished'):
                continue
            res = [y for y in (x.get('matchResults') or []) if y['resultTypeID'] == 2]
            if not res:
                continue
            out.append(dict(lg=cn, slug=slug, dt=x['matchDateTime'],
                            h=x['team1']['teamName'], a=x['team2']['teamName'],
                            hg=res[0]['pointsTeam1'], ag=res[0]['pointsTeam2']))
    out.sort(key=lambda m: m['dt'])
    return out


def load_odds():
    """我方 79 场的赔率热门（按队名+联赛匹配）"""
    ev = json.load(open(os.path.join(ROOT, 'data', 'tmp', 'batch_output', '_eval.json'),
                        encoding='utf-8'))
    out = {}
    for r in ev:
        parts = r['key'].split('_')
        if len(parts) < 7:
            continue
        lg, h, a = parts[3], parts[4], parts[6]
        t = open(os.path.join(ROOT, 'data', 'tmp', 'batch_output', 'out', r['key'] + '.txt'),
                 encoding='utf-8').read()
        m = re.search(r'隐含: 主([0-9.]+)%/平([0-9.]+)%/客([0-9.]+)%', t)
        if not m:
            continue
        p = [float(m.group(i)) for i in (1, 2, 3)]
        out[(lg, h, a)] = dict(pick=LAB[p.index(max(p))], p=p, act=r['truth']['act'])
    return out


CN2DE = {'云达不莱梅': 'SV Werder Bremen', '帕德博恩': 'SC Paderborn 07',
         '沙尔克04': 'FC Schalke 04', '美因茨': '1. FSV Mainz 05',
         '埃弗斯堡': 'SV 07 Elversberg', '奥格斯堡': 'FC Augsburg',
         '拜仁慕尼黑': 'FC Bayern München', 'RB莱比锡': 'RB Leipzig',
         '勒沃库森': 'Bayer 04 Leverkusen', '弗赖堡': 'SC Freiburg',
         '门兴格拉德巴赫': 'Borussia Mönchengladbach', '霍芬海姆': 'TSG Hoffenheim',
         '柏林联合': '1. FC Union Berlin', '多特蒙德': 'Borussia Dortmund',
         '汉堡': 'Hamburger SV', '斯图加特': 'VfB Stuttgart',
         '法兰克福': 'Eintracht Frankfurt', '科隆': '1. FC Köln'}


def main():
    E = load_elo()
    print('clubelo 队伍 %d' % len(E))
    odds = load_odds()
    print('我方赔率场次 %d' % len(odds))
    matches = fetch_matches()
    print('openligadb 已完赛 %d' % len(matches))

    # 历史（用于近况）
    hist = defaultdict(list)
    rows = []
    for m in matches:
        eh = match_elo(E, m['lg'], m['h'])
        ea = match_elo(E, m['lg'], m['a'])
        if eh and ea:
            truth = '主胜' if m['hg'] > m['ag'] else ('平局' if m['hg'] == m['ag'] else '客胜')
            hf = hist[m['h']][-5:]; af = hist[m['a']][-5:]
            rows.append(dict(lg=m['lg'], h=m['h'], a=m['a'], dt=m['dt'],
                             eh=eh, ea=ea, truth=truth,
                             hatk=sum(x[0] for x in hf) / max(len(hf), 1),
                             hdef=sum(x[1] for x in hf) / max(len(hf), 1),
                             aatk=sum(x[0] for x in af) / max(len(af), 1),
                             adef=sum(x[1] for x in af) / max(len(af), 1),
                             nh=len(hf), na=len(af)))
        hist[m['h']].append((m['hg'], m['ag']))
        hist[m['a']].append((m['ag'], m['hg']))

    print('Elo 可匹配 %d 场' % len(rows))

    def elo_pick(r, use_form):
        d = (r['eh'] - r['ea']) + 60.0       # 主场优势约 60 Elo
        exp = 1 / (1 + 10 ** (-d / 400))
        if use_form and r['nh'] >= 3 and r['na'] >= 3:
            atk = (r['hatk'] - r['adef']) - (r['aatk'] - r['hdef'])
            exp += atk * 0.02
        exp = max(0.05, min(0.92, exp))
        pd = max(0.14, 0.30 - abs(exp - 0.5) * 0.40)
        rest = 1 - pd
        p = [rest * exp, pd, rest * (1 - exp)]
        return LAB[p.index(max(p))], p

    n = len(rows)
    hit_elo = sum(1 for r in rows if elo_pick(r, False)[0] == r['truth'])
    hit_form = sum(1 for r in rows if elo_pick(r, True)[0] == r['truth'])
    print()
    print('=== 全样本（openligadb 真实赛果·含 Elo 可匹配的）===')
    print('  n=%d' % n)
    print('  B 纯 Elo        %d/%d = %.1f%%' % (hit_elo, n, hit_elo / n * 100))
    print('  C Elo+近况      %d/%d = %.1f%%' % (hit_form, n, hit_form / n * 100))
    print('  永远押主胜       %.1f%%' % (
        sum(1 for r in rows if r['truth'] == '主胜') / n * 100))

    print()
    print('=== 按 Elo 差距分层（纯 Elo）===')
    t = defaultdict(lambda: [0, 0])
    for r in rows:
        d = abs(r['eh'] - r['ea'])
        b = '<80' if d < 80 else ('80-160' if d < 160 else ('160-260' if d < 260 else '>=260'))
        t[b][0] += (elo_pick(r, False)[0] == r['truth'])
        t[b][1] += 1
    for b in ('<80', '80-160', '160-260', '>=260'):
        if t[b][1]:
            print('  Elo差%-8s n=%-3d 命中 %5.1f%%' % (b, t[b][1], t[b][0] / t[b][1] * 100))

    json.dump(dict(n=n, elo=hit_elo, form=hit_form), open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print()
    print('→', OUT)


if __name__ == '__main__':
    main()
