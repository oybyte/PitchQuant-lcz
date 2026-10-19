#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fundamentals_join.py — 中英队名映射 + Elo/赔率/结果三方对齐
   🔴 这是「基本面能否带来增量」的决定性实验的前置：先把两侧真正接上"""
import json, os, re, ssl, sys, urllib.request
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 中文 → openligadb 英文（手工对齐·覆盖我方 79 场里五大联赛的队）
CN2EN = {
 # 德甲
 '云达不莱梅':'SV Werder Bremen','帕德博恩':'SC Paderborn 07','沙尔克04':'FC Schalke 04',
 '美因茨':'1. FSV Mainz 05','埃弗斯堡':'SV 07 Elversberg','奥格斯堡':'FC Augsburg',
 '拜仁慕尼黑':'FC Bayern München','RB莱比锡':'RB Leipzig','勒沃库森':'Bayer 04 Leverkusen',
 '弗赖堡':'SC Freiburg','门兴格拉德巴赫':'Borussia Mönchengladbach','霍芬海姆':'TSG Hoffenheim',
 '柏林联合':'1. FC Union Berlin','多特蒙德':'Borussia Dortmund','汉堡':'Hamburger SV',
 '斯图加特':'VfB Stuttgart','法兰克福':'Eintracht Frankfurt','科隆':'1. FC Köln',
 # 英超
 '伯恩茅斯':'AFC Bournemouth','桑德兰':'Sunderland AFC','利兹联':'Leeds United',
 '曼彻斯特联':'Manchester United FC','埃弗顿':'Everton FC','切尔西':'Chelsea FC',
 '富勒姆':'Fulham FC','赫尔城':'Hull City','布伦特福德':'Brentford F.C.',
 '利物浦':'Liverpool FC','曼彻斯特城':'Manchester City FC','伊普斯维奇':'Ipswich Town',
 '纽卡斯尔联':'Newcastle United FC','阿斯顿维拉':'Aston Villa',
 '诺丁汉森林':"Nottingham Forest FC",'阿森纳':'Arsenal FC',
 # 西甲
 '塞尔塔':'Celta Vigo','阿拉维斯':'Deportivo Alaves','奥萨苏纳':'CA Osasuna',
 '桑坦德竞技':'Racing Santander','巴伦西亚':'Valencia CF','毕尔巴鄂竞技':'Athletic Club',
 '拉科鲁尼亚':'Deportivo A Coruña','莱万特':'Levante UD','比利亚雷亚尔':'Villarreal CF',
 '埃尔切':'Elche CF','皇家贝蒂斯':'Real Betis','巴塞罗那':'FC Barcelona',
 '皇家马德里':'Real Madrid','塞维利亚':'Sevilla FC','西班牙人':'Espanyol Barcelona',
 '马德里竞技':'Atlético Madrid','马拉加':'Málaga CF','皇家社会':'Real Sociedad',
}

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
        return json.loads(r.read().decode('utf-8','ignore'))

LG = {'pl':'英超','la1':'西甲','bl1':'德甲'}

def build():
    # 1) Elo
    E = {}
    d = json.load(open(os.path.join(ROOT,'data','tmp','clubelo_20261019.json'), encoding='utf-8'))
    for lg, v in (d.get('leagues') or {}).items():
        for t in (v.get('teams') or []):
            if t.get('name') and t.get('elo'):
                E.setdefault(lg, {})[t['name']] = float(t['elo'])
    # 2) 我方赔率
    ev = json.load(open(os.path.join(ROOT,'data','tmp','batch_output','_eval.json'), encoding='utf-8'))
    odds = {}
    LAB=('主胜','平局','客胜')
    for r in ev:
        p = r['key'].split('_')
        if len(p) < 7: continue
        lg, h, a = p[3], p[4], p[6]
        if lg not in ('英超','西甲','德甲'): continue
        t = open(os.path.join(ROOT,'data','tmp','batch_output','out',r['key']+'.txt'), encoding='utf-8').read()
        m = re.search(r'隐含: 主([0-9.]+)%/平([0-9.]+)%/客([0-9.]+)%', t)
        if not m: continue
        pp = [float(m.group(i)) for i in (1,2,3)]
        odds[(lg,h,a)] = dict(pick=LAB[pp.index(max(pp))], p=pp, act=r['truth']['act'])
    # 3) openligadb 赛果
    ms = []
    for slug, cn in LG.items():
        for x in get('https://api.openligadb.de/getmatchdata/%s/2026' % slug):
            if not x.get('matchIsFinished'): continue
            res = [y for y in (x.get('matchResults') or []) if y['resultTypeID']==2]
            if not res: continue
            ms.append(dict(lg=cn, dt=x['matchDateTime'], h=x['team1']['teamName'],
                           a=x['team2']['teamName'],
                           hg=res[0]['pointsTeam1'], ag=res[0]['pointsTeam2']))
    ms.sort(key=lambda m: m['dt'])
    return E, odds, ms

def elo_side(E, lg, en):
    pool = E.get(lg) or {}
    if en in pool: return pool[en]
    def nz(s):
        s=(s or '').lower()
        for a,b in (('ä','a'),('ö','o'),('ü','u'),('é','e'),('á','a'),('í','i'),('ñ','n'),('ç','c')):
            s=s.replace(a,b)
        for w in ('fc ', 'fc', 'cf ', 'club ', 'sc ', 'vfb ', 'vfl ', 'tsg ', 'sv ',
                  'ac ', 'ca ', 'ud ', '1. ', '.', '-', ' ', '&', "'"):
            s=s.replace(w,'')
        return s
    t = nz(en)
    for n,e in pool.items():
        if nz(n)==t: return e
    for n,e in pool.items():
        nn=nz(n)
        if t and (t in nn or nn in t): return e
    return None

if __name__ == '__main__':
    E, odds, ms = build()
    print('Elo 联赛:', {k: len(v) for k,v in E.items()})
    print('我方赔率(五大):', len(odds))
    print('openligadb 已完赛:', len(ms))
    # 对齐我方 79 场
    ok = 0; matched = []
    for (lg,h,a), o in odds.items():
        hen, aen = CN2EN.get(h), CN2EN.get(a)
        if not hen or not aen: 
            print('  未映射:', lg, h, a); continue
        rec = [m for m in ms if m['lg']==lg and m['h']==hen and m['a']==aen]
        eh, ea = elo_side(E, lg, hen), elo_side(E, lg, aen)
        if rec and eh and ea:
            ok += 1
            matched.append(dict(lg=lg,h=h,a=a,hen=hen,aen=aen,eh=eh,ea=ea,
                                odds=o, truth=o['act'], score='%d:%d'%(rec[0]['hg'],rec[0]['ag'])))
    print('三方对齐成功:', ok)
    json.dump(matched, open(os.path.join(ROOT,'data','tmp','_joined.json'),'w',encoding='utf-8'),
              ensure_ascii=False, indent=1)
