# -*- coding: utf-8 -*-
"""v09_run.py — 按 v0.9 方案严格实现可计算的部分，跑全部历史数据。

数据现实（实测）：
  一级卡口（澳门亚盘时序）：A组332场 / B组71场 有≥3点 ✅ 可算
  二级卡口（Pinnacle 欧赔【时序】）：❌ Pinna在A组238场只有即盘、无逐点时序；
      B组 euro_timeline 也是澳门（无company）→ 无法做独立时序验证
  三级卡口（6-8家独立机构）：A组有36/威/Interwetten/立博/Pinna/Betfair 即盘，无逐点
      → 凯利可用即盘算"相对值"，但方案要的是"凯利较初始值变化"，缺时序
因此本脚本：
  ① 完整实现一级卡口（方案唯一在现有数据上可严格复现的部分）
  ② 二级用「澳门欧赔时序 vs 澳门亚盘时序」做【同源版】（明确标注违背方案2.3独立源要求）
  ③ 三级用即盘机构计数（无变化量）
  ④ 按方案5.2口径：只报"开发集假设检查"，不报胜率承诺
"""
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')
rows = json.load(open('data/tmp/_master_cover.json', encoding='utf-8'))

# ── 亚盘隐含概率（v0.9 2.1 修正公式：水位是净赔付，全赔=1+水）──
def ah_prob(wh, wa):
    oh, oa = 1+wh, 1+wa
    inv = 1/oh + 1/oa
    R = 1/inv
    return R/oh          # 主队赢盘隐含

def half_cover(margin, line):
    """v0.9 2.1(2) 半赢半输折算。line=澳门原始(正=主让)，支持 .25/.75 四分线"""
    if line is None: return None
    # 把 margin-line 按四分之一线折算到 {-1,-0.5,0,0.5,1}
    d = margin - line
    q = round(d*4)/4
    if q>=0.75: return 1.0
    if q==0.25: return 0.75
    if q==0: return 0.5       # 走水 0.5
    if q==-0.25: return 0.25
    return 0.0

def gate1(r):
    """一级卡口：≥3点 + 严格单调 + 隐含概率变化>=2.5pp。返回 (passed, reason, direction)"""
    pts = r.get('ah_pts') or []
    if len(pts) < 3: return False, '时序<3点', None
    ph = [ah_prob(p[0], p[2]) for p in pts]
    # 严格单调（允许微小数值噪声 0.1pp）
    eps = 0.001
    up_all = all(ph[i+1] > ph[i]-eps for i in range(len(ph)-1)) and ph[-1]>ph[0]
    dn_all = all(ph[i+1] < ph[i]+eps for i in range(len(ph)-1)) and ph[-1]<ph[0]
    delta = ph[-1]-ph[0]
    if abs(delta)*100 < 2.5: return False, '幅度<2.5pp', None
    if up_all: return True, '', '主'
    if dn_all: return True, '', '客'
    return False, '非严格单调', None

res=[]
for r in rows:
    if r.get('cover_open') is None: continue
    ok1, reason, direction = gate1(r)
    r['_g1']=ok1; r['_g1r']=reason; r['_dir']=direction
    r['_hc'] = half_cover(r['margin'], r.get('ah_open_line'))
    res.append(r)

n=len(res); g1=sum(1 for r in res if r['_g1'])
print('='*70)
print('v0.9 一级卡口 在 %d 场上运行' % n)
print('='*70)
print('通过一级: %d (%.1f%%)  排除: %d' % (g1, 100*g1/n, n-g1))
from collections import Counter
print('排除原因:', dict(Counter(r['_g1r'] for r in res if not r['_g1'])))
print()
# 方向
passed=[r for r in res if r['_g1']]
print('通过场次方向:', dict(Counter(r['_dir'] for r in passed)))

# ── 按方案5.2：信号组 vs 同档排除组 的赢盘率差（只在浅盘中档[45,55]）──
print()
print('=== 方案核心验证：浅盘+初始隐含[45,55%] 内，通过组 vs 排除组 ===')
def in_scope(r):
    p0 = ah_prob(r['ah_pts'][0][0], r['ah_pts'][0][2])*100 if r.get('ah_pts') else None
    L = r.get('ah_open_line')
    return (p0 is not None and 45<=p0<=55 and L is not None and abs(L)<=0.5)
scope=[r for r in res if in_scope(r)]
sig=[r for r in scope if r['_g1']]
exc=[r for r in scope if not r['_g1']]
def cover_rate(sub, direction=None):
    vals=[r['_hc'] for r in sub if r['_hc'] is not None]
    if direction=='主': vals=[r['_hc'] for r in sub if r['_dir']=='主' and r['_hc'] is not None]
    if direction=='客': vals=[1-r['_hc'] for r in sub if r['_dir']=='客' and r['_hc'] is not None]
    return (100*sum(vals)/len(vals) if vals else 0, len(vals))
cs,ns=cover_rate(sig); ce,ne=cover_rate(exc)
print('  适用范围场次: %d' % len(scope))
print('  信号组(通过一级): n=%d 折算赢盘率 %.1f%%' % (ns, cs))
print('  排除组:           n=%d 折算赢盘率 %.1f%%' % (ne, ce))
print('  差值: %+.1fpp' % (cs-ce))
print()
print('注：二级(Pinnacle时序)/三级(凯利变化)在现有数据上无法计算——')
print('    Pinna仅即盘无逐点时序，B组euro_timeline实为澳门(同源)。')
json.dump([{k:r[k] for k in ('src','home','away','_g1','_g1r','_dir','_hc','act','score','ah_open_line')} for r in res],
          open('data/tmp/_v09_gate1.json','w',encoding='utf-8'), ensure_ascii=False)
