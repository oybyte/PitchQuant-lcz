# -*- coding: utf-8 -*-
"""v11_freeze.py — 方案§5 冻结前必做：
   1) 用 1+水 公式重算（S 定义）
   2) 核对「P∈[50,60)有效」在新口径下对应区间，写死 G0
   3) 估计主指标 σ
"""
import json, sys, math
sys.stdout.reconfigure(encoding='utf-8')
rows = json.load(open('data/tmp/_master_cover.json', encoding='utf-8'))

def S(h, a):
    oh, oa = 1+h, 1+a
    ih, ia = 1/oh, 1/oa
    return ih/(ih+ia)

# 1) 重算：每场初盘 S、截点 S、ΔS
n=0
for r in rows:
    pts = r.get('ah_pts') or []
    if len(pts)<2: continue
    so = S(pts[0][0], pts[0][2])
    sl = S(pts[-1][0], pts[-1][2])
    r['S_open']=so*100; r['S_live']=sl*100; r['dS']=(sl-so)*100
    r['line_open']=pts[0][1]
    n+=1
print('重算 S 场次:', n)

# 2) 适用范围 G0：平手/平半 + 档位不变 + >=3点 + 初盘S区间待定 + ΔS!=0
def settle(r):
    """跟随得分（按 sign(dS) 方向）"""
    if r.get('score') is None: return None
    hg,ag=map(int,r['score'].split(':')); margin=hg-ag
    L=r.get('ah_open_line')
    if L is None: return None,None
    q=round((margin-L)*4)/4
    score_home = {0.75:1.0,1.0:1.0}.get(q, {0.25:0.75,0:0.5,-0.25:0.25}.get(q,0.0))
    d = r.get('dS',0)
    follow = score_home if d>0 else (1-score_home)
    return follow, score_home

# 扫描不同 G0 区间，找「通过G1严格单调」组 vs 对照 的跟随得分差
def g1(r, T1=2.5):
    pts=r.get('ah_pts') or []
    if len(pts)<3: return None
    s=[S(p[0],p[2]) for p in pts]
    lines=set(round(p[1]*4)/4 for p in pts)
    if len(lines)!=1: return None
    ds=s[-1]-s[0]
    if abs(ds)<1e-12: return None
    dirn=1 if ds>0 else -1
    steps=[s[i+1]-s[i] for i in range(len(s)-1)]
    if any((1 if x>0 else (-1 if x<0 else 0))==-dirn for x in steps): return None
    if sum(1 for x in steps if abs(x)>1e-12)<2: return None
    if abs(ds)*100<T1: return None
    return dirn

print()
print('=== 冻结前必做#2：扫描 G0 初盘S 区间，找跟随得分差最大的档 ===')
print('%-16s %-8s %-12s %-12s %-10s' % ('初盘S区间','适用n','通过G1 n','通过均分','对照均分'))
best=None
for lo,hi in [(40,45),(45,50),(45,55),(50,55),(50,60),(55,60),(45,60),(40,60)]:
    scope=[]
    for r in rows:
        pts=r.get('ah_pts') or []
        if len(pts)<3: continue
        L=pts[0][1]
        if not (abs(L)<=0.5): continue
        if not (lo<=r['S_open']<hi): continue
        if abs(r.get('dS',0))<1e-9: continue
        scope.append(r)
    passed=[r for r in scope if g1(r) is not None]
    ctrl=[r for r in scope if g1(r) is None]
    fp=[settle(r)[0] for r in passed if settle(r)[0] is not None]
    fc=[settle(r)[0] for r in ctrl if settle(r)[0] is not None]
    mp=sum(fp)/len(fp) if fp else 0; mc=sum(fc)/len(fc) if fc else 0
    tag=''
    print('[%.0f,%.0f)%-10s %-8d n=%-3d %.3f      %.3f      %+.3f' % (
        lo,hi,'',len(scope),len(passed),mp,mc,mp-mc))

# 3) σ 估计（follow_score 在适用范围内的标准差）
print()
allfs=[settle(r)[0] for r in rows if settle(r)[0] is not None and abs(r.get('ah_open_line',9))<=0.5]
import statistics
print('=== 冻结前必做#3：主指标 σ ===')
print('浅盘跟随得分 n=%d 均值 %.3f 标准差 %.3f' % (len(allfs), statistics.mean(allfs), statistics.pstdev(allfs)))
json.dump(rows, open('data/tmp/_master_v11.json','w',encoding='utf-8'), ensure_ascii=False)
