# -*- coding: utf-8 -*-
"""v1.1 完整运行：G0/G1 主假设检验（Welch/bootstrap），G2/G3 可行性盘点"""
import json, sys, math, statistics
sys.stdout.reconfigure(encoding='utf-8')
rows = json.load(open('data/tmp/_master_v11.json', encoding='utf-8'))

def S(h,a):
    o_h,o_a=1+h,1+a; i_h,i_a=1/o_h,1/o_a; return i_h/(i_h+i_a)
def settle(r):
    if r.get('score') is None: return None
    hg,ag=map(int,r['score'].split(':')); m=hg-ag; L=r.get('ah_open_line')
    if L is None: return None
    q=round((m-L)*4)/4
    sh={0.75:1.0,1.0:1.0}.get(q,{0.25:0.75,0:0.5,-0.25:0.25}.get(q,0.0))
    return sh if r.get('dS',0)>0 else (1-sh)
def g1(r,T1=2.5):
    pts=r.get('ah_pts') or []
    if len(pts)<3: return (None,'点数')
    s=[S(p[0],p[2]) for p in pts]
    if len({round(p[1]*4)/4 for p in pts})!=1: return (None,'档位变')
    ds=s[-1]-s[0]
    if abs(ds)<1e-12: return (None,'ΔS=0')
    dirn=1 if ds>0 else -1
    steps=[s[i+1]-s[i] for i in range(len(s)-1)]
    if any((1 if x>0 else (-1 if x<0 else 0))==-dirn for x in steps): return (None,'反向步')
    if sum(1 for x in steps if abs(x)>1e-12)<2: return (None,'非零步')
    if abs(ds)*100<T1: return (None,'幅度')
    return (dirn,'')

# 主假设按方案选 G0：先用它自己写的 45-55（§5 让我们改成有效档，但实测无有效档，故保留原档演示）
for LO,HI,label in [(45,55,'方案原档[45,55)'),(50,60,'历史声称有效[50,60)')]:
    scope=[]
    for r in rows:
        pts=r.get('ah_pts') or []
        if len(pts)<3: continue
        L=pts[0][1]
        if not (abs(L)<=0.5): continue
        if not (LO<=r['S_open']<HI): continue
        if abs(r.get('dS',0))<1e-9: continue
        scope.append(r)
    passed=[r for r in scope if g1(r)[0] is not None]
    ctrl=[r for r in scope if g1(r)[0] is None]
    fp=[settle(r) for r in passed if settle(r) is not None]
    fc=[settle(r) for r in ctrl if settle(r) is not None]
    mp=statistics.mean(fp) if fp else 0; mc=statistics.mean(fc) if fc else 0
    # Welch 单侧
    def welch(a,b):
        na,nb=len(a),len(b)
        if na<2 or nb<2: return None
        va,vb=statistics.variance(a),statistics.variance(b)
        se=math.sqrt(va/na+vb/nb)
        t=(statistics.mean(a)-statistics.mean(b))/se if se>0 else 0
        return t,se
    w=welch(fp,fc)
    print('=== G0=%s ===' % label)
    print('  适用 %d  通过 %d  对照 %d' % (len(scope),len(passed),len(ctrl)))
    print('  通过组跟随得分 %.3f   对照组 %.3f   差 %+.3f' % (mp,mc,mp-mc))
    if w: print('  Welch t=%.2f  （主假设需通过组>对照且单侧下限>0）→ %s' % (
        w[0], '✅支持' if (mp>mc and w[0]>1.65) else '❌不支持'))
    print()

# bootstrap 主档
import random
random.seed(42)
scope=[r for r in rows if r.get('ah_pts') and len(r['ah_pts'])>=3 and abs(r['ah_pts'][0][1])<=0.5
       and 45<=r['S_open']<55 and abs(r.get('dS',0))>=1e-9]
passed=[settle(r) for r in scope if g1(r)[0] is not None and settle(r) is not None]
ctrl=[settle(r) for r in scope if g1(r)[0] is None and settle(r) is not None]
diffs=[]
for _ in range(10000):
    a=[random.choice(passed) for _ in passed]
    b=[random.choice(ctrl) for _ in ctrl]
    diffs.append(statistics.mean(a)-statistics.mean(b))
diffs.sort()
lo5=diffs[int(.05*len(diffs))]
print('Bootstrap(1万次) [45,55) 差值 5%%单侧下限: %+.3f  → %s' % (
    lo5, '下限>0 有效' if lo5>0 else '🔴 下限<=0，主假设不成立'))
print()
print('=== G2/G3 可行性（关键）===')
# Pinnacle 时序：两组都查
import os
A_pin_tl=0; A_pin_snap=0; B_pin_tl=0
# A组 Pinna 只有 euro_books 即盘
for b in ('batch_2_5_8','batch_74','batch_140','batch_203'):
    p='data/tmp/%s/blind_parsed.json'%b
    if os.path.exists(p):
        for x in json.load(open(p,encoding='utf-8')):
            if any('Pinna' in str(bb[0]) for bb in (x.get('euro_books') or []) if isinstance(bb,(list,tuple)) and bb):
                A_pin_snap+=1
print('A组 Pinna 即盘快照: %d 场；Pinna 逐点时序: 0 场（tl_eu 为澳门）' % A_pin_snap)
OUT=r'F:\ocr_python_data\football-research\data-2.5.9\output'
for d in os.listdir(OUT):
    pth=os.path.join(OUT,d)
    if not os.path.isdir(pth) or d.startswith('_') or d.endswith('_ocr'): continue
    js=os.path.join(pth,'服务端数据.json')
    if not os.path.exists(js): continue
    det=json.load(open(js,encoding='utf-8'))['detail']
    has_pin=any((e.get('company_en') or '')=='Pinnacle' for e in (det.get('euro') or []))
    etl=det.get('euro_timeline') or []
    pin_tl = has_pin and any((e.get('company_en') or '')=='Pinnacle' for e in etl)
    if pin_tl: B_pin_tl+=1
print('B组 Pinnacle 即盘: 79 场；Pinnacle 逐点时序: %d 场（euro_timeline 为澳门）' % B_pin_tl)
