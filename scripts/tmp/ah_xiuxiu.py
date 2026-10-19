#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ah_xiuxiu.py — 邪修实验：澳门亚盘「初盘 → 即时盘」的走势，
   对「初盘方案」是加强(confirm) 还是利空(contradict)？

核心问题（用户提问）:
  已知「初盘赔率所指向的方向」是高命中信号（P≥0.65 → 82.5%）。
  那么亚盘走势（升盘降盘 / 水位升降）能否进一步区分「这次是真信号还是假信号」？

口径
  澳门亚盘行:  ['澳*', 主水, 盘口, 客水, 盘口数值]
  时序 tl_ah:  [[时间, [主水, 盘口字符串, 客水]], ...]  时间降序
  初盘 = 时序最早点？  —— 注意：历史语料里「最早点」不等于真初盘（先前实测 55% 不等）
  🔴 这里两套都测：
     (a) asian 行的第2/4列 作「真初盘」（如果数据源提供 init）
     (b) tl_ah 最早点 作「可得最早」
"""
import json, os, re, sys
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8')
LAB = ('主胜', '平局', '客胜')

def lv(s):
    """'0.5/1' → 0.75 ; '-0.5' → -0.5"""
    if s is None: return None
    s = str(s).strip().replace('+','')
    if '/' in s:
        a,b = s.split('/')[:2]
        try: return (float(a)+float(b))/2
        except ValueError: return None
    try: return float(s)
    except ValueError: return None

def asian_p(w_h, w_a):
    """亚盘双水 → 上盘 EV 中性概率"""
    try:
        lh, la = float(w_h), float(w_a)
    except (TypeError, ValueError):
        return None
    if lh < 1.3: lh += 1.0
    if la < 1.3: la += 1.0
    if lh <= 1 or la <= 1: return None
    return max(0.0, min(1.0, (la-1)/((lh-1)+(la-1))))

rows = json.load(open('data/tmp/_master514.json', encoding='utf-8'))
for r in rows:
    p = [r['ph'], r['pd'], r['pa']]
    i = p.index(max(p)); r['fav']=LAB[i]; r['maxp']=max(p); r['pick']=r['fav']

# 把 A 组的亚盘信息挂到 rows 上（按 league+home+away 匹配）
idx = {}
for b in ('batch_2_5_8','batch_74','batch_140','batch_203'):
    p = os.path.join('data','tmp',b,'blind_parsed.json')
    if not os.path.exists(p): continue
    for x in json.load(open(p,encoding='utf-8')):
        key = (x.get('league'), x.get('home'), x.get('away'))
        idx[key] = x

def norm(s):
    s=(s or '').lower()
    for a,bb in (('ä','a'),('ö','o'),('ü','u'),('é','e'),('á','a'),('í','i'),('ñ','n'),('ç','c')): s=s.replace(a,bb)
    for w in (' ','.','-','_','(',')','（','）',"'",'·'): s=s.replace(w,'')
    return s
idx2 = {(norm(k[0]),norm(k[1]),norm(k[2])): v for k,v in idx.items()}

n_ah = 0
for r in rows:
    x = idx2.get((norm(r.get('lg')), norm(r.get('home')), norm(r.get('away'))))
    if not x: continue
    ah_line = next((a for a in (x.get('asian') or []) if str(a[0]).startswith('澳')), None)
    tl = x.get('tl_ah') or []
    if not ah_line: continue
    pts = []
    for t, v in reversed(tl):        # 时间升序
        try:
            w_h, line_s, w_a = float(v[0]), v[1], float(v[2])
        except (TypeError, ValueError, IndexError):
            continue
        L = lv(line_s)
        if L is None: continue
        pts.append((w_h, L, w_a))
    if len(pts) < 2: continue
    n_ah += 1
    o = pts[0]; e = pts[-1]
    r['ah_open_line'] = o[1]; r['ah_live_line'] = e[1]
    r['ah_line_move'] = e[1]-o[1]
    r['ah_open_w'] = o[0]; r['ah_live_w'] = e[0]
    r['ah_w_move'] = e[0]-o[0]
    r['ah_npts'] = len(pts)
    po, pe = asian_p(o[0],o[2]), asian_p(e[0],e[2])
    r['ah_p_open'] = po*100 if po else None
    r['ah_p_live'] = pe*100 if pe else None
    r['ah_p_move'] = (pe-po)*100 if (po and pe) else None

print('匹配到亚盘时序的场次: %d / %d' % (n_ah, len(rows)))
ok = [r for r in rows if r.get('ah_npts')]
print('可用作分析的: %d' % len(ok))
json.dump(rows, open('data/tmp/_master_ah.json','w',encoding='utf-8'), ensure_ascii=False)
